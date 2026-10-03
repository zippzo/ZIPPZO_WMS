from pathlib import Path
import ast
import sqlite3
import sys
import importlib
import traceback

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "APP"
FRONTEND = APP / "FRONTEND"
DB = ROOT / "zippzo_wms.db"

sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
WARN = 0

def result(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name}")
    if detail:
        print(f"       {detail}")

def warning(name, detail=""):
    global WARN
    WARN += 1
    print(f"[WARN] {name}")
    if detail:
        print(f"       {detail}")

print("=" * 75)
print("              ZIPPZO WMS COMPLETE LIVE TEST")
print("=" * 75)
print("Project:", ROOT)
print()

# ---------------------------------------------------------
# 1. PYTHON SYNTAX
# ---------------------------------------------------------
print("[1] PYTHON SYNTAX TEST")

py_files = [
    p for p in APP.rglob("*.py")
    if "__pycache__" not in str(p)
]

syntax_fail = 0

for p in py_files:
    try:
        ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
    except Exception as e:
        syntax_fail += 1
        print("       FAIL:", p, e)

result(
    "Python syntax",
    syntax_fail == 0,
    f"{len(py_files) - syntax_fail}/{len(py_files)} files valid"
)

print()

# ---------------------------------------------------------
# 2. DATABASE
# ---------------------------------------------------------
print("[2] DATABASE TEST")

if DB.exists():
    result("Database file", True, f"{DB.stat().st_size:,} bytes")

    try:
        conn = sqlite3.connect(str(DB))
        conn.execute("PRAGMA integrity_check")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

        result("SQLite connection", True)
        result("Database integrity", integrity == "ok", integrity)
        result("Database tables", len(tables) > 0, f"{len(tables)} tables")

        conn.close()
    except Exception as e:
        result("Database operations", False, str(e))
else:
    result("Database file", False, "zippzo_wms.db not found")

print()

# ---------------------------------------------------------
# 3. CORE IMPORTS
# ---------------------------------------------------------
print("[3] BACKEND IMPORT TEST")

modules = [
    "APP.database",
    "APP.models",
    "APP.models_v4",
    "APP.v4_permissions",
    "APP.workflow_v4",
    "APP.workflow_v4_router",
    "APP.batch_backend_v2_corrected",
    "APP.batch_setup_v2",
    "APP.backend_setup_v4",
    "APP.main",
]

for module in modules:
    try:
        importlib.import_module(module)
        result(f"Import {module}", True)
    except Exception as e:
        result(f"Import {module}", False, str(e))

print()

# ---------------------------------------------------------
# 4. FASTAPI APP
# ---------------------------------------------------------
print("[4] FASTAPI APPLICATION TEST")

try:
    from APP.main import app

    result("FastAPI app import", True)

    routes = list(app.routes)
    result("Routes registered", len(routes) > 0, f"{len(routes)} routes")

    try:
        openapi = app.openapi()
        paths = openapi.get("paths", {})
        result("OpenAPI generation", True, f"{len(paths)} API paths")
    except Exception as e:
        result("OpenAPI generation", False, str(e))

except Exception as e:
    app = None
    result("FastAPI app import", False, str(e))

print()

# ---------------------------------------------------------
# 5. ROUTE INVENTORY
# ---------------------------------------------------------
print("[5] API ROUTE INVENTORY")

if app:
    methods = {}

    for route in app.routes:
        if hasattr(route, "methods"):
            for method in route.methods:
                methods[method] = methods.get(method, 0) + 1

    for method in sorted(methods):
        print(f"       {method:<8} {methods[method]}")

    result("API route inventory", len(app.routes) > 0)

print()

# ---------------------------------------------------------
# 6. RBAC
# ---------------------------------------------------------
print("[6] RBAC TEST")

try:
    from APP.v4_permissions import get_role_access

    access = get_role_access("SUPER_ADMIN")
    permissions = set(access.get("permissions", []))

    required = {
        "BATCH_VIEW",
        "BATCH_CREATE",
        "BATCH_UPLOAD",
        "BATCH_CANCEL",
    }

    missing = required - permissions

    result(
        "SUPER_ADMIN RBAC",
        not missing,
        f"{len(permissions)} permissions"
    )

    result(
        "Batch permissions",
        not missing,
        "Missing: " + ", ".join(sorted(missing)) if missing else "All required permissions present"
    )

except Exception as e:
    result("RBAC test", False, str(e))

print()

# ---------------------------------------------------------
# 7. DATABASE ORM
# ---------------------------------------------------------
print("[7] ORM TEST")

try:
    from APP.database import SessionLocal

    db = SessionLocal()

    try:
        from sqlalchemy import text; db.execute(text("SELECT 1"))
        result("SQLAlchemy session", True)

        try:
            from APP.models import RolePermission
            rows = db.query(RolePermission).count()
            result("RolePermission ORM", True, f"{rows} rows")
        except Exception as e:
            warning("RolePermission ORM", str(e))

    finally:
        db.close()

except Exception as e:
    result("SQLAlchemy session", False, str(e))

print()

# ---------------------------------------------------------
# 8. LIVE FASTAPI TEST CLIENT
# ---------------------------------------------------------
print("[8] LIVE API TEST CLIENT")

if app:
    try:
        from fastapi.testclient import TestClient

        client = TestClient(app)

        response = client.get("/openapi.json")

        result(
            "GET /openapi.json",
            response.status_code == 200,
            f"HTTP {response.status_code}"
        )

        response = client.get("/docs")

        result(
            "GET /docs",
            response.status_code == 200,
            f"HTTP {response.status_code}"
        )

        # Test every registered GET route.
        tested = 0
        server_errors = 0

        for route in app.routes:
            if not hasattr(route, "methods"):
                continue

            if "GET" not in route.methods:
                continue

            path = getattr(route, "path", "")

            # Skip parameterized routes because fake IDs can cause
            # misleading failures.
            if "{" in path:
                continue

            if path in ["/openapi.json", "/docs", "/redoc"]:
                continue

            try:
                r = client.get(path)
                tested += 1

                if r.status_code >= 500:
                    server_errors += 1
                    print(
                        f"       SERVER ERROR: GET {path} -> {r.status_code}"
                    )

            except Exception as e:
                server_errors += 1
                print(f"       EXCEPTION: GET {path} -> {e}")

        result(
            "GET endpoint smoke test",
            server_errors == 0,
            f"{tested} endpoints tested; {server_errors} server errors"
        )

    except Exception as e:
        result("FastAPI TestClient", False, str(e))
else:
    result("FastAPI TestClient", False, "FastAPI app unavailable")

print()

# ---------------------------------------------------------
# 9. BATCH ROUTER
# ---------------------------------------------------------
print("[9] BATCH MODULE TEST")

batch_file = APP / "batch_backend_v2_corrected.py"

if batch_file.exists():
    result("Batch backend file", True)

    text = batch_file.read_text(
        encoding="utf-8",
        errors="ignore"
    )

    checks = {
        "BATCH_VIEW": "BATCH_VIEW" in text,
        "BATCH_CREATE": "BATCH_CREATE" in text,
        "BATCH_UPLOAD": "BATCH_UPLOAD" in text,
        "BATCH_CANCEL": "BATCH_CANCEL" in text,
    }

    for name, ok in checks.items():
        result(f"Batch permission {name}", ok)
else:
    result("Batch backend file", False)

print()

# ---------------------------------------------------------
# 10. FRONTEND FILE TEST
# ---------------------------------------------------------
print("[10] FRONTEND TEST")

required_screens = [
    "index.html",
    "warehouse-dashboard.html",
    "inventory.html",
    "orders.html",
    "products.html",
    "suppliers.html",
    "employees.html",
    "attendance.html",
    "grn.html",
    "putaway.html",
    "picking.html",
    "sorting.html",
    "dispatch.html",
    "riders.html",
    "bins.html",
    "locations.html",
    "purchase-orders.html",
    "stock-movements.html",
    "access-control.html",
    "audit-logs.html",
]

missing = []

for screen in required_screens:
    if not (FRONTEND / screen).exists():
        missing.append(screen)

result(
    "Required frontend screens",
    not missing,
    f"{len(required_screens) - len(missing)}/{len(required_screens)} present"
)

if missing:
    for item in missing:
        print("       Missing:", item)

print()

# ---------------------------------------------------------
# 11. FRONTEND JAVASCRIPT/CSS
# ---------------------------------------------------------
print("[11] FRONTEND ASSET TEST")

css = list(FRONTEND.glob("*.css"))
js = list(FRONTEND.glob("*.js"))

result("CSS assets", len(css) > 0, f"{len(css)} files")
result("JavaScript assets", len(js) > 0, f"{len(js)} files")

print()

# ---------------------------------------------------------
# 12. SECURITY ROUTER
# ---------------------------------------------------------
print("[12] SECURITY TEST")

main_text = (APP / "main.py").read_text(
    encoding="utf-8",
    errors="ignore"
)

result(
    "Secure router registered",
    "secure_router" in main_text
)

result(
    "Batch router registered",
    "batch_router" in main_text
)

result(
    "Authentication module",
    (APP / "setup_auth.py").exists()
)

print()

# ---------------------------------------------------------
# 13. REQUIREMENTS
# ---------------------------------------------------------
print("[13] DEPENDENCY TEST")

requirements = APP / "requirements.txt"

if requirements.exists():
    lines = [
        x.strip()
        for x in requirements.read_text(
            encoding="utf-8",
            errors="ignore"
        ).splitlines()
        if x.strip() and not x.startswith("#")
    ]

    result(
        "requirements.txt",
        True,
        f"{len(lines)} dependencies listed"
    )
else:
    result("requirements.txt", False)

print()

# ---------------------------------------------------------
# 14. TEST FILES
# ---------------------------------------------------------
print("[14] AUTOMATED TEST FILES")

test_files = list(ROOT.rglob("test_*.py")) + list(
    ROOT.rglob("*_test.py")
)

test_files = [
    p for p in test_files
    if "__pycache__" not in str(p)
    and ".venv" not in str(p)
]

if test_files:
    result(
        "Automated test files",
        True,
        f"{len(test_files)} files"
    )
    for p in test_files:
        print("       ", p.relative_to(ROOT))
else:
    warning(
        "Automated test files",
        "No permanent pytest test files yet"
    )

print()

# ---------------------------------------------------------
# FINAL
# ---------------------------------------------------------
print("=" * 75)
print("                         TEST SUMMARY")
print("=" * 75)

TOTAL = PASS + FAIL

print("PASS :", PASS)
print("FAIL :", FAIL)
print("WARN :", WARN)
print("TESTS:", TOTAL)

if TOTAL:
    test_percent = (PASS / TOTAL) * 100
else:
    test_percent = 0

print()
print(f"LIVE TEST PASS RATE : {test_percent:.1f}%")

if FAIL == 0:
    print("RESULT              : PASS")
elif FAIL <= 3:
    print("RESULT              : NEEDS FIXES")
else:
    print("RESULT              : FAILED")

print("=" * 75)
print()
print("NOTE:")
print("This test runner performs live application smoke testing,")
print("but it does not replace load testing, penetration testing,")
print("real browser workflow testing, or production deployment testing.")

