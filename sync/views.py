import os
import jwt
import psutil
import subprocess
import sys
import json
import logging
from decimal import Decimal
from datetime import datetime, date, timedelta
from functools import wraps
from decimal import Decimal, ROUND_HALF_UP
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .sql_helper import get_connection, _get_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

PAIR_PASSWORD = os.getenv("PAIR_PASSWORD", "IMC-MOBILE")

# ✅ Make JWT robust: default secret if env missing (so login won’t fail silently)
JWT_SECRET = os.getenv("JWT_SECRET") or "dev-secret-change-me"
JWT_ALGO   = os.getenv("JWT_ALGO", "HS256")


# ------------------ helpers ------------------
def _extract_token(request):
    hdr = request.headers.get("Authorization", "")
    if not hdr.startswith("Bearer "):
        return None
    return hdr.split(" ", 1)[1]

def _decode(token):
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])

def jwt_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        token = _extract_token(request)
        if not token:
            return JsonResponse({"detail": "Token missing"}, status=401)
        try:
            payload = _decode(token)
            request.userid = payload["sub"]
        except jwt.ExpiredSignatureError:
            return JsonResponse({"detail": "Token expired"}, status=401)
        except jwt.PyJWTError:
            return JsonResponse({"detail": "Invalid token"}, status=401)
        return view_func(request, *args, **kwargs)
    return _wrapped

def _to_float(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, Decimal):
        return float(x)
    try:
        return float(str(x))
    except Exception:
        return None

def _coerce_date(v):
    """
    Accepts date objects, ISO strings 'YYYY-MM-DD', 'YYYY/MM/DD', or empty -> use today's date.
    SQL Anywhere understands DATE, but passing a Python date is safest.
    """
    if isinstance(v, date):
        return v
    if not v:
        return date.today()
    s = str(v).strip().replace("/", "-")
    # try common formats
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    # fallback: today
    return date.today()


# ------------------ endpoints ------------------
@csrf_exempt
@require_http_methods(["POST"])
def pair_check(request):
    try:
        data = json.loads(request.body or b"{}")
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    logging.info("📱 Pair check request from: %s", data)

    if data.get("password") != PAIR_PASSWORD:
        logging.error("❌ Invalid password")
        return JsonResponse({"detail": "Invalid password"}, status=401)

    exe_name = "SyncService.exe"
    base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    exe_path = os.path.join(base_dir, exe_name)

    if not os.path.exists(exe_path):
        logging.error("❌ SyncService.exe not found at %s", exe_path)
        return JsonResponse({"detail": "SyncService.exe not found"}, status=404)

    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] and "SyncService.exe" in proc.info["name"]:
                logging.info("🔄 SyncService already running (PID %s)", proc.info["pid"])
                return JsonResponse({"status": "success", "message": "SyncService already running", "pair_successful": True})
        except Exception:
            continue

    try:
        subprocess.Popen([exe_path], cwd=base_dir)
        logging.info("✅ SyncService started")
        return JsonResponse({"status": "success", "message": "SyncService launched successfully", "pair_successful": True})
    except Exception as e:
        logging.error("❌ Failed to start SyncService: %s", e)
        return JsonResponse({"detail": f"Failed to start sync service: {e}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def login(request):
    """
    POST { "userid": "...", "password": "..." }
    Fixes:
      • default JWT secret so encode never crashes
      • clearer error messages
    """
    try:
        data = json.loads(request.body or b"{}")
        userid = (data.get("userid") or "").strip()
        password = (data.get("password") or "").strip()
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    if not userid or not password:
        return JsonResponse({"detail": "userid & password required"}, status=400)

    logging.info("🔐 Login attempt for user: %s", userid)

    try:
        conn = get_connection()
        cur = conn.cursor()
        # SQL Anywhere compatible positional parameters (?)
        cur.execute("SELECT id, pass FROM acc_users WHERE id = ? AND pass = ?", (userid, password))
        row = cur.fetchone()
    except Exception as dbx:
        logging.exception("DB error during login")
        return JsonResponse({"detail": f"DB error: {dbx}"}, status=500)
    finally:
        try:
            cur.close(); conn.close()
        except Exception:
            pass

    if not row:
        logging.warning("❌ Invalid credentials")
        return JsonResponse({"detail": "Invalid credentials"}, status=401)

    payload = {"sub": userid, "exp": datetime.utcnow() + timedelta(days=7)}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    # PyJWT v2 returns a str already; in v1 it may be bytes
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    logging.info("✅ Login successful")
    return JsonResponse({"status": "success", "message": "Login successful", "user_id": row[0], "token": token})


@jwt_required
@require_http_methods(["GET"])
def verify_token(request):
    logging.info("✅ Token verified for user: %s", request.userid)
    return JsonResponse({"status": "success", "userid": request.userid})






@require_http_methods(["GET"])
def get_status(request):
    cfg = _get_config()
    primary = cfg.get("ip", "unknown")
    all_ips = cfg.get("all_ips", [])
    return JsonResponse({
        "status": "online",
        "message": "SyncAnywhere server is running",
        "primary_ip": primary,
        "all_available_ips": all_ips,
        "connection_urls": [f"http://{ip}:8000" for ip in all_ips],
        "pair_password_hint": f"Password starts with: {PAIR_PASSWORD[:3]}...",
        "server_time": datetime.now().isoformat(),
        "instructions": {
            "mobile_setup": "Try connecting to any of the URLs listed in 'connection_urls'",
            "troubleshooting": [
                "Ensure both devices are on the same WiFi network",
                "Try each IP address if the first one doesn't work",
                "Check firewall settings on the server computer",
                "Verify port 8000 is not blocked"
            ]
        }
    })


@jwt_required
@require_http_methods(["GET"])
def get_items(request):
    item_code = request.GET.get("item_code")

    try:
        conn = get_connection()
        cur = conn.cursor()

        if item_code:
            cur.execute("""
                SELECT
                    i.item_code,
                    i.item_name,
                    i.rate,
                    i.rate1,
                    i.rate2,
                    i.kitchen,
                    i.activity,
                    i.image,
                    c.name,
                    i.taxper,
                    i.longname
                FROM tb_item_master i
                LEFT JOIN dine_itemcategory c
                    ON i.category = c.code
                WHERE i.item_code = ?
            """, (item_code,))
        else:
            cur.execute("""
                SELECT
                    i.item_code,
                    i.item_name,
                    i.rate,
                    i.rate1,
                    i.rate2,
                    i.kitchen,
                    i.activity,
                    i.image,
                    c.name,
                    i.taxper,
                    i.longname
                FROM tb_item_master i
                LEFT JOIN dine_itemcategory c
                    ON i.category = c.code
            """)

        rows = cur.fetchall()

        data = []
        for r in rows:
            data.append({
                "item_code": r[0],
                "item_name": r[1],
                "rate": r[2],
                "rate1": r[3],
                "rate2": r[4],
                "kitchen": r[5],
                "activity": r[6],
                "image": r[7],

                # ✅ ONLY CATEGORY NAME
                "category": r[8],

                "taxper": r[9],
                "longname": r[10]
            })

        return JsonResponse({
            "status": "success",
            "count": len(data),
            "items": data
        })

    except Exception as e:
        return JsonResponse(
            {"status": "error", "detail": str(e)},
            status=500
        )

    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass



@jwt_required
@require_http_methods(["GET"])
def get_dine_tables(request):
    """
    GET /dine-tables/
    GET /dine-tables/?tableno=T01
    """

    tableno = request.GET.get("tableno")

    try:
        conn = get_connection()
        cur = conn.cursor()

        if tableno:
            # 🔹 Particular table
            cur.execute("""
                SELECT
                    tableno,
                    description,
                    section
                FROM dine_tables
                WHERE tableno = ?
            """, (tableno,))
        else:
            # 🔹 All tables
            cur.execute("""
                SELECT
                    tableno,
                    description,
                    section
                FROM dine_tables
            """)

        rows = cur.fetchall()

        data = []
        for r in rows:
            data.append({
                "tableno": r[0],
                "description": r[1],
                "section": r[2]
            })

        return JsonResponse({
            "status": "success",
            "count": len(data),
            "tables": data
        })

    except Exception as e:
        return JsonResponse(
            {"status": "error", "detail": str(e)},
            status=500
        )

    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass

@jwt_required
@require_http_methods(["GET"])
def get_user_settings(request):
    """
    GET /user-settings/
    GET /user-settings/?uid=USER01
    """

    uid = request.GET.get("uid")

    try:
        conn = get_connection()
        cur = conn.cursor()

        if uid:
            # 🔹 Particular user
            cur.execute("""
                SELECT
                    uid,
                    code
                FROM acc_userssettings
                WHERE uid = ?
            """, (uid,))
        else:
            # 🔹 All users settings
            cur.execute("""
                SELECT
                    uid,
                    code
                FROM acc_userssettings
            """)

        rows = cur.fetchall()

        data = []
        for r in rows:
            data.append({
                "uid": r[0],
                "code": r[1]
            })

        return JsonResponse({
            "status": "success",
            "count": len(data),
            "settings": data
        })

    except Exception as e:
        return JsonResponse(
            {"status": "error", "detail": str(e)},
            status=500
        )

    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


@jwt_required
@require_http_methods(["GET"])
def get_dine_categories(request):
    """
    GET /dine-categories/
    GET /dine-categories/?catagorycode=FD
    """

    catagorycode = request.GET.get("catagorycode")

    try:
        conn = get_connection()
        cur = conn.cursor()

        if catagorycode:
            # 🔹 Particular category
            cur.execute("""
                SELECT
                    catagorycode,
                    name
                FROM dine_catagory
                WHERE catagorycode = ?
            """, (catagorycode,))
        else:
            # 🔹 All categories
            cur.execute("""
                SELECT
                    catagorycode,
                    name
                FROM dine_catagory
            """)

        rows = cur.fetchall()

        data = []
        for r in rows:
            data.append({
                "catagorycode": r[0],
                "name": r[1]
            })

        return JsonResponse({
            "status": "success",
            "count": len(data),
            "categories": data
        })

    except Exception as e:
        return JsonResponse(
            {"status": "error", "detail": str(e)},
            status=500
        )

    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass
