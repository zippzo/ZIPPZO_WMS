from pathlib import Path

p = Path("APP/main.py")
s = p.read_text(encoding="utf-8")

start_marker = "# =========================================================\n# ROLES\n# ========================================================="

# Locate all Roles sections.
positions = []
start = 0

while True:
    pos = s.find(start_marker, start)
    if pos == -1:
        break
    positions.append(pos)
    start = pos + 1

if len(positions) != 2:
    raise SystemExit(
        f"STOP: expected exactly 2 ROLES sections, found {len(positions)}"
    )

# The second Roles section continues through the duplicate
# Roles, Permissions, Role-Permissions and Audit Logs block.
second_start = positions[1]

putaway_marker = "# =========================================================\n# PUTAWAY\n# ========================================================="
putaway_pos = s.find(putaway_marker, second_start)

if putaway_pos == -1:
    raise SystemExit(
        "STOP: PUTAWAY section after duplicate Roles block was not found."
    )

s = s[:second_start] + s[putaway_pos:]

p.write_text(s, encoding="utf-8")

print("DUPLICATE ROLES/PERMISSIONS/AUDIT BLOCK REMOVED")
print("Database was NOT modified.")
