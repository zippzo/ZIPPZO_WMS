import os
import hashlib
from datetime import datetime

from .database import SessionLocal
from .models import Employee


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def ensure_admin():
    password = os.getenv("ZIPPZO_ADMIN_PASSWORD")

    if not password:
        print("ZIPPZO_ADMIN_PASSWORD not set - admin bootstrap skipped.")
        return

    employee_id = os.getenv("ZIPPZO_ADMIN_ID", "ZLL000-01")
    full_name = os.getenv("ZIPPZO_ADMIN_NAME", "ILLA BHARGAVA")
    email = os.getenv("ZIPPZO_ADMIN_EMAIL", "BHARGAVAILLAZIPPZO@gmail.com")
    mobile = os.getenv("ZIPPZO_ADMIN_MOBILE", "8247362557")
    role = os.getenv("ZIPPZO_ADMIN_ROLE", "SUPER_ADMIN")

    reset_password = os.getenv(
        "ZIPPZO_ADMIN_RESET_PASSWORD", "false"
    ).lower() == "true"

    db = SessionLocal()
    now = datetime.now()

    try:
        employee = (
            db.query(Employee)
            .filter(Employee.employee_id == employee_id)
            .first()
        )

        if employee:
            employee.full_name = full_name
            employee.email = email
            employee.mobile = mobile
            employee.role = role
            employee.status = "ACTIVE"
            employee.email_verified = True
            employee.mobile_verified = True
            employee.updated_at = now

            if reset_password or not employee.password_hash:
                employee.password_hash = hash_password(password)

            db.commit()

            print(f"ZIPPZO ADMIN READY: {employee_id}")

        else:
            employee = Employee(
                employee_id=employee_id,
                full_name=full_name,
                email=email,
                mobile=mobile,
                password_hash=hash_password(password),
                role=role,
                status="ACTIVE",
                email_verified=True,
                mobile_verified=True,
                created_at=now,
                updated_at=now,
            )

            db.add(employee)
            db.commit()

            print(f"ZIPPZO ADMIN CREATED: {employee_id}")

    except Exception as e:
        db.rollback()
        print(f"ZIPPZO ADMIN ERROR: {e}")
        raise

    finally:
        db.close()
