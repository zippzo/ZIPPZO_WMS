from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .models import Employee, LoginSession

from .workflow_v4 import router as workflow_router

from .v4_permissions import (
    has_v4_permission,
)


# ============================================================
# ZIPPZO WMS V4 — SECURE ROUTER
# ============================================================
#
# Existing authentication:
#
# Authorization: Bearer <session_token>
#
#        ↓
#
# LoginSession
#        ↓
# Employee
#        ↓
# Active Employee
#        ↓
# V4 Permission
#        ↓
# Workflow API
#
# This file does NOT:
# - delete the database
# - reset the database
# - create a second login system
# - create a second FastAPI application
#
# It only protects the existing V4 workflow router.
# ============================================================


# ============================================================
# 1. SECURE ROUTER
# ============================================================

secure_router = APIRouter(
    tags=["Zippzo WMS V4 Secure Workflow"],
)


# ============================================================
# 2. DATETIME HELPER
# ============================================================

def parse_datetime(value):
    """
    Convert stored session expiry value into datetime.
    """

    if not value:
        return None

    if isinstance(value, datetime):
        return value

    text = str(value).strip()

    if not text:
        return None

    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except Exception:
        return None


# ============================================================
# 3. CURRENT V4 EMPLOYEE
# ============================================================

def get_current_v4_employee(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Validate the existing Zippzo login session.

    No new authentication system is created.
    """

    # --------------------------------------------------------
    # Authorization header
    # --------------------------------------------------------

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    token = authorization.strip()

    # --------------------------------------------------------
    # Bearer token
    # --------------------------------------------------------

    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
        )

    # --------------------------------------------------------
    # Find active login session
    # --------------------------------------------------------

    session = (
        db.query(LoginSession)
        .filter(
            LoginSession.session_token == token,
            LoginSession.revoked == False,
        )
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session",
        )

    # --------------------------------------------------------
    # Session expiry
    # --------------------------------------------------------

    expiry = parse_datetime(
        session.expires_at
    )

    if not expiry:
        session.revoked = True
        db.commit()

        raise HTTPException(
            status_code=401,
            detail="Invalid session expiry",
        )

    # --------------------------------------------------------
    # Handle timezone-aware / naive datetimes
    # --------------------------------------------------------

    try:
        current_time = datetime.now(
            expiry.tzinfo
        ) if expiry.tzinfo else datetime.now()

    except Exception:
        current_time = datetime.now()

    if current_time >= expiry:

        session.revoked = True
        db.commit()

        raise HTTPException(
            status_code=401,
            detail="Session expired",
        )

    # --------------------------------------------------------
    # Find employee
    # --------------------------------------------------------

    employee = (
        db.query(Employee)
        .filter(
            Employee.id == session.employee_id
        )
        .first()
    )

    if not employee:

        session.revoked = True
        db.commit()

        raise HTTPException(
            status_code=401,
            detail="Employee account not found",
        )

    # --------------------------------------------------------
    # Employee active check
    # --------------------------------------------------------

    if str(
        getattr(employee, "status", "")
    ).upper() != "ACTIVE":

        session.revoked = True
        db.commit()

        raise HTTPException(
            status_code=403,
            detail="Employee account is inactive",
        )

    return employee


# ============================================================
# 4. V4 PERMISSION DEPENDENCY
# ============================================================

def require_v4_permission(permission_code: str):
    """
    Secure a V4 endpoint using the existing login session
    and the V4 role/permission engine.
    """

    required = str(
        permission_code
    ).strip().upper()

    def dependency(
        employee: Employee = Depends(
            get_current_v4_employee
        ),
    ):

        if not has_v4_permission(
            employee,
            required,
        ):

            role = str(
                getattr(
                    employee,
                    "role",
                    "",
                )
            ).strip()

            raise HTTPException(
                status_code=403,
                detail=(
                    f"Permission denied: "
                    f"{required}. "
                    f"Role '{role or 'UNKNOWN'}' "
                    f"cannot perform this action."
                ),
            )

        return employee

    return dependency


# ============================================================
# 5. HEALTH CHECK
# ============================================================

@secure_router.get(
    "/secure-health",
    summary="V4 Secure Health Check",
)
def secure_health(
    employee: Employee = Depends(
        get_current_v4_employee
    ),
):
    """
    Verify that authentication is working.
    """

    return {
        "success": True,
        "module": "Zippzo WMS V4",
        "authenticated": True,
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
        "role": getattr(
            employee,
            "role",
            None,
        ),
        "status": getattr(
            employee,
            "status",
            None,
        ),
    }


# ============================================================
# 6. PERMISSION CHECK ROUTE
# ============================================================

@secure_router.get(
    "/permissions/check/{permission_code}",
    summary="Check V4 Permission",
)
def check_permission(
    permission_code: str,
    employee: Employee = Depends(
        get_current_v4_employee
    ),
):
    """
    Allows the frontend to determine whether the logged-in
    employee can perform a particular V4 action.
    """

    required = str(
        permission_code
    ).strip().upper()

    allowed = has_v4_permission(
        employee,
        required,
    )

    return {
        "success": True,
        "permission": required,
        "allowed": allowed,
        "employee_id": getattr(
            employee,
            "employee_id",
            None,
        ),
        "role": getattr(
            employee,
            "role",
            None,
        ),
    }


# ============================================================
# 7. V4 WORKFLOW ROUTER
# ============================================================
#
# The workflow_v4 router is included below.
#
# IMPORTANT:
#
# The existing workflow_v4.py currently contains the actual
# business endpoints.
#
# This secure router provides the authentication layer.
#
# Endpoint-specific permission enforcement should be applied
# in the workflow implementation before production use.
# ============================================================

secure_router.include_router(
    workflow_router,
    dependencies=[
        Depends(get_current_v4_employee)
    ],
)


# ============================================================
# END
# ============================================================