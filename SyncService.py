#!/usr/bin/env python3
"""
SyncService — freeze-aware Django launcher

Usage style:
- Build once (PyInstaller).
- After that, only edit the external config.json and .env in syncservice_dist.
- On each run, .env values override config.json.
- DB DSN = DB_DSN in .env (if set) else "dsn" in config.json.
- DNS hostname = DNS_NAME in .env (optional).
- Always auto-select IP and run migrations.
"""

import json
import os
import socket
import sys
import time
from typing import List, Tuple

# ----------------------------- helpers ---------------------------------------
def _exe_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _strip_comment(s: str) -> str:
    if not isinstance(s, str):
        return s
    return s.split("#", 1)[0].strip()

# ----------------------------- config ----------------------------------------
def load_config(exe_dir: str) -> dict:
    cfg_path = os.path.join(exe_dir, "config.json")
    cfg = {
        "ip": "auto",
        "port": 8000,
        "dsn": None,
        "settings": "django_sync.settings",
        "env_file": ".env"
    }
    if os.path.isfile(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            user = json.load(f) or {}
        cfg.update(user)
    if cfg.get("dsn"):
        cfg["dsn"] = _strip_comment(cfg["dsn"])
    return cfg

def load_env(exe_dir: str, filename: str) -> dict:
    path = os.path.join(exe_dir, filename)
    loaded = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), _strip_comment(v.strip())
                os.environ[k] = v   # overwrite each run
                loaded[k] = v
    return loaded

# ----------------------------- IP auto-pick ----------------------------------
def ipv4_candidates() -> list[str]:
    cands = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        cands.append(s.getsockname()[0])
    except Exception:
        pass
    finally:
        try: s.close()
        except: pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and ip != "127.0.0.1":
                cands.append(ip)
    except Exception:
        pass
    seen, uniq = set(), []
    for ip in cands:
        if ip not in seen:
            seen.add(ip)
            uniq.append(ip)
    return uniq

def select_bind_ip(port: int) -> Tuple[str, list[str]]:
    tried = []
    for ip in ipv4_candidates():
        tried.append(ip)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((ip, port))
            s.close()
            return ip, tried
        except Exception:
            pass
    tried.append("0.0.0.0")
    return "0.0.0.0", tried

# ----------------------------- Django setup ----------------------------------
def bootstrap_django(settings: str, proj_root: str):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings)
    if proj_root not in sys.path:
        sys.path.insert(0, proj_root)
    import django
    django.setup()

def apply_migrations():
    from django.core.management import call_command
    call_command("migrate", interactive=False, verbosity=1)

def run_server(bind_ip: str, port: int):
    from django.core.management import call_command
    call_command("runserver", f"{bind_ip}:{port}", use_reloader=False)

# ----------------------------- Main ------------------------------------------
def main():
    exe_dir = _exe_dir()
    cfg = load_config(exe_dir)
    env_loaded = load_env(exe_dir, cfg.get("env_file", ".env"))

    # DB DSN: .env overrides config.json
    dsn = os.environ.get("DB_DSN", cfg.get("dsn") or "")
    os.environ["DB_DSN"] = _strip_comment(dsn)
    os.environ["DB_UID"] = os.getenv("DB_UID", "dba")
    os.environ["DB_PWD"] = os.getenv("DB_PWD", "(*$^)")

    proj_root = exe_dir
    bootstrap_django(cfg.get("settings", "django_sync.settings"), proj_root)

    port = int(cfg.get("port", 8000))
    bind_ip, tried = select_bind_ip(port)

    dns_name = _strip_comment(os.getenv("DNS_NAME", "")) or None

    # Banner
    print(f"🚀 Config: {os.path.join(exe_dir, 'config.json')}", flush=True)
    print(f"🧪 .env loaded: {env_loaded}", flush=True)
    if dns_name:
        print(f"🌍 DNS_NAME: {dns_name}")
        print(f"🔗 http://{dns_name}:{port}/")
    print(f"🔎 IP selection: tried={tried}, chosen={bind_ip}")
    print("⚙️ Applying migrations...")
    apply_migrations()

    import django
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{now}")
    print(f"Django {django.get_version()}, settings '{cfg.get('settings')}'")
    print(f"Starting at http://{bind_ip}:{port}/")
    if dns_name:
        print(f"(Also via http://{dns_name}:{port}/)")
    print("Quit with CTRL-BREAK.")

    run_server(bind_ip, port)

if __name__ == "__main__":
    main()
