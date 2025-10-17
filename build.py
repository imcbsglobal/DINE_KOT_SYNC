# build.py — one-click packager for SyncService.exe
import os, sys, subprocess, shutil, venv, textwrap

# === Project knobs ============================================================
PROJECT_NAME = "SyncService"              # exe name
ENTRY_SCRIPT = "SyncService.py"           # your launcher

# (src, dst) → dst is the relative path inside the dist folder ('.' = root)
EXTRA_DATA = [
    ("config.json", "."),                 # ship config.json next to exe
    (".env", "."),                        # ship .env next to exe
    ("django_sync", "django_sync"),       # ship your Django package (templates/static inside)
    ("db.sqlite3", "."),                  # if you want to ship a starter DB (optional)
]

# Python packages that must be present in the build venv.
# We also install from requirements.txt if present (see pip_install()).
REQUIREMENTS = [
    "pyinstaller",
    "Django",
    "psutil",
    "pyjwt",
    "pyodbc",
    "python-dotenv",
    "djangorestframework",
    "djangorestframework-simplejwt",
    "django-cors-headers",
]

# === Paths ===================================================================
DIST_ROOT = f"{PROJECT_NAME.lower()}_dist"  # final drop folder
BUILD_DIR = "build"
DIST_DIR  = "dist"
VENV_DIR  = ".buildvenv"

# === Helpers =================================================================
def run(cmd, check=True):
    print(">", " ".join(cmd))
    return subprocess.run(cmd, check=check)

def ensure_venv():
    if not os.path.isdir(VENV_DIR):
        print("Creating build venv …")
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    py = os.path.join(VENV_DIR, "Scripts", "python.exe") if os.name == "nt" \
         else os.path.join(VENV_DIR, "bin", "python")
    return py

def pip_install(py, packages):
    print("Installing build requirements …")
    run([py, "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools"])
    # Install explicit essentials
    if packages:
        run([py, "-m", "pip", "install", *packages])
    # Also install from requirements.txt if present
    if os.path.exists("requirements.txt"):
        print("requirements.txt found — installing those too …")
        run([py, "-m", "pip", "install", "-r", "requirements.txt"])

def pyinstaller_add_data_arg(src, dst):
    # PyInstaller uses ';' on Windows and ':' on POSIX for --add-data
    sep = ";" if os.name == "nt" else ":"
    return f"{src}{sep}{dst}"

def copy_extra_to_dist(dist_root, extras):
    """Copy EXTRA_DATA (files or directories) to dist_root correctly."""
    for src, dst in extras:
        if not os.path.exists(src):
            continue
        if os.path.isdir(src):
            # Put directory under target path
            target = os.path.join(dist_root, dst if dst != "." else os.path.basename(src))
            # copy full folder (dirs_exist_ok requires Python 3.8+)
            shutil.copytree(src, target, dirs_exist_ok=True)
        else:
            target_dir = os.path.join(dist_root, dst) if dst != "." else dist_root
            os.makedirs(target_dir, exist_ok=True)
            shutil.copy2(src, os.path.join(target_dir, os.path.basename(src)))

# === Build ===================================================================
def build():
    py = ensure_venv()
    pip_install(py, REQUIREMENTS)

    # Clean old artifacts
    for p in (BUILD_DIR, DIST_DIR, DIST_ROOT, f"{PROJECT_NAME}.spec"):
        if os.path.exists(p):
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    os.remove(p)
                except Exception:
                    pass

    # Collect --add-data args for files/dirs that actually exist
    add_data_args = []
    for src, dst in EXTRA_DATA:
        if os.path.exists(src):
            add_data_args += ["--add-data", pyinstaller_add_data_arg(src, dst)]
        else:
            print(f"WARNING: {src} not found, skipping.")

    # Collect Django pieces to avoid missed imports
    collect_args = [
        "--collect-all", "django",
        "--collect-submodules", "django",
        "--collect-submodules", "django_sync",
    ]

    # Ensure Django can import settings at build time (some hooks call django.setup())
    env = os.environ.copy()
    env.setdefault("DJANGO_SETTINGS_MODULE", "django_sync.settings")

    cmd = [
        py, "-m", "PyInstaller",
        "--onefile",
        "--console",                    # switch to --windowed for GUI apps
        f"--name={PROJECT_NAME}",
        *collect_args,
        *add_data_args,
        ENTRY_SCRIPT,
    ]
    print("\nBuilding EXE …")
    run(cmd)

    # Make a friendly distribution folder
    os.makedirs(DIST_ROOT, exist_ok=True)
    exe_name = f"{PROJECT_NAME}.exe" if os.name == "nt" else PROJECT_NAME
    shutil.copy2(os.path.join(DIST_DIR, exe_name), os.path.join(DIST_ROOT, exe_name))

    # Copy extra files/directories properly (fixes PermissionError for folders)
    copy_extra_to_dist(DIST_ROOT, EXTRA_DATA)

    # Helper batch files (Windows)
    if os.name == "nt":
        with open(os.path.join(DIST_ROOT, f"{PROJECT_NAME}_console.bat"), "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(f"""\
            @echo off
            setlocal
            "%~dp0{exe_name}"
            pause
            """))
        with open(os.path.join(DIST_ROOT, f"{PROJECT_NAME}_background.bat"), "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(f"""\
            @echo off
            start "" "%~dp0{exe_name}"
            """))

    # Mini README
    with open(os.path.join(DIST_ROOT, "README.txt"), "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(f"""\
        {PROJECT_NAME} — portable build
        --------------------------------
        Double-click {exe_name} to start the service.

        This folder also contains:
        - config.json
        - .env
        - django_sync/ (your Django package, templates, static, etc.)
        Edit config.json or .env as needed; no rebuild required.
        """))

    print(f"\n✅ Done. Your portable package is in: {os.path.abspath(DIST_ROOT)}")

# === Main ====================================================================
if __name__ == "__main__":
    try:
        build()
    except subprocess.CalledProcessError as e:
        print("\n❌ Build failed with a subprocess error.")
        sys.exit(e.returncode)
    except Exception as e:
        print("\n❌ Build failed:", e)
        sys.exit(1)
