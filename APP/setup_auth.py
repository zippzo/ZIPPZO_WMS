import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "zippzo_wms.db"


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    return any(row[1] == column_name for row in columns)


def create_tables(connection):
    cursor = connection.cursor()

    # =====================================================
    # EMPLOYEES
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY,
            employee_id VARCHAR UNIQUE NOT NULL,
            full_name VARCHAR NOT NULL,
            email VARCHAR UNIQUE NOT NULL,
            mobile VARCHAR UNIQUE NOT NULL,
            password_hash VARCHAR,
            role VARCHAR DEFAULT 'EMPLOYEE',
            department VARCHAR,
            location_id INTEGER,
            status VARCHAR DEFAULT 'ACTIVE',
            email_verified BOOLEAN DEFAULT 0,
            mobile_verified BOOLEAN DEFAULT 0,
            last_login VARCHAR,
            created_at VARCHAR NOT NULL,
            updated_at VARCHAR NOT NULL
        )
    """)

    # =====================================================
    # ROLES
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY,
            role_code VARCHAR UNIQUE NOT NULL,
            role_name VARCHAR NOT NULL,
            description VARCHAR,
            active BOOLEAN DEFAULT 1
        )
    """)

    # =====================================================
    # PERMISSIONS
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS permissions (
            id INTEGER PRIMARY KEY,
            permission_code VARCHAR UNIQUE NOT NULL,
            permission_name VARCHAR NOT NULL,
            module VARCHAR NOT NULL,
            active BOOLEAN DEFAULT 1
        )
    """)

    # =====================================================
    # ROLE PERMISSIONS
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS role_permissions (
            id INTEGER PRIMARY KEY,
            role_code VARCHAR NOT NULL,
            permission_code VARCHAR NOT NULL,
            allowed BOOLEAN DEFAULT 1
        )
    """)

    # =====================================================
    # OTP
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS otp_verifications (
            id INTEGER PRIMARY KEY,
            employee_id INTEGER,
            identifier VARCHAR NOT NULL,
            identifier_type VARCHAR NOT NULL,
            otp_code VARCHAR NOT NULL,
            purpose VARCHAR DEFAULT 'LOGIN',
            expires_at VARCHAR NOT NULL,
            verified BOOLEAN DEFAULT 0,
            attempts INTEGER DEFAULT 0,
            created_at VARCHAR NOT NULL
        )
    """)

    # =====================================================
    # LOGIN SESSIONS
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS login_sessions (
            id INTEGER PRIMARY KEY,
            employee_id INTEGER NOT NULL,
            session_token VARCHAR UNIQUE NOT NULL,
            login_method VARCHAR NOT NULL,
            device_name VARCHAR,
            ip_address VARCHAR,
            expires_at VARCHAR NOT NULL,
            revoked BOOLEAN DEFAULT 0,
            created_at VARCHAR NOT NULL
        )
    """)

    # =====================================================
    # AUDIT LOG
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY,
            employee_id INTEGER,
            employee_name VARCHAR,
            action VARCHAR NOT NULL,
            module VARCHAR NOT NULL,
            reference_id VARCHAR,
            description VARCHAR,
            ip_address VARCHAR,
            created_at VARCHAR NOT NULL
        )
    """)

    connection.commit()


def insert_default_roles(connection):
    cursor = connection.cursor()

    roles = [
        (
            "SUPER_ADMIN",
            "Super Admin",
            "Full access to the complete Zippzo platform"
        ),
        (
            "ADMIN",
            "Admin",
            "Administrative access"
        ),
        (
            "WAREHOUSE_MANAGER",
            "Warehouse Manager",
            "Warehouse and inventory management"
        ),
        (
            "STORE_MANAGER",
            "Store Manager",
            "Dark store operations"
        ),
        (
            "PICKER",
            "Picker",
            "Order picking operations"
        ),
        (
            "PACKER",
            "Packer",
            "Order packing operations"
        ),
        (
            "OPERATIONS",
            "Operations",
            "Operations and order management"
        ),
        (
            "FINANCE",
            "Finance",
            "Financial and payment operations"
        ),
        (
            "EMPLOYEE",
            "Employee",
            "Basic employee access"
        )
    ]

    for role_code, role_name, description in roles:
        cursor.execute("""
            INSERT OR IGNORE INTO roles
            (
                role_code,
                role_name,
                description,
                active
            )
            VALUES (?, ?, ?, 1)
        """, (
            role_code,
            role_name,
            description
        ))

    connection.commit()


def insert_permissions(connection):
    cursor = connection.cursor()

    permissions = [
        ("DASHBOARD_VIEW", "View Dashboard", "DASHBOARD"),

        ("PRODUCT_VIEW", "View Products", "PRODUCTS"),
        ("PRODUCT_CREATE", "Create Products", "PRODUCTS"),
        ("PRODUCT_EDIT", "Edit Products", "PRODUCTS"),
        ("PRODUCT_DELETE", "Delete Products", "PRODUCTS"),

        ("LOCATION_VIEW", "View Locations", "LOCATIONS"),
        ("LOCATION_CREATE", "Create Locations", "LOCATIONS"),
        ("LOCATION_EDIT", "Edit Locations", "LOCATIONS"),

        ("INVENTORY_VIEW", "View Inventory", "INVENTORY"),
        ("INVENTORY_EDIT", "Edit Inventory", "INVENTORY"),
        ("INVENTORY_TRANSFER", "Transfer Stock", "INVENTORY"),
        ("INVENTORY_ADJUST", "Adjust Stock", "INVENTORY"),

        ("BIN_VIEW", "View Bins", "BINS"),
        ("BIN_CREATE", "Create Bins", "BINS"),
        ("BIN_EDIT", "Edit Bins", "BINS"),

        ("ORDER_VIEW", "View Orders", "ORDERS"),
        ("ORDER_CREATE", "Create Orders", "ORDERS"),
        ("ORDER_EDIT", "Edit Orders", "ORDERS"),
        ("ORDER_CANCEL", "Cancel Orders", "ORDERS"),

        ("PICKING_VIEW", "View Picking Tasks", "PICKING"),
        ("PICKING_EXECUTE", "Execute Picking", "PICKING"),

        ("PACKING_VIEW", "View Packing Tasks", "PACKING"),
        ("PACKING_EXECUTE", "Execute Packing", "PACKING"),

        ("RIDER_VIEW", "View Riders", "RIDERS"),
        ("RIDER_ASSIGN", "Assign Riders", "RIDERS"),
        ("RIDER_EDIT", "Edit Riders", "RIDERS"),

        ("SUPPLIER_VIEW", "View Suppliers", "SUPPLIERS"),
        ("SUPPLIER_CREATE", "Create Suppliers", "SUPPLIERS"),
        ("SUPPLIER_EDIT", "Edit Suppliers", "SUPPLIERS"),

        ("REPORT_VIEW", "View Reports", "REPORTS"),
        ("REPORT_EXPORT", "Export Reports", "REPORTS"),

        ("EMPLOYEE_VIEW", "View Employees", "EMPLOYEES"),
        ("EMPLOYEE_CREATE", "Create Employees", "EMPLOYEES"),
        ("EMPLOYEE_EDIT", "Edit Employees", "EMPLOYEES"),
        ("EMPLOYEE_DISABLE", "Disable Employees", "EMPLOYEES"),

        ("ROLE_VIEW", "View Roles", "SECURITY"),
        ("ROLE_EDIT", "Edit Roles", "SECURITY"),

        ("AUDIT_VIEW", "View Audit Logs", "SECURITY")
    ]

    for permission_code, permission_name, module in permissions:
        cursor.execute("""
            INSERT OR IGNORE INTO permissions
            (
                permission_code,
                permission_name,
                module,
                active
            )
            VALUES (?, ?, ?, 1)
        """, (
            permission_code,
            permission_name,
            module
        ))

    connection.commit()


def setup_role_permissions(connection):
    cursor = connection.cursor()

    cursor.execute("SELECT role_code FROM roles")
    roles = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT permission_code FROM permissions")
    permissions = [row[0] for row in cursor.fetchall()]

    for role_code in roles:

        if role_code == "SUPER_ADMIN":
            allowed_permissions = permissions

        elif role_code == "ADMIN":
            allowed_permissions = [
                p for p in permissions
                if not p.startswith("ROLE_")
            ]

        elif role_code == "WAREHOUSE_MANAGER":
            allowed_permissions = [
                "DASHBOARD_VIEW",
                "PRODUCT_VIEW",
                "PRODUCT_CREATE",
                "PRODUCT_EDIT",
                "LOCATION_VIEW",
                "INVENTORY_VIEW",
                "INVENTORY_EDIT",
                "INVENTORY_TRANSFER",
                "INVENTORY_ADJUST",
                "BIN_VIEW",
                "BIN_CREATE",
                "BIN_EDIT",
                "SUPPLIER_VIEW",
                "SUPPLIER_CREATE",
                "SUPPLIER_EDIT",
                "ORDER_VIEW",
                "PICKING_VIEW",
                "PACKING_VIEW",
                "REPORT_VIEW",
                "REPORT_EXPORT"
            ]

        elif role_code == "STORE_MANAGER":
            allowed_permissions = [
                "DASHBOARD_VIEW",
                "PRODUCT_VIEW",
                "LOCATION_VIEW",
                "INVENTORY_VIEW",
                "INVENTORY_EDIT",
                "BIN_VIEW",
                "ORDER_VIEW",
                "ORDER_EDIT",
                "PICKING_VIEW",
                "PACKING_VIEW",
                "RIDER_VIEW",
                "RIDER_ASSIGN",
                "REPORT_VIEW"
            ]

        elif role_code == "PICKER":
            allowed_permissions = [
                "DASHBOARD_VIEW",
                "ORDER_VIEW",
                "PICKING_VIEW",
                "PICKING_EXECUTE",
                "INVENTORY_VIEW"
            ]

        elif role_code == "PACKER":
            allowed_permissions = [
                "DASHBOARD_VIEW",
                "ORDER_VIEW",
                "PACKING_VIEW",
                "PACKING_EXECUTE",
                "INVENTORY_VIEW"
            ]

        elif role_code == "OPERATIONS":
            allowed_permissions = [
                "DASHBOARD_VIEW",
                "PRODUCT_VIEW",
                "LOCATION_VIEW",
                "INVENTORY_VIEW",
                "ORDER_VIEW",
                "ORDER_CREATE",
                "ORDER_EDIT",
                "ORDER_CANCEL",
                "PICKING_VIEW",
                "PACKING_VIEW",
                "RIDER_VIEW",
                "RIDER_ASSIGN",
                "REPORT_VIEW"
            ]

        elif role_code == "FINANCE":
            allowed_permissions = [
                "DASHBOARD_VIEW",
                "ORDER_VIEW",
                "REPORT_VIEW",
                "REPORT_EXPORT"
            ]

        else:
            allowed_permissions = [
                "DASHBOARD_VIEW",
                "PRODUCT_VIEW",
                "LOCATION_VIEW",
                "INVENTORY_VIEW",
                "ORDER_VIEW"
            ]

        for permission_code in allowed_permissions:
            cursor.execute("""
                INSERT OR IGNORE INTO role_permissions
                (
                    role_code,
                    permission_code,
                    allowed
                )
                VALUES (?, ?, 1)
            """, (
                role_code,
                permission_code
            ))

    connection.commit()


def main():
    print()
    print("==============================================")
    print("       ZIPPZO AUTHENTICATION SETUP")
    print("==============================================")
    print()

    print(f"Database:")
    print(DB_PATH)
    print()

    if not DB_PATH.exists():
        print("ERROR: zippzo_wms.db was not found.")
        print("Make sure this script is inside APP.")
        return

    connection = sqlite3.connect(DB_PATH)

    try:
        print("Creating authentication tables...")
        create_tables(connection)

        print("Creating default roles...")
        insert_default_roles(connection)

        print("Creating permissions...")
        insert_permissions(connection)

        print("Connecting roles with permissions...")
        setup_role_permissions(connection)

        print()
        print("==============================================")
        print("       ZIPPZO AUTH SETUP COMPLETE")
        print("==============================================")
        print()
        print("Authentication tables created:")
        print("- employees")
        print("- roles")
        print("- permissions")
        print("- role_permissions")
        print("- otp_verifications")
        print("- login_sessions")
        print("- audit_logs")
        print()
        print("Default roles created.")
        print("Existing WMS data was not deleted.")
        print()

    except Exception as error:
        connection.rollback()

        print()
        print("SETUP ERROR:")
        print(error)
        print()

    finally:
        connection.close()


if __name__ == "__main__":
    main()