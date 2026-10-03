from pathlib import Path

p = Path("APP/main.py")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)

start = 8169
end = 8260

if len(lines) < end:
    raise SystemExit(f"STOP: main.py only has {len(lines)} lines.")

selected = "".join(lines[start:end])

required = [
    '@app.get("/api/roles")',
    '@app.get("/api/permissions")',
    '@app.get("/api/role-permissions")',
    '@app.get("/api/audit-logs")',
]

for item in required:
    if item not in selected:
        raise SystemExit(f"STOP: {item} was not found in target section.")

new_lines = lines[:start] + lines[end:]

p.write_text("".join(new_lines), encoding="utf-8")

print("DUPLICATE ACCESS ROUTES REMOVED")
print("Removed original lines 8170-8260.")
print("Database was NOT modified.")
