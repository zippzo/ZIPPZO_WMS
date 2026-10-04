from .database import SessionLocal
from .models import Role

ROLES = [
    ("SUPER_ADMIN", "Super Admin", "Full access to the complete Zippzo platform"),
    ("ADMIN", "Admin", "Administrative access"),
    ("WAREHOUSE_MANAGER", "Warehouse Manager", "Warehouse and inventory management"),
    ("STORE_MANAGER", "Store Manager", "Dark store operations"),
    ("PICKER", "Picker", "Order picking operations"),
    ("PACKER", "Packer", "Order packing operations"),
    ("OPERATIONS", "Operations", "Operations and order management"),
    ("FINANCE", "Finance", "Financial and payment operations"),
    ("EMPLOYEE", "Employee", "Basic employee access"),
]

def ensure_roles():
    db = SessionLocal()
    try:
        for role_code, role_name, description in ROLES:
            role = db.query(Role).filter(Role.role_code == role_code).first()

            if role is None:
                db.add(
                    Role(
                        role_code=role_code,
                        role_name=role_name,
                        description=description,
                        active=True,
                    )
                )

        db.commit()
    finally:
        db.close()
