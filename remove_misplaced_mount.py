from pathlib import Path

p = Path("APP/main.py")
s = p.read_text(encoding="utf-8")

old = '''# =========================================================
# FINAL STATIC FRONTEND MOUNT
# =========================================================
#
# IMPORTANT:
# This MUST remain at the absolute bottom of this file.
# API routes must be registered before this catch-all mount.
#

if FRONTEND_DIR.exists():

    app.mount(
        "/",
        StaticFiles(
            directory=FRONTEND_DIR,
            html=True
        ),
        name="frontend"
    )

# =========================================================
# EMPLOYEES
# =========================================================
'''

if old not in s:
    raise SystemExit("STOP: misplaced frontend mount block was not found.")

new = '''# =========================================================
# EMPLOYEES
# =========================================================
'''

s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")

print("REMOVED MISPLACED FRONTEND MOUNT")
print("Database was NOT modified.")
