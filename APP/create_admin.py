import getpass
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "zippzo_wms.db"

EMPLOYEE_ID = "ZLL000-01"
FULL_NAME = "ILLA BHARGAVA"
ROLE = "SUPER_ADMIN"
EMAIL = "BHARGAVAILLAZIPPZO@gmail.com"
MOBILE = "8247362557"


def hash_password(password):
    return hashlib.sha256(
        password.encode("utf-8")
    ).hexdigest()


def main():
    print()
    print("==============================================")
    print("       ZIPPZO SUPER ADMIN SETUP")
    print("==============================================")
    print()

    print("Database:")
    print(DB_PATH)
    print()

    if not DB_PATH.exists():
        print("ERROR: zippzo_wms.db was not found.")
        return

    password = getpass.getpass(
        "Enter Super Admin password: "
    )

    confirm_password = getpass.getpass(
        "Confirm password: "
    )

    if not password:
        print("ERROR: Password cannot be empty.")
        return

    if password != confirm_password:
        print("ERROR: Passwords do not match.")
        return

    if len(password) < 8:
        print("ERROR: Password must contain at least 8 characters.")
        return

    connection = sqlite3.connect(DB_PATH)

    try:
        cursor = connection.cursor()

        now = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        password_hash = hash_password(password)

        cursor.execute(
            """
            SELECT id
            FROM employees
            WHERE employee_id = ?
               OR email = ?
               OR mobile = ?
            """,
            (
                EMPLOYEE_ID,
                EMAIL,
                MOBILE
            )
        )

        existing = cursor.fetchone()

        if existing:

            cursor.execute(
                """
                UPDATE employees
                SET
                    employee_id = ?,
                    full_name = ?,
                    email = ?,
                    mobile = ?,
                    password_hash = ?,
                    role = ?,
                    status = 'ACTIVE',
                    email_verified = 1,
                    mobile_verified = 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    EMPLOYEE_ID,
                    FULL_NAME,
                    EMAIL,
                    MOBILE,
                    password_hash,
                    ROLE,
                    now,
                    existing[0]
                )
            )

            print("Existing employee account updated.")

        else:

            cursor.execute(
                """
                INSERT INTO employees
                (
                    employee_id,
                    full_name,
                    email,
                    mobile,
                    password_hash,
                    role,
                    status,
                    email_verified,
                    mobile_verified,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    EMPLOYEE_ID,
                    FULL_NAME,
                    EMAIL,
                    MOBILE,
                    password_hash,
                    ROLE,
                    "ACTIVE",
                    1,
                    1,
                    now,
                    now
                )
            )

            print("New Super Admin account created.")

        connection.commit()

        print()
        print("==============================================")
        print("       SUPER ADMIN CREATED SUCCESSFULLY")
        print("==============================================")
        print()
        print("Employee ID :", EMPLOYEE_ID)
        print("Name        :", FULL_NAME)
        print("Role        :", ROLE)
        print("Email       :", EMAIL)
        print("Mobile      :", MOBILE)
        print("Status      : ACTIVE")
        print("Password    : Securely stored as hash")
        print()
        print("Zippzo Super Admin is ready.")
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