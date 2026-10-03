"""
Zippzo WMS - Batch Backend V2
Safe standalone backend module.

This file is intentionally separate from APP/main.py.
After testing, it can be included from main.py with:
    from .batch_backend_v2 import router as batch_router
    app.include_router(batch_router)

It creates only the new Batch tables and Batch permissions.
It does NOT delete or reset existing Zippzo WMS data.
"""

from datetime import datetime
from typing import Optional
from pathlib import Path
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Header
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import (
    Employee,
    RolePermission,
    Permission,
    LoginSession,
    Order,
    OrderItem,
    Location,
)

router = APIRouter(tags=["Batch Management"])


# =========================================================
# NEW BATCH TABLES
# =========================================================

class Batch(Base):
    __tablename__ = "wms_batches"

    id = Column(Integer, primary_key=True, index=True)
    batch_number = Column(String, unique=True, nullable=False, index=True)
    location_id = Column(Integer, nullable=False, index=True)

    order_count = Column(Integer, default=0)
    total_units = Column(Integer, default=0)

    priority = Column(String, default="NORMAL", index=True)
    status = Column(String, default="CREATED", index=True)

    order_status = Column(String, default="ALLOCATED")
    notes = Column(Text, nullable=True)

    created_by = Column(Integer, nullable=True, index=True)
    created_by_name = Column(String, nullable=True)

    cancelled_by = Column(Integer, nullable=True)
    cancelled_by_name = Column(String, nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    cancelled_at = Column(String, nullable=True)

    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class BatchOrder(Base):
    __tablename__ = "wms_batch_orders"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("wms_batches.id"), nullable=False, index=True)
    order_id = Column(Integer, nullable=False, index=True)

    order_number = Column(String, nullable=False, index=True)
    quantity = Column(Integer, default=0)

    status = Column(String, default="IN_BATCH", index=True)
    created_at = Column(String, nullable=False)


# Create only the new tables.
Base.metadata.create_all(bind=engine)


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

    # Admin and Operations Manager receive all batch permissions.
    admin_roles = {
        "ADMIN",
        "ADMINISTRATOR",
        "OPERATIONS_MANAGER",
        "OPERATIONS MANAGER",
        "OPS_MANAGER",
    }

    for role_code in admin_roles:
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


def generate_batch_number(db: Session) -> str:
    highest = 0

    rows = db.query(Batch.batch_number).all()

    for row in rows:
        value = row[0] or ""
        if value.startswith("ZPB-"):
            try:
                highest = max(highest, int(value.split("-")[-1]))
            except ValueError:
                pass

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


def get_role_variants(employee: Employee):
    raw = str(employee.role or "").strip().upper()

    variants = {
        raw,
        raw.replace("_", " "),
        raw.replace(" ", "_"),
    }

    if raw in {"ADMIN", "ADMINISTRATOR"}:
        variants.update({"ADMIN", "ADMINISTRATOR"})

    if raw in {
        "OPERATIONS MANAGER",
        "OPERATIONS_MANAGER",
        "OPS MANAGER",
        "OPS_MANAGER",
        "OPS_MANAGER",
    }:
        variants.update({
            "OPERATIONS MANAGER",
            "OPERATIONS_MANAGER",
            "OPS MANAGER",
            "OPS_MANAGER",
        })

    return variants


def require_batch_permission(
    employee: Employee,
    db: Session,
    permission_code: str,
):
    # First check the configured role-permission table.
    variants = get_role_variants(employee)

    allowed = (
        db.query(RolePermission)
        .filter(
            RolePermission.role_code.in_(variants),
            RolePermission.permission_code == permission_code,
            RolePermission.allowed == True,
        )
        .first()
    )

    if allowed:
        return

    # Fallback for the two explicitly approved management roles.
    if (
        permission_code in {
            "BATCH_VIEW",
            "BATCH_UPLOAD",
            "BATCH_CREATE",
            "BATCH_CANCEL",
        }
        and variants.intersection({
            "ADMIN",
            "ADMINISTRATOR",
            "OPERATIONS MANAGER",
            "OPERATIONS_MANAGER",
            "OPS MANAGER",
            "OPS_MANAGER",
        })
    ):
        return

    raise HTTPException(
        status_code=403,
        detail=f"Permission denied: {permission_code}",
    )


def current_employee_from_session(
    authorization: Optional[str],
    db: Session,
) -> Employee:
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization required",
        )

    token = authorization
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

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
            detail="Invalid session",
        )

    employee = (
        db.query(Employee)
        .filter(Employee.id == session.employee_id)
        .first()
    )

    if not employee:
        raise HTTPException(
            status_code=401,
            detail="Employee not found",
        )

    if str(employee.status).upper() != "ACTIVE":
        raise HTTPException(
            status_code=403,
            detail="Employee account is not active",
        )

    return employee


# =========================================================
# SCHEMAS
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
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    # Header extraction is handled manually here so this standalone
    # router does not depend on main.py.
    employee = current_employee_from_session(authorization, db)
    require_batch_permission(employee, db, "BATCH_VIEW")

    rows = (
        db.query(Batch)
        .order_by(Batch.id.desc())
        .all()
    )

    result = []

    for batch in rows:
        location = (
            db.query(Location)
            .filter(Location.id == batch.location_id)
            .first()
        )

        result.append({
            "id": batch.id,
            "batch_number": batch.batch_number,
            "location_id": batch.location_id,
            "location_code": location.location_code if location else None,
            "location_name": location.location_name if location else None,
            "order_count": batch.order_count,
            "total_units": batch.total_units,
            "priority": batch.priority,
            "status": batch.status,
            "order_status": batch.order_status,
            "notes": batch.notes,
            "created_by": batch.created_by,
            "created_by_name": batch.created_by_name,
            "cancelled_by": batch.cancelled_by,
            "cancelled_by_name": batch.cancelled_by_name,
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
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    employee = current_employee_from_session(authorization, db)
    require_batch_permission(employee, db, "BATCH_CREATE")

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

    allowed_statuses = {
        "ALLOCATED",
        "READY_FOR_PICKING",
        "PICKING_READY",
    }

    requested_status = str(data.order_status).upper()

    if requested_status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail="Invalid order status for batch creation",
        )

    # Only orders not already placed in a non-cancelled batch
    # are eligible.
    existing_order_ids = {
        row.order_id
        for row in (
            db.query(BatchOrder.order_id)
            .join(Batch, Batch.id == BatchOrder.batch_id)
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

    eligible = [
        order
        for order in orders
        if order.id not in existing_order_ids
    ]

    if not eligible:
        raise HTTPException(
            status_code=400,
            detail=(
                "No eligible orders found for this location and status. "
                "Orders may already be in a batch."
            ),
        )

    batch_time = now()
    batch_number = generate_batch_number(db)

    total_units = 0

    batch = Batch(
        batch_number=batch_number,
        location_id=data.location_id,
        order_count=0,
        total_units=0,
        priority=str(data.priority or "NORMAL").upper(),
        status="CREATED",
        order_status=requested_status,
        notes=data.notes,
        created_by=employee.id,
        created_by_name=employee.full_name,
        created_at=batch_time,
        updated_at=batch_time,
    )

    db.add(batch)
    db.flush()

    for order in eligible:
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

        db.add(
            BatchOrder(
                batch_id=batch.id,
                order_id=order.id,
                order_number=order.order_number,
                quantity=quantity,
                status="IN_BATCH",
                created_at=batch_time,
            )
        )

        order.status = "BATCH_CREATED"
        order.updated_at = batch_time

    batch.order_count = len(eligible)
    batch.total_units = total_units
    batch.updated_at = batch_time

    # Audit log is intentionally written directly so this standalone
    # module does not depend on main.py's helper.
    from .models import AuditLog

    db.add(
        AuditLog(
            employee_id=employee.id,
            employee_name=employee.full_name,
            action="CREATE",
            module="BATCH",
            reference_id=str(batch.id),
            description=(
                f"Created batch {batch.batch_number}; "
                f"{batch.order_count} orders; "
                f"{batch.total_units} units"
            ),
            ip_address=None,
            created_at=batch_time,
        )
    )

    db.commit()
    db.refresh(batch)

    return {
        "message": "Batch created successfully",
        "batch": {
            "id": batch.id,
            "batch_number": batch.batch_number,
            "location_id": batch.location_id,
            "order_count": batch.order_count,
            "total_units": batch.total_units,
            "status": batch.status,
            "priority": batch.priority,
        },
    }


# =========================================================
# CANCEL BATCH
# =========================================================

@router.post("/api/batches/{batch_id}/cancel")
def cancel_batch(
    batch_id: int,
    data: BatchCancelRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    employee = current_employee_from_session(authorization, db)
    require_batch_permission(employee, db, "BATCH_CANCEL")

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

    batch.status = "CANCELLED"
    batch.cancelled_by = employee.id
    batch.cancelled_by_name = employee.full_name
    batch.cancellation_reason = data.reason.strip()
    batch.cancelled_at = now()
    batch.updated_at = batch.cancelled_at

    # Return batch orders to their previous operational status.
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
            order.status = batch.order_status or "ALLOCATED"
            order.updated_at = batch.cancelled_at

        batch_order.status = "BATCH_CANCELLED"

    from .models import AuditLog

    db.add(
        AuditLog(
            employee_id=employee.id,
            employee_name=employee.full_name,
            action="CANCEL",
            module="BATCH",
            reference_id=str(batch.id),
            description=(
                f"Cancelled batch {batch.batch_number}. "
                f"Reason: {batch.cancellation_reason}"
            ),
            ip_address=None,
            created_at=batch.cancelled_at,
        )
    )

    db.commit()

    return {
        "message": "Batch cancelled successfully",
        "batch_id": batch.id,
        "batch_number": batch.batch_number,
        "status": batch.status,
        "reason": batch.cancellation_reason,
    }


# =========================================================
# EXCEL / CSV UPLOAD
# =========================================================

def parse_uploaded_rows(filename: str, content: bytes):
    suffix = Path(filename or "").suffix.lower()

    if suffix == ".csv":
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        return list(reader)

    if suffix in {".xlsx", ".xls"}:
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Excel support requires openpyxl. "
                    "Install it with: python -m pip install openpyxl"
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
        detail="Only .xlsx, .xls and .csv files are supported",
    )


@router.post("/api/batches/upload-excel")
async def upload_batch_excel(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    employee = current_employee_from_session(authorization, db)
    require_batch_permission(employee, db, "BATCH_UPLOAD")

    content = await file.read()
    rows = parse_uploaded_rows(file.filename or "", content)

    if not rows:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file contains no data rows",
        )

    # Accepted header names.
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

    for row_number, item in enumerate(normalized, start=2):
        order_number = item.get("order_number", "").strip()

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
            .filter(Order.order_number == order_number)
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
                "error": f"Order status {order.status} is not eligible",
            })
            continue

        if item.get("location_code"):
            location = (
                db.query(Location)
                .filter(
                    Location.location_code
                    == item["location_code"]
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
                    "error": "Order does not belong to uploaded location",
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
            "errors": errors,
        }

    # Group uploaded orders by location.
    groups = {}

    for item in valid:
        key = (
            item["location_id"],
            item["priority"],
            item["order_status"],
        )
        groups.setdefault(key, []).append(item)

    imported = 0
    created_batches = []

    for (location_id, priority, order_status), group in groups.items():
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
            notes=f"Created from Excel upload: {file.filename}",
            created_by=employee.id,
            created_by_name=employee.full_name,
            created_at=batch_time,
            updated_at=batch_time,
        )

        db.add(batch)
        db.flush()

        total_units = 0

        for item in group:
            existing = (
                db.query(BatchOrder)
                .join(Batch, Batch.id == BatchOrder.batch_id)
                .filter(
                    BatchOrder.order_id == item["order_id"],
                    Batch.status != "CANCELLED",
                )
                .first()
            )

            if existing:
                errors.append({
                    "row": item["row"],
                    "order_number": item["order_number"],
                    "error": "Order is already in an active batch",
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
                .filter(Order.id == item["order_id"])
                .first()
            )

            if order:
                order.status = "BATCH_CREATED"
                order.updated_at = batch_time

            imported += 1

        batch.order_count = len(
            db.query(BatchOrder)
            .filter(BatchOrder.batch_id == batch.id)
            .all()
        )
        batch.total_units = total_units

        if batch.order_count == 0:
            db.delete(batch)
            db.flush()
        else:
            created_batches.append(batch_number)

    from .models import AuditLog

    db.add(
        AuditLog(
            employee_id=employee.id,
            employee_name=employee.full_name,
            action="UPLOAD",
            module="BATCH",
            reference_id="EXCEL",
            description=(
                f"Batch Excel upload {file.filename}; "
                f"imported {imported} orders"
            ),
            ip_address=None,
            created_at=now(),
        )
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
