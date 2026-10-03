from pathlib import Path

p = Path("APP/main.py")
s = p.read_text(encoding="utf-8")

block = '''# =========================================================
# EMPLOYEES
# =========================================================

@app.get("/api/employees")
def get_employees(
    db: Session = Depends(get_db)
):

    employees = (
        db.query(Employee)
        .order_by(Employee.id.desc())
        .all()
    )

    return [
        {
            "id": employee.id,
            "employee_id": employee.employee_id,
            "full_name": employee.full_name,
            "email": employee.email,
            "mobile": employee.mobile,
            "role": employee.role,
            "department": employee.department,
            "location_id": employee.location_id,
            "status": employee.status,
            "email_verified": employee.email_verified,
            "mobile_verified": employee.mobile_verified,
            "last_login": employee.last_login,
            "created_at": employee.created_at,
            "updated_at": employee.updated_at,
        }
        for employee in employees
    ]
# =========================================================
# PUTAWAY
# =========================================================
'''

if s.count(block) != 1:
    raise SystemExit(
        f"STOP: expected exactly one duplicate Employee block, found {s.count(block)}"
    )

s = s.replace(block, "# =========================================================\n# PUTAWAY\n# =========================================================\n", 1)

p.write_text(s, encoding="utf-8")

print("DUPLICATE EMPLOYEE ROUTE REMOVED")
print("Database was NOT modified.")
