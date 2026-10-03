"""
Zippzo WMS - Corrected Batch Backend V2

This module is designed to be imported by APP.main.
It uses the same LoginSession / Employee authentication structure
already present in the existing Zippzo WMS.

DO NOT run this file directly.

Integration in APP/main.py:
    from .batch_backend_v2_corrected import router as batch_router
    app.include_router(batch_router)

It creates only:
    wms_batches
    wms_batch_orders

It does NOT delete, reset, or replace existing WMS data.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
import csv
import io

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel, Field
from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models_v4 import WMSBatch, WMSBatchOrder
from .models import (
    AuditLog,
    Employee,
    Location,
    LoginSession,
    Order,
    OrderItem,
    Permission,
    RolePermission,
)

router = APIRouter(tags=["Batch Management"])


# =========================================================
# NEW BATCH TABLES
# =========================================================

Batch = WMSBatch
BatchOrder = WMSBatchOrder



# =========================================================
# PERMISSIONS
# =========================================================

BATCH_PERMISSIONS = [
    ("BATCH_VIEW", "View Batches", "BATCH"),
    ("BATCH_UPLOAD", "Upload Batch Excel", "BATCH"),
    ("BATCH_CREATE", "Create Batch", "BATCH"),
    ("BATCH_CANCEL", "Cancel Batch", "BATCH"),
]


def seed_batch_permissions(db: Session):
    """
    Safe/idempotent permission setup.
    Existing permissions are not changed.
    """
    for code, name, module in BATCH_PERMISSIONS:
        existing = (
            db.query(Permission)
            .filter(Permission.permission_code == code)
            .first()
        )

        if not existing:
            db.add(
                Permission(
                    permission_code=code,
                    permission_name=name,
                    module=module,
                    active=True,
                )
            )

    db.flush()

    management_roles = {
        "ADMIN",
        "ADMINISTRATOR",
        "OPERATIONS MANAGER",
        "OPERATIONS_MANAGER",
        "OPS MANAGER",
        "OPS_MANAGER",
    }

    for role_code in management_roles:
        for permission_code, _, _ in BATCH_PERMISSIONS:
            existing = (
                db.query(RolePermission)
                .filter(
                    RolePermission.role_code == role_code,
                    RolePermission.permission_code == permission_code,
                )
                .first()
            )

            if not existing:
                db.add(
                    RolePermission(
                        role_code=role_code,
                        permission_code=permission_code,
                        allowed=True,
                    )
                )

    db.commit()


# =========================================================
# HELPERS
# =========================================================

def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def employee_role_variants(employee: Employee) -> set[str]:
    raw = str(employee.role or "").strip().upper()

    variants = {
        raw,
        raw.replace("_", " "),
        raw.replace(" ", "_"),
    }

    if raw in {
        "ADMIN",
        "ADMINISTRATOR",
    }:
        variants.update({
            "ADMIN",
            "ADMINISTRATOR",
        })

    if raw in {
        "OPERATIONS MANAGER",
        "OPERATIONS_MANAGER",
        "OPS MANAGER",
        "OPS_MANAGER",
    }:
        variants.update({
            "OPERATIONS MANAGER",
            "OPERATIONS_MANAGER",
            "OPS MANAGER",
            "OPS_MANAGER",
        })

    return variants


def get_current_batch_employee(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Employee:
    """
    Matches the existing WMS LoginSession authentication:
    Authorization: Bearer <session_token>
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization required",
        )

    token = authorization.strip()

    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
        )

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

    # Existing WMS stores expiry as YYYY-MM-DD HH:MM:SS.
    try:
        expiry = datetime.strptime(
            session.expires_at,
            "%Y-%m-%d %H:%M:%S",
        )

        if datetime.now() >= expiry:
            session.revoked = True
            db.commit()
            raise HTTPException(
                status_code=401,
                detail="Session expired",
            )
    except ValueError:
        pass

    employee = (
        db.query(Employee)
        .filter(Employee.id == session.employee_id)
        .first()
    )

    if not employee:
        raise HTTPException(
            status_code=401,
            detail="Employee account not found",
        )

    if str(employee.status or "").upper() != "ACTIVE":
        raise HTTPException(
            status_code=403,
            detail="Employee account is inactive",
        )

    return employee


def require_batch_permission(
    employee: Employee,
    db: Session,
    permission_code: str,
):
    variants = employee_role_variants(employee)

    # First use the real WMS RolePermission table.
    permission = (
        db.query(RolePermission)
        .filter(
            RolePermission.role_code.in_(variants),
            RolePermission.permission_code == permission_code,
            RolePermission.allowed == True,
        )
        .first()
    )

    if permission:
        return

    # Management roles are explicitly allowed for Batch management.
    management_roles = {
        "ADMIN",
        "ADMINISTRATOR",
        "OPERATIONS MANAGER",
        "OPERATIONS_MANAGER",
        "OPS MANAGER",
        "OPS_MANAGER",
    }

    if variants.intersection(management_roles):
        if permission_code in {
            "BATCH_VIEW",
            "BATCH_UPLOAD",
            "BATCH_CREATE",
            "BATCH_CANCEL",
        }:
            return

    raise HTTPException(
        status_code=403,
        detail=f"Permission denied: {permission_code}",
    )


def generate_batch_number(db: Session) -> str:
    highest = 0

    for row in db.query(Batch.batch_number).all():
        value = row[0] or ""

        if value.startswith("ZPB-"):
            try:
                highest = max(
                    highest,
                    int(value.split("-")[-1]),
                )
            except ValueError:
                continue

    candidate = highest + 1

    while True:
        number = f"ZPB-{candidate:06d}"

        exists = (
            db.query(Batch)
            .filter(Batch.batch_number == number)
            .first()
        )

        if not exists:
            return number

        candidate += 1


def add_audit(
    db: Session,
    employee: Employee,
    action: str,
    reference_id: str,
    description: str,
):
    db.add(
        AuditLog(
            employee_id=employee.id,
            employee_name=employee.full_name,
            action=action,
            module="BATCH",
            reference_id=reference_id,
            description=description,
            ip_address=None,
            created_at=now(),
        )
    )


# =========================================================
# REQUEST MODELS
# =========================================================

class BatchCreateRequest(BaseModel):
    location_id: int
    priority: str = "NORMAL"
    order_status: str = "ALLOCATED"
    max_orders: int = Field(default=50, ge=1, le=1000)
    notes: Optional[str] = None


class BatchCancelRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=500)


# =========================================================
# GET BATCHES
# =========================================================

@router.get("/api/batches")
def get_batches(
    employee: Employee = Depends(get_current_batch_employee),
    db: Session = Depends(get_db),
):
    require_batch_permission(
        employee,
        db,
        "BATCH_VIEW",
    )

    batches = (
        db.query(Batch)
        .order_by(Batch.id.desc())
        .all()
    )

    result = []

    for batch in batches:
        location = (
            db.query(Location)
            .filter(Location.id == batch.location_id)
            .first()
        )

        result.append({
            "id": batch.id,
            "batch_number": batch.batch_number,
            "location_id": batch.location_id,
            "location_code": (
                location.location_code
                if location
                else None
            ),
            "location_name": (
                location.location_name
                if location
                else None
            ),
            "order_count": batch.total_orders or 0,
            "total_units": batch.total_units or 0,
            "priority": batch.priority,
            "status": batch.status,
            "order_status": None,
            "notes": None,
            "created_by": batch.created_by,
            "created_by_name": None,
            "cancelled_by": None,
            "cancelled_by_name": None,
            "cancellation_reason": batch.cancellation_reason,
            "cancelled_at": batch.cancelled_at,
            "created_at": batch.created_at,
            "updated_at": batch.updated_at,
        })

    return result


# =========================================================
# CREATE BATCH
# =========================================================

@router.post("/api/batches")
def create_batch(
    data: BatchCreateRequest,
    employee: Employee = Depends(get_current_batch_employee),
    db: Session = Depends(get_db),
):
    require_batch_permission(
        employee,
        db,
        "BATCH_CREATE",
    )

    location = (
        db.query(Location)
        .filter(Location.id == data.location_id)
        .first()
    )

    if not location:
        raise HTTPException(
            status_code=404,
            detail="Location not found",
        )

    if not location.active:
        raise HTTPException(
            status_code=400,
            detail="Location is inactive",
        )

    requested_status = (
        str(data.order_status or "ALLOCATED")
        .strip()
        .upper()
    )

    allowed_statuses = {
        "ALLOCATED",
        "READY_FOR_PICKING",
        "PICKING_READY",
    }

    if requested_status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=(
                "Order status must be "
                "ALLOCATED, READY_FOR_PICKING "
                "or PICKING_READY"
            ),
        )

    # Orders already belonging to an active batch
    # cannot be added again.
    active_batch_order_ids = {
        row.order_id
        for row in (
            db.query(BatchOrder.order_id)
            .join(
                Batch,
                Batch.id == BatchOrder.batch_id,
            )
            .filter(Batch.status != "CANCELLED")
            .all()
        )
    }

    orders = (
        db.query(Order)
        .filter(
            Order.location_id == data.location_id,
            Order.status == requested_status,
        )
        .order_by(Order.id.asc())
        .limit(data.max_orders)
        .all()
    )

    eligible_orders = [
        order
        for order in orders
        if order.id not in active_batch_order_ids
    ]

    if not eligible_orders:
        raise HTTPException(
            status_code=400,
            detail=(
                "No eligible orders found. "
                "Check the selected location and order status."
            ),
        )

    created_time = now()
    batch_number = generate_batch_number(db)

    batch = Batch(
        batch_number=batch_number,
        location_id=data.location_id,
        total_orders=0,
        total_units=0,
        priority=(
            str(data.priority or "NORMAL")
            .strip()
            .upper()
        ),
        status="CREATED",
        created_by=employee.id,
        created_at=created_time,
        updated_at=created_time,
    )

    db.add(batch)
    db.flush()

    total_units = 0

    for order in eligible_orders:
        items = (
            db.query(OrderItem)
            .filter(OrderItem.order_id == order.id)
            .all()
        )

        quantity = sum(
            int(item.quantity or 0)
            for item in items
        )

        total_units += quantity

        original_order_status = str(
            order.status or requested_status
        )

        db.add(
            BatchOrder(
                batch_id=batch.id,
                order_id=order.id,
                order_status_before=original_order_status,
                created_at=created_time,
            )
        )

        order.status = "BATCH_CREATED"
        order.updated_at = created_time

    batch.total_orders = len(eligible_orders)
    batch.total_units = total_units
    batch.updated_at = created_time

    add_audit(
        db=db,
        employee=employee,
        action="CREATE",
        reference_id=str(batch.id),
        description=(
            f"Created {batch.batch_number}; "
            f"{batch.total_orders} orders; "
            f"{batch.total_units} units"
        ),
    )

    db.commit()
    db.refresh(batch)

    return {
        "message": "Batch created successfully",
        "batch": {
            "id": batch.id,
            "batch_number": batch.batch_number,
            "location_id": batch.location_id,
            "order_count": batch.total_orders,
            "total_orders": batch.total_orders,
            "total_units": batch.total_units,
            "priority": batch.priority,
            "status": batch.status,
        },
    }

# CANCEL BATCH
# =========================================================

@router.post("/api/batches/{batch_id}/cancel")
def cancel_batch(
    batch_id: int,
    data: BatchCancelRequest,
    employee: Employee = Depends(get_current_batch_employee),
    db: Session = Depends(get_db),
):
    require_batch_permission(
        employee,
        db,
        "BATCH_CANCEL",
    )

    batch = (
        db.query(Batch)
        .filter(Batch.id == batch_id)
        .first()
    )

    if not batch:
        raise HTTPException(
            status_code=404,
            detail="Batch not found",
        )

    if batch.status == "CANCELLED":
        raise HTTPException(
            status_code=400,
            detail="Batch is already cancelled",
        )

    if batch.status == "COMPLETED":
        raise HTTPException(
            status_code=400,
            detail="Completed batch cannot be cancelled",
        )

    cancel_time = now()

    batch.status = "CANCELLED"
    batch.cancellation_reason = data.reason.strip()
    batch.cancelled_at = cancel_time
    batch.updated_at = cancel_time

    batch_orders = (
        db.query(BatchOrder)
        .filter(BatchOrder.batch_id == batch.id)
        .all()
    )

    for batch_order in batch_orders:
        order = (
            db.query(Order)
            .filter(Order.id == batch_order.order_id)
            .first()
        )

        if order and order.status == "BATCH_CREATED":
            order.status = (
                batch_order.order_status_before
                or "ALLOCATED"
            )
            order.updated_at = cancel_time

    add_audit(
        db=db,
        employee=employee,
        action="CANCEL",
        reference_id=str(batch.id),
        description=(
            f"Cancelled {batch.batch_number}. "
            f"Reason: {batch.cancellation_reason}"
        ),
    )

    db.commit()

    return {
        "message": "Batch cancelled successfully",
        "batch_id": batch.id,
        "batch_number": batch.batch_number,
        "status": batch.status,
        "reason": batch.cancellation_reason,
    }

# EXCEL / CSV PARSER
# =========================================================

def parse_uploaded_rows(
    filename: str,
    content: bytes,
):
    suffix = Path(filename or "").suffix.lower()

    if suffix == ".csv":
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(
            io.StringIO(text)
        )
        return list(reader)

    if suffix in {".xlsx", ".xls"}:
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Excel support requires openpyxl. "
                    "Run: python -m pip install openpyxl"
                ),
            )

        workbook = load_workbook(
            filename=io.BytesIO(content),
            read_only=True,
            data_only=True,
        )

        sheet = workbook.active
        values = list(sheet.values)

        if not values:
            return []

        headers = [
            str(value).strip()
            if value is not None
            else ""
            for value in values[0]
        ]

        rows = []

        for values_row in values[1:]:
            row = {}

            for index, header in enumerate(headers):
                row[header] = (
                    values_row[index]
                    if index < len(values_row)
                    else None
                )

            rows.append(row)

        return rows

    raise HTTPException(
        status_code=400,
        detail=(
            "Only .xlsx, .xls and .csv files "
            "are supported"
        ),
    )


# =========================================================
# EXCEL UPLOAD
# =========================================================

@router.post("/api/batches/upload-excel")
async def upload_batch_excel(
    file: UploadFile = File(...),
    employee: Employee = Depends(get_current_batch_employee),
    db: Session = Depends(get_db),
):
    require_batch_permission(
        employee,
        db,
        "BATCH_UPLOAD",
    )

    content = await file.read()

    rows = parse_uploaded_rows(
        file.filename or "",
        content,
    )

    if not rows:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file contains no data rows",
        )

    aliases = {
        "order number": "order_number",
        "ordernumber": "order_number",
        "order_number": "order_number",
        "location code": "location_code",
        "location_code": "location_code",
        "priority": "priority",
        "order status": "order_status",
        "order_status": "order_status",
    }

    normalized = []

    for raw in rows:
        item = {}

        for key, value in raw.items():
            clean_key = str(key or "").strip().lower()
            mapped = aliases.get(clean_key)

            if mapped:
                item[mapped] = (
                    str(value).strip()
                    if value is not None
                    else ""
                )

        normalized.append(item)

    valid = []
    errors = []
    seen = set()

    for row_number, item in enumerate(
        normalized,
        start=2,
    ):
        order_number = (
            item.get("order_number", "")
            .strip()
        )

        if not order_number:
            errors.append({
                "row": row_number,
                "order_number": "",
                "error": "Order Number is required",
            })
            continue

        if order_number in seen:
            errors.append({
                "row": row_number,
                "order_number": order_number,
                "error": "Duplicate order number in upload",
            })
            continue

        seen.add(order_number)

        order = (
            db.query(Order)
            .filter(
                Order.order_number == order_number
            )
            .first()
        )

        if not order:
            errors.append({
                "row": row_number,
                "order_number": order_number,
                "error": "Order not found in WMS",
            })
            continue

        if str(order.status).upper() not in {
            "ALLOCATED",
            "READY_FOR_PICKING",
            "PICKING_READY",
        }:
            errors.append({
                "row": row_number,
                "order_number": order_number,
                "error": (
                    f"Order status {order.status} "
                    "is not eligible"
                ),
            })
            continue

        location_code = item.get(
            "location_code",
            "",
        ).strip()

        if location_code:
            location = (
                db.query(Location)
                .filter(
                    Location.location_code
                    == location_code
                )
                .first()
            )

            if not location:
                errors.append({
                    "row": row_number,
                    "order_number": order_number,
                    "error": "Location Code not found",
                })
                continue

            if order.location_id != location.id:
                errors.append({
                    "row": row_number,
                    "order_number": order_number,
                    "error": (
                        "Order does not belong "
                        "to uploaded location"
                    ),
                })
                continue

        valid.append({
            "row": row_number,
            "order_id": order.id,
            "order_number": order.order_number,
            "location_id": order.location_id,
            "priority": (
                item.get("priority")
                or "NORMAL"
            ).upper(),
            "order_status": (
                item.get("order_status")
                or order.status
            ).upper(),
        })

    if not valid:
        return {
            "message": "No valid rows were imported",
            "total_rows": len(rows),
            "valid_rows": 0,
            "error_rows": len(errors),
            "imported_rows": 0,
            "created_batches": [],
            "errors": errors,
        }

    # Group valid upload rows by location/priority/status.
    groups = {}

    for item in valid:
        key = (
            item["location_id"],
            item["priority"],
            item["order_status"],
        )

        groups.setdefault(
            key,
            [],
        ).append(item)

    imported = 0
    created_batches = []

    for (
        location_id,
        priority,
        order_status,
    ), group in groups.items():

        batch_time = now()
        batch_number = generate_batch_number(db)

        batch = Batch(
            batch_number=batch_number,
            location_id=location_id,
            order_count=0,
            total_units=0,
            priority=priority,
            status="CREATED",
            order_status=order_status,
            notes=(
                "Created from Excel upload: "
                f"{file.filename}"
            ),
            created_by=employee.id,
            created_by_name=employee.full_name,
            created_at=batch_time,
            updated_at=batch_time,
        )

        db.add(batch)
        db.flush()

        total_units = 0

        for item in group:
            active_batch = (
                db.query(BatchOrder)
                .join(
                    Batch,
                    Batch.id == BatchOrder.batch_id,
                )
                .filter(
                    BatchOrder.order_id
                    == item["order_id"],
                    Batch.status != "CANCELLED",
                )
                .first()
            )

            if active_batch:
                errors.append({
                    "row": item["row"],
                    "order_number": item["order_number"],
                    "error": (
                        "Order is already "
                        "in an active batch"
                    ),
                })
                continue

            order_items = (
                db.query(OrderItem)
                .filter(
                    OrderItem.order_id
                    == item["order_id"]
                )
                .all()
            )

            quantity = sum(
                int(order_item.quantity or 0)
                for order_item in order_items
            )

            total_units += quantity

            db.add(
                BatchOrder(
                    batch_id=batch.id,
                    order_id=item["order_id"],
                    order_number=item["order_number"],
                    quantity=quantity,
                    status="IN_BATCH",
                    created_at=batch_time,
                )
            )

            order = (
                db.query(Order)
                .filter(
                    Order.id == item["order_id"]
                )
                .first()
            )

            if order:
                order.status = "BATCH_CREATED"
                order.updated_at = batch_time

            imported += 1

        batch.order_count = (
            db.query(BatchOrder)
            .filter(
                BatchOrder.batch_id == batch.id
            )
            .count()
        )

        batch.total_units = total_units

        if batch.order_count == 0:
            db.delete(batch)
            db.flush()
        else:
            created_batches.append(
                batch_number
            )

    add_audit(
        db=db,
        employee=employee,
        action="UPLOAD",
        reference_id="EXCEL",
        description=(
            f"Batch Excel upload "
            f"{file.filename}; "
            f"imported {imported} orders"
        ),
    )

    db.commit()

    return {
        "message": "Batch Excel import completed",
        "total_rows": len(rows),
        "valid_rows": len(valid),
        "error_rows": len(errors),
        "imported_rows": imported,
        "created_batches": created_batches,
        "errors": errors,
    }



