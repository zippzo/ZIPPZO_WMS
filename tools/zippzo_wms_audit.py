from pathlib import Path
import ast
import sqlite3

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "APP"
FRONTEND = APP / "FRONTEND"
DB = ROOT / "zippzo_wms.db"

print("=" * 70)
print("        ZIPPZO WMS - COMPLETE PROJECT AUDIT")
print("=" * 70)
print("PROJECT:", ROOT)
print()

def exists(path):
    return path.exists()

def count_files(folder, pattern):
    if not folder.exists():
        return 0
    return len(list(folder.rglob(pattern)))

def read_file(path):
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except:
        return ""

# --------------------------------------------------
# 1. FRONTEND
# --------------------------------------------------
html_count = count_files(FRONTEND, "*.html")
css_count = count_files(FRONTEND, "*.css")
js_count = count_files(FRONTEND, "*.js")

frontend_score = 0
frontend_score += 40 if html_count >= 20 else int(html_count / 20 * 40)
frontend_score += 30 if css_count >= 2 else int(css_count / 2 * 30)
frontend_score += 30 if js_count >= 2 else int(js_count / 2 * 30)
frontend_score = min(frontend_score, 100)

print("[1] FRONTEND")
print("    HTML files :", html_count)
print("    CSS files  :", css_count)
print("    JS files   :", js_count)
print("    Score      :", frontend_score, "%")
print()

# --------------------------------------------------
# 2. BACKEND
# --------------------------------------------------
py_files = []
if APP.exists():
    py_files = [
        p for p in APP.rglob("*.py")
        if "__pycache__" not in str(p)
        and "BACKUP" not in p.name.upper()
    ]

syntax_ok = 0
syntax_fail = []

for p in py_files:
    try:
        ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        syntax_ok += 1
    except Exception as e:
        syntax_fail.append((p.name, str(e)))

backend_score = 100 if py_files and not syntax_fail else (
    int((syntax_ok / len(py_files)) * 100) if py_files else 0
)

print("[2] BACKEND")
print("    Python files:", len(py_files))
print("    Syntax OK   :", syntax_ok)
print("    Syntax FAIL :", len(syntax_fail))
print("    Score       :", backend_score, "%")

if syntax_fail:
    print("    Failed files:")
    for name, error in syntax_fail[:10]:
        print("      -", name, ":", error)

print()

# --------------------------------------------------
# 3. ACTIVE MAIN ROUTER
# --------------------------------------------------
main_text = read_file(APP / "main.py")

print("[3] ACTIVE ROUTER")
if "batch_backend_v2_corrected" in main_text:
    print("    Batch router : batch_backend_v2_corrected.py")
    batch_router_ok = True
elif "batch_backend_v2" in main_text:
    print("    Batch router : batch_backend_v2.py")
    batch_router_ok = True
else:
    print("    Batch router : NOT DETECTED")
    batch_router_ok = False

if "include_router" in main_text:
    print("    FastAPI routers detected : YES")
    router_ok = True
else:
    print("    FastAPI routers detected : NO")
    router_ok = False

router_score = 100 if batch_router_ok and router_ok else 50
print("    Score :", router_score, "%")
print()

# --------------------------------------------------
# 4. RBAC
# --------------------------------------------------
permissions_file = APP / "v4_permissions.py"
perm_text = read_file(permissions_file)

required_permissions = [
    "BATCH_VIEW",
    "BATCH_CREATE",
    "BATCH_UPLOAD",
    "BATCH_CANCEL",
]

print("[4] RBAC / PERMISSIONS")

rbac_score = 0

if permissions_file.exists():
    print("    v4_permissions.py : FOUND")
    rbac_score += 30
else:
    print("    v4_permissions.py : MISSING")

if "ROLE_PERMISSION_MAP" in perm_text:
    print("    ROLE_PERMISSION_MAP : FOUND")
    rbac_score += 20

if "normalize_role" in perm_text:
    print("    normalize_role      : FOUND")
    rbac_score += 20

try:
    import sys
    sys.path.insert(0, str(ROOT))
    from APP.v4_permissions import get_role_access

    result = get_role_access("SUPER_ADMIN")
    perms = set(result.get("permissions", []))

    print("    SUPER_ADMIN permissions:", len(perms))

    missing = [p for p in required_permissions if p not in perms]

    if not missing:
        print("    Batch permissions      : PASS")
        rbac_score += 30
    else:
        print("    Missing permissions    :", ", ".join(missing))
except Exception as e:
    print("    RBAC runtime test      : ERROR")
    print("    Error                  :", e)

print("    Score :", min(rbac_score, 100), "%")
print()

# --------------------------------------------------
# 5. DATABASE
# --------------------------------------------------
print("[5] DATABASE")

db_score = 0

if DB.exists():
    print("    Database : FOUND")
    print("    Size     :", DB.stat().st_size, "bytes")
    db_score += 40

    try:
        conn = sqlite3.connect(str(DB))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()

        print("    Tables   :", len(tables))

        if tables:
            db_score += 60
            print("    Database connection : PASS")
        else:
            print("    Database connection : EMPTY")
    except Exception as e:
        print("    Database connection : FAIL")
        print("    Error :", e)
else:
    print("    Database : NOT FOUND")

print("    Score :", min(db_score, 100), "%")
print()

# --------------------------------------------------
# 6. WMS MODULES
# --------------------------------------------------
modules = {
    "Authentication": ["setup_auth.py", "create_admin.py"],
    "Batch": ["batch_backend_v2_corrected.py", "batch_setup_v2.py"],
    "Workflow": ["workflow_v4.py", "workflow_v4_router.py"],
    "Database": ["database.py", "models.py"],
    "Permissions": ["v4_permissions.py"],
    "Backend": ["main.py"],
}

print("[6] WMS MODULES")

module_pass = 0

for module, files in modules.items():
    found = any((APP / f).exists() for f in files)

    if found:
        print("    PASS  ", module)
        module_pass += 1
    else:
        print("    FAIL  ", module)

module_score = int(module_pass / len(modules) * 100)
print("    Score :", module_score, "%")
print()

# --------------------------------------------------
# 7. FRONTEND BUSINESS SCREENS
# --------------------------------------------------
business_screens = [
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

print("[7] BUSINESS SCREENS")

screen_pass = 0

for screen in business_screens:
    if (FRONTEND / screen).exists():
        screen_pass += 1
    else:
        print("    MISSING:", screen)

screen_score = int(screen_pass / len(business_screens) * 100)

print("    Found :", screen_pass, "/", len(business_screens))
print("    Score :", screen_score, "%")
print()

# --------------------------------------------------
# 8. TESTING / QUALITY
# --------------------------------------------------
print("[8] TESTING / QUALITY")

test_files = list(ROOT.rglob("test_*.py")) + list(ROOT.rglob("*_test.py"))
test_files = [
    p for p in test_files
    if ".venv" not in str(p)
    and "__pycache__" not in str(p)
]

print("    Test files :", len(test_files))

if test_files:
    testing_score = 70
else:
    testing_score = 20
    print("    WARNING: No dedicated automated test files detected.")

print("    Score :", testing_score, "%")
print()

# --------------------------------------------------
# 9. SECURITY / CONFIG
# --------------------------------------------------
print("[9] SECURITY / CONFIG")

security_score = 0

if permissions_file.exists():
    security_score += 30

if (APP / "setup_auth.py").exists():
    security_score += 20

if (APP / "create_admin.py").exists():
    security_score += 20

if "secure_router" in main_text:
    security_score += 30

print("    Score :", security_score, "%")
print()

# --------------------------------------------------
# 10. DOCUMENTATION / DEPLOYMENT
# --------------------------------------------------
print("[10] DOCUMENTATION / DEPLOYMENT")

docs = list(ROOT.glob("*.md")) + list(ROOT.glob("README*"))
requirements = APP / "requirements.txt"

deployment_score = 0

if docs:
    deployment_score += 40

if requirements.exists():
    deployment_score += 30

if (ROOT / "Dockerfile").exists() or (ROOT / "docker-compose.yml").exists():
    deployment_score += 30

print("    Documentation files:", len(docs))
print("    requirements.txt   :", "FOUND" if requirements.exists() else "MISSING")
print("    Score              :", deployment_score, "%")
print()

# --------------------------------------------------
# OVERALL
# --------------------------------------------------
scores = {
    "Frontend": frontend_score,
    "Backend": backend_score,
    "Router": router_score,
    "RBAC": min(rbac_score, 100),
    "Database": min(db_score, 100),
    "WMS Modules": module_score,
    "Business Screens": screen_score,
    "Testing": testing_score,
    "Security": security_score,
    "Deployment/Docs": deployment_score,
}

weights = {
    "Frontend": 15,
    "Backend": 20,
    "Router": 10,
    "RBAC": 10,
    "Database": 10,
    "WMS Modules": 10,
    "Business Screens": 10,
    "Testing": 5,
    "Security": 5,
    "Deployment/Docs": 5,
}

overall = sum(scores[k] * weights[k] for k in scores) / sum(weights.values())

print("=" * 70)
print("                    OVERALL ZIPPZO WMS")
print("=" * 70)

for name, score in scores.items():
    print(f"{name:<22} {score:>3}%")

print("-" * 70)
print(f"OVERALL PROJECT STATUS : {overall:.1f}%")
print("-" * 70)

if overall >= 90:
    status = "PRODUCTION READY CANDIDATE"
elif overall >= 75:
    status = "ADVANCED / NEAR PRODUCTION"
elif overall >= 50:
    status = "DEVELOPMENT - MAJOR WORK REMAINS"
else:
    status = "EARLY DEVELOPMENT"

print("STATUS:", status)
print("=" * 70)
print()
print("NOTE: This is a static/structural audit.")
print("It does not replace live browser/API/load/security testing.")
