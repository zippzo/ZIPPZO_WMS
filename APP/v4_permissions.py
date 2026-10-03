from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .models import Employee


# ============================================================
# ZIPPZO WMS V4
# ROLE & PERMISSION ENGINE
# ============================================================
#
# Workflow:
#
# LOGIN
#   ↓
# EMPLOYEE
#   ↓
# ACTIVE CHECK
#   ↓
# ROLE
#   ↓
# PERMISSION
#   ↓
# API ACTION
#
# Existing authentication remains unchanged.
# This file does NOT delete, reset, or recreate the database.
# ============================================================


# ============================================================
# 1. PERMISSION CODES
# ============================================================

V4_PERMISSION_CODES = {
    # -------------------------
    # BATCH
    # -------------------------
    "BATCH_VIEW",
    "BATCH_CREATE",
    "BATCH_UPLOAD",
    "BATCH_CANCEL",

    # -------------------------
    # PICKING
    # -------------------------
    "PICK_VIEW",
    "PICK_CREATE",
    "PICK_ASSIGN",
    "PICK_REMOVE",
    "PICK_EXECUTE",

    # -------------------------
    # SORTING
    # -------------------------
    "SORT_VIEW",
    "SORT_CREATE",
    "SORT_ASSIGN",
    "SORT_REMOVE",
    "SORT_EXECUTE",

    # -------------------------
    # GRID PUTAWAY
    # -------------------------
    "GRID_VIEW",
    "GRID_CREATE",
    "GRID_ASSIGN",
    "GRID_EXECUTE",
}


# ============================================================
# 2. ROLE → PERMISSION MATRIX
# ============================================================

ROLE_PERMISSION_MAP = {

    # ========================================================
    # ADMIN
    # ========================================================

    "ADMIN": set(V4_PERMISSION_CODES),
    "SUPER_ADMIN": set(V4_PERMISSION_CODES),

    # ========================================================
    # OPERATIONS MANAGER
    # ========================================================

    "OPERATIONS MANAGER": {
        # Batch
        "BATCH_VIEW",
        "BATCH_CREATE",
        "BATCH_UPLOAD",
        "BATCH_CANCEL",

        # Picking
        "PICK_VIEW",
        "PICK_CREATE",
        "PICK_ASSIGN",
        "PICK_REMOVE",

        # Sorting
        "SORT_VIEW",
        "SORT_CREATE",
        "SORT_ASSIGN",
        "SORT_REMOVE",

        # Grid Putaway
        "GRID_VIEW",
        "GRID_CREATE",
        "GRID_ASSIGN",
        "GRID_EXECUTE",
    },

    # Database may store underscore version
    "OPERATIONS_MANAGER": {
        # Batch
        "BATCH_VIEW",
        "BATCH_CREATE",
        "BATCH_UPLOAD",
        "BATCH_CANCEL",

        # Picking
        "PICK_VIEW",
        "PICK_CREATE",
        "PICK_ASSIGN",
        "PICK_REMOVE",

        # Sorting
        "SORT_VIEW",
        "SORT_CREATE",
        "SORT_ASSIGN",
        "SORT_REMOVE",

        # Grid Putaway
        "GRID_VIEW",
        "GRID_CREATE",
        "GRID_ASSIGN",
        "GRID_EXECUTE",
    },

    # ========================================================
    # PICKER
    # ========================================================

    "PICKER": {
        "PICK_VIEW",
        "PICK_EXECUTE",
    },

    # ========================================================
    # SORTER
    # ========================================================

    "SORTER": {
        "SORT_VIEW",
        "SORT_EXECUTE",
    },
}


# ============================================================
# 3. ROLE NORMALIZATION
# ============================================================

def normalize_role(role) -> str:
    """
    Converts different role formats into a standard format.

    Examples:

        "admin"
            → "ADMIN"

        "Operations Manager"
            → "OPERATIONS MANAGER"

        "operations_manager"
            → "OPERATIONS MANAGER"

        "Operations-Manager"
            → "OPERATIONS MANAGER"
    """

    if not role:
        return ""

    value = str(role).strip().upper()

    value = value.replace("-", " ")
    value = value.replace("_", " ")

    value = " ".join(value.split())

    return value


# ============================================================
# 4. EMPLOYEE ROLE
# ============================================================

def employee_role(employee: Employee) -> str:
    """
    Return normalized employee role.
    """

    if not employee:
        return ""

    return normalize_role(
        getattr(employee, "role", None)
    )


# ============================================================
# 5. GET EMPLOYEE PERMISSIONS
# ============================================================

def get_employee_permissions(employee: Employee) -> set[str]:
    """
    Return all V4 permissions available to an employee.
    """

    if not employee:
        return set()

    role = employee_role(employee)

    # Handle normalized role names.
    if role == "OPERATIONS MANAGER":
        return set(
            ROLE_PERMISSION_MAP.get(
                "OPERATIONS MANAGER",
                set()
            )
        )

    return set(
        ROLE_PERMISSION_MAP.get(
            role,
            set()
        )
    )


# ============================================================
# 6. CHECK PERMISSION
# ============================================================

def has_v4_permission(
    employee: Employee,
    permission_code: str,
) -> bool:
    """
    Check whether an employee has a specific V4 permission.
    """

    if not employee:
        return False

    # Employee must be active.
    if str(
        getattr(employee, "status", "")
    ).upper() != "ACTIVE":
        return False

    required = str(
        permission_code
    ).strip().upper()

    if required not in V4_PERMISSION_CODES:
        return False

    permissions = get_employee_permissions(
        employee
    )

    return required in permissions


# ============================================================
# 7. REQUIRE PERMISSION
# ============================================================

def require_v4_permission(permission_code: str):
    """
    FastAPI dependency factory.

    Example:

        employee = Depends(
            require_v4_permission("PICK_EXECUTE")
        )
    """

    required = str(
        permission_code
    ).strip().upper()

    def dependency(
        employee: Employee,
        db: Session = Depends(get_db),
    ):
        # ----------------------------------------------------
        # Validate permission code
        # ----------------------------------------------------

        if required not in V4_PERMISSION_CODES:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Unknown V4 permission: "
                    f"{required}"
                ),
            )

        # ----------------------------------------------------
        # Employee check
        # ----------------------------------------------------

        if not employee:
            raise HTTPException(
                status_code=401,
                detail="Employee authentication required",
            )

        # ----------------------------------------------------
        # Active account check
        # ----------------------------------------------------

        if str(
            getattr(employee, "status", "")
        ).upper() != "ACTIVE":

            raise HTTPException(
                status_code=403,
                detail="Employee account is inactive",
            )

        # ----------------------------------------------------
        # Permission check
        # ----------------------------------------------------

        if not has_v4_permission(
            employee,
            required,
        ):

            role = employee_role(employee)

            raise HTTPException(
                status_code=403,
                detail=(
                    f"Permission denied: {required}. "
                    f"Role '{role or 'UNKNOWN'}' "
                    f"cannot perform this action."
                ),
            )

        return employee

    return dependency


# ============================================================
# 8. PERMISSION MATRIX
# ============================================================

def get_v4_permission_matrix():
    """
    Return complete V4 permission matrix.

    Useful for:
        - Admin panel
        - Access Control page
        - API response
        - Permission reports
    """

    result = []

    for role, permissions in ROLE_PERMISSION_MAP.items():

        result.append({
            "role": role,
            "permissions": sorted(
                permissions
            ),
            "permission_count": len(
                permissions
            ),
        })

    return result


# ============================================================
# 9. ROLE ACCESS SUMMARY
# ============================================================

def get_role_access(role: str):
    """
    Return permissions for a specific role.
    """

    normalized = normalize_role(role)

    # ROLE_PERMISSION_MAP uses SUPER_ADMIN with underscore,
    # while normalize_role() converts it to SUPER ADMIN.
    map_role = normalized

    if normalized == "SUPER ADMIN":
        map_role = "SUPER_ADMIN"

    permissions = ROLE_PERMISSION_MAP.get(
        map_role,
        set(),
    )

    return {
        "role": normalized,
        "permissions": sorted(permissions),
        "permission_count": len(permissions),
    }


# ============================================================
# 10. MODULE ACCESS CHECK
# ============================================================

def can_access_batch(employee: Employee) -> bool:
    return has_v4_permission(
        employee,
        "BATCH_VIEW",
    )


def can_access_picking(employee: Employee) -> bool:
    return has_v4_permission(
        employee,
        "PICK_VIEW",
    )


def can_access_sorting(employee: Employee) -> bool:
    return has_v4_permission(
        employee,
        "SORT_VIEW",
    )


def can_access_grid_putaway(employee: Employee) -> bool:
    return has_v4_permission(
        employee,
        "GRID_VIEW",
    )


# ============================================================
# 11. ACTION CHECKS
# ============================================================

def can_create_batch(employee: Employee) -> bool:
    return has_v4_permission(
        employee,
        "BATCH_CREATE",
    )


def can_upload_batch(employee: Employee) -> bool:
    return has_v4_permission(
        employee,
        "BATCH_UPLOAD",
    )


def can_cancel_batch(employee: Employee) -> bool:
    return has_v4_permission(
        employee,
        "BATCH_CANCEL",
    )


def can_create_pick(employee: Employee) -> bool:
    return has_v4_permission(
        employee,
        "PICK_CREATE",
    )


def can_assign_picker(employee: Employee) -> bool:
    return has_v4_permission(
        employee,
        "PICK_ASSIGN",
    )


def can_remove_picker(employee: Employee) -> bool:
    return has_v4_permission(
        employee,
        "PICK_REMOVE",
    )


def can_execute_picking(employee: Employee) -> bool:
    return has_v4_permission(
        employee,
        "PICK_EXECUTE",
    )


def can_create_sort(employee: Employee) -> bool:
    return has_v4_permission(
        employee,
        "SORT_CREATE",
    )


def can_assign_sorter(employee: Employee) -> bool:
    return has_v4_permission(
        employee,
        "SORT_ASSIGN",
    )


def can_remove_sorter(employee: Employee) -> bool:
    return has_v4_permission(
        employee,
        "SORT_REMOVE",
    )


def can_execute_sorting(employee: Employee) -> bool:
    return has_v4_permission(
        employee,
        "SORT_EXECUTE",
    )


def can_create_grid_putaway(
    employee: Employee,
) -> bool:
    return has_v4_permission(
        employee,
        "GRID_CREATE",
    )


def can_assign_grid_putaway(
    employee: Employee,
) -> bool:
    return has_v4_permission(
        employee,
        "GRID_ASSIGN",
    )


def can_execute_grid_putaway(
    employee: Employee,
) -> bool:
    return has_v4_permission(
        employee,
        "GRID_EXECUTE",
    )


# ============================================================
# 12. DEBUG / ADMIN INFORMATION
# ============================================================

def permission_summary(
    employee: Employee,
):
    """
    Return a clean permission summary for frontend/admin use.
    """

    role = employee_role(employee)
    permissions = get_employee_permissions(
        employee
    )

    return {
        "employee_id": getattr(
            employee,
            "employee_id",
            None,
        ),
        "employee_name": getattr(
            employee,
            "name",
            None,
        ),
        "role": role,
        "status": getattr(
            employee,
            "status",
            None,
        ),
        "permissions": sorted(
            permissions
        ),
        "modules": {
            "batch": "BATCH_VIEW" in permissions,
            "picking": "PICK_VIEW" in permissions,
            "sorting": "SORT_VIEW" in permissions,
            "grid_putaway": "GRID_VIEW" in permissions,
        },
    }


# ============================================================
# END OF V4 PERMISSION ENGINE
# ============================================================