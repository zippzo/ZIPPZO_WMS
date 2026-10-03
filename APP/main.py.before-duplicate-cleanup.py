from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import secrets


from .database import Base, engine, get_db
from . import models

from .models import (
    Location,
    Product,
    Supplier,
    Inventory,
    StockMovement,
    Bin,
    Order,
    OrderItem,
    Rider,
    Employee,
    Role,
    Permission,
    RolePermission,
    OTPVerification,
    LoginSession,
    AuditLog,
    PurchaseOrder,
    PurchaseOrderItem,
    GoodsReceiptNote,
GoodsReceiptNoteItem,
PutawayTask,
PutawayAuditTask,
BinInventory,
)


# =========================================================
# DATABASE
# =========================================================

Base.metadata.create_all(bind=engine)


# =========================================================
# FASTAPI APP
# =========================================================

app = FastAPI(
    title="Zippzo Warehouse Management System",
    version="3.0.0",
    description="Zippzo WMS Backend API"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


FRONTEND_DIR = Path(__file__).resolve().parent / "FRONTEND"


# =========================================================
# CONSTANTS
# =========================================================

DELIVERY_CHARGE = 50.0
HANDLING_CHARGE = 5.0
FREE_DELIVERY_LIMIT = 100.0
SESSION_HOURS = 24


# =========================================================
# GENERAL HELPERS
# =========================================================

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.now().strftime("%Y-%m-%d")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def parse_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    return None
def as_dict(obj):
    if obj is None:
        return None

    result = {}

    for column in obj.__table__.columns:
        # Get the Python attribute value
        value = getattr(obj, column.key, None)

        # Product model:
        # database column "name" -> Python attribute "product_name"
        if hasattr(obj, "product_name") and column.name == "name":
            value = obj.product_name

        # Location model:
        # database column "code" -> Python attribute "location_code"
        elif hasattr(obj, "location_code") and column.name == "code":
            value = obj.location_code

        # Location model:
        # database column "name" -> Python attribute "location_name"
        elif hasattr(obj, "location_name") and column.name == "name":
            value = obj.location_name

        # Supplier model:
        # database column "credit_days" -> Python attribute "payment_terms"
        elif hasattr(obj, "payment_terms") and column.name == "credit_days":
            value = obj.payment_terms

        result[column.name] = value

    return result
def create_audit_log(
    db: Session,
    employee=None,
    action="",
    module="",
    reference_id=None,
    description=None,
    ip_address=None,
):
    log = AuditLog(
        employee_id=employee.id if employee else None,
        employee_name=employee.full_name if employee else None,
        action=action,
        module=module,
        reference_id=str(reference_id) if reference_id is not None else None,
        description=description,
        ip_address=ip_address,
        created_at=now(),
    )

    db.add(log)


# =========================================================
# AUTHENTICATION SCHEMAS
# =========================================================

class LoginRequest(BaseModel):
    identifier: str
    password: str


class LogoutRequest(BaseModel):
    session_token: str


class LoginResponse(BaseModel):
    message: str
    session_token: str
    expires_at: str
    user: dict


# =========================================================
# AUTHENTICATION
# =========================================================

@app.post("/api/auth/login", response_model=LoginResponse)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db)
):

    employee = (
        db.query(Employee)
        .filter(
            (
                (Employee.email == data.identifier)
                | (Employee.employee_id == data.identifier)
                | (Employee.mobile == data.identifier)
            )
        )
        .first()
    )

    if not employee:
        raise HTTPException(
            status_code=401,
            detail="Invalid login credentials"
        )

    if employee.status != "ACTIVE":
        raise HTTPException(
            status_code=403,
            detail="Employee account is not active"
        )

    if not employee.password_hash:
        raise HTTPException(
            status_code=401,
            detail="Password is not configured"
        )

    if hash_password(data.password) != employee.password_hash:
        raise HTTPException(
            status_code=401,
            detail="Invalid login credentials"
        )

    token = generate_session_token()

    expires = datetime.now() + timedelta(hours=SESSION_HOURS)

    session = LoginSession(
        employee_id=employee.id,
        session_token=token,
        login_method="PASSWORD",
        device_name=None,
        ip_address=None,
        expires_at=expires.strftime("%Y-%m-%d %H:%M:%S"),
        revoked=False,
        created_at=now(),
    )

    employee.last_login = now()

    db.add(session)

    create_audit_log(
        db=db,
        employee=employee,
        action="LOGIN",
        module="AUTH",
        description="Employee logged in",
    )

    db.commit()

    return {
        "message": "Login successful",
        "session_token": token,
        "expires_at": expires.strftime("%Y-%m-%d %H:%M:%S"),
        "user": {
            "id": employee.id,
            "employee_id": employee.employee_id,
            "full_name": employee.full_name,
            "email": employee.email,
            "mobile": employee.mobile,
            "role": employee.role,
            "department": employee.department,
            "location_id": employee.location_id,
            "status": employee.status,
        },
    }


def get_current_employee(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization required"
        )

    token = authorization

    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

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
            detail="Invalid session"
        )

    expiry = parse_datetime(session.expires_at)

    if expiry and datetime.now() > expiry:
        session.revoked = True
        db.commit()

        raise HTTPException(
            status_code=401,
            detail="Session expired"
        )

    employee = (
        db.query(Employee)
        .filter(Employee.id == session.employee_id)
        .first()
    )

    if not employee:
        raise HTTPException(
            status_code=401,
            detail="Employee not found"
        )

    return employee


@app.get("/api/auth/me")
def auth_me(
    employee: Employee = Depends(get_current_employee)
):

    return {
        "authenticated": True,
        "user": {
            "id": employee.id,
            "employee_id": employee.employee_id,
            "full_name": employee.full_name,
            "email": employee.email,
            "mobile": employee.mobile,
            "role": employee.role,
            "department": employee.department,
            "location_id": employee.location_id,
            "status": employee.status,
        },
    }


@app.post("/api/auth/logout")
def logout(
    data: LogoutRequest,
    db: Session = Depends(get_db)
):

    session = (
        db.query(LoginSession)
        .filter(
            LoginSession.session_token == data.session_token
        )
        .first()
    )

    if session:
        session.revoked = True

        employee = (
            db.query(Employee)
            .filter(Employee.id == session.employee_id)
            .first()
        )

        create_audit_log(
            db=db,
            employee=employee,
            action="LOGOUT",
            module="AUTH",
            description="Employee logged out",
        )

        db.commit()

    return {
        "message": "Logout successful"
    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/api/health")
def health():
    return {
        "status": "OK",
        "application": "Zippzo WMS",
        "version": "3.0.0",
        "time": now(),
    }


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():

    index_file = FRONTEND_DIR / "index.html"

    if index_file.exists():
        return FileResponse(index_file)

    return {
        "application": "Zippzo Warehouse Management System",
        "status": "running",
        "version": "3.0.0",
    }


@app.get("/purchase-orders.html")
def purchase_orders_page():

    file = FRONTEND_DIR / "purchase-orders.html"

    if file.exists():
        return FileResponse(file)

    raise HTTPException(
        status_code=404,
        detail="Purchase Orders page not found"
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.get("/api/dashboard")
def dashboard(
    db: Session = Depends(get_db)
):

    total_products = db.query(Product).count()
    total_locations = db.query(Location).count()
    total_inventory = db.query(Inventory).count()
    total_orders = db.query(Order).count()
    total_riders = db.query(Rider).count()
    total_suppliers = db.query(Supplier).count()
    total_purchase_orders = db.query(PurchaseOrder).count()
    total_grns = db.query(GoodsReceiptNote).count()

    available_stock = (
        db.query(func.coalesce(func.sum(Inventory.available_qty), 0))
        .scalar()
        or 0
    )

    order_value = (
        db.query(func.coalesce(func.sum(Order.total_amount), 0))
        .scalar()
        or 0
    )

    return {
        "total_products": total_products,
        "total_locations": total_locations,
        "total_inventory_records": total_inventory,
        "total_stock": available_stock,
        "total_orders": total_orders,
        "total_riders": total_riders,
        "total_suppliers": total_suppliers,
        "total_purchase_orders": total_purchase_orders,
        "total_grns": total_grns,
        "total_order_value": order_value,
    }


# =========================================================
# PRODUCT SCHEMA
# =========================================================

class ProductCreate(BaseModel):
    sku: str
    barcode: str | None = None
    image_url: str | None = None
    product_name: str
    category: str | None = None
    brand: str | None = None
    uom: str = "PCS"
    mrp: float = 0
    selling_price: float = 0
    purchase_price: float = 0
    gst_percent: float = 0
    weight: float = 0
    reorder_level: int = 0
    minimum_stock: int = 0
    maximum_stock: int = 0
    active: bool = True


@app.get("/api/products")
def get_products(
    db: Session = Depends(get_db)
):

    products = (
        db.query(Product)
        .order_by(Product.id.desc())
        .all()
    )

    return [as_dict(product) for product in products]


@app.post("/api/products")
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    existing = (
        db.query(Product)
        .filter(Product.sku == data.sku)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="SKU already exists"
        )

    product = Product(
        sku=data.sku,
        barcode=data.barcode,
        image_url=data.image_url,
        product_name=data.product_name,
        category=data.category,
        brand=data.brand,
        uom=data.uom,
        mrp=data.mrp,
        selling_price=data.selling_price,
        purchase_price=data.purchase_price,
        gst_percent=data.gst_percent,
        weight=data.weight,
        reorder_level=data.reorder_level,
        minimum_stock=data.minimum_stock,
        maximum_stock=data.maximum_stock,
        active=data.active,
    )

    db.add(product)

    create_audit_log(
        db=db,
        employee=employee,
        action="CREATE",
        module="PRODUCT",
        description=f"Created product {data.sku}",
    )

    db.commit()
    db.refresh(product)

    return as_dict(product)


# =========================================================
# LOCATION SCHEMA
# =========================================================

class LocationCreate(BaseModel):
    location_code: str
    location_name: str
    location_type: str
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    manager_name: str | None = None
    capacity: int = 0
    active: bool = True


@app.get("/api/locations")
def get_locations(
    db: Session = Depends(get_db)
):

    locations = (
        db.query(Location)
        .order_by(Location.id.desc())
        .all()
    )

    return [as_dict(location) for location in locations]


@app.post("/api/locations")
def create_location(
    data: LocationCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    existing = (
        db.query(Location)
        .filter(Location.location_code == data.location_code)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Location code already exists"
        )

    location = Location(
        location_code=data.location_code,
        location_name=data.location_name,
        location_type=data.location_type,
        address=data.address,
        city=data.city,
        state=data.state,
        pincode=data.pincode,
        manager_name=data.manager_name,
        capacity=data.capacity,
        active=data.active,
    )

    db.add(location)

    create_audit_log(
        db=db,
        employee=employee,
        action="CREATE",
        module="LOCATION",
        description=f"Created location {data.location_code}",
    )

    db.commit()
    db.refresh(location)

    return as_dict(location)

# =========================================================
# INVENTORY
# =========================================================

class StockInRequest(BaseModel):
    product_id: int
    location_id: int
    bin_id: int | None = None
    quantity: int
    reference_number: str | None = None
    remarks: str | None = None


class StockTransferRequest(BaseModel):
    product_id: int
    from_location_id: int
    to_location_id: int
    quantity: int
    from_bin_id: int | None = None
    to_bin_id: int | None = None
    reference_number: str | None = None
    remarks: str | None = None


class StockAdjustmentRequest(BaseModel):
    product_id: int
    location_id: int
    quantity: int
    bin_id: int | None = None
    reason: str
    reference_number: str | None = None


class InventoryCreate(BaseModel):
    location_id: int
    product_id: int
    bin_id: int | None = None
    available_qty: int = 0
    reserved_qty: int = 0
    picked_qty: int = 0
    packed_qty: int = 0
    dispatched_qty: int = 0
    damaged_qty: int = 0
    returned_qty: int = 0
    quarantine_qty: int = 0


def get_inventory_record(
    db: Session,
    location_id: int,
    product_id: int,
):
    """
    Find the inventory record for one SKU at one location.

    IMPORTANT:
    This function only searches.
    It does not create inventory automatically.
    """

    return (
        db.query(Inventory)
        .filter(
            Inventory.location_id == location_id,
            Inventory.product_id == product_id,
        )
        .first()
    )


# =========================================================
# GET INVENTORY
# =========================================================

@app.get("/api/inventory")
def get_inventory(
    location_id: int | None = None,
    product_id: int | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(Inventory)

    if location_id is not None:
        query = query.filter(
            Inventory.location_id == location_id
        )

    if product_id is not None:
        query = query.filter(
            Inventory.product_id == product_id
        )

    records = (
        query
        .order_by(Inventory.id.desc())
        .all()
    )

    result = []

    for inventory in records:

        product = (
            db.query(Product)
            .filter(Product.id == inventory.product_id)
            .first()
        )

        location = (
            db.query(Location)
            .filter(Location.id == inventory.location_id)
            .first()
        )

        bin_record = None

        if inventory.bin_id:
            bin_record = (
                db.query(Bin)
                .filter(Bin.id == inventory.bin_id)
                .first()
            )

        item = as_dict(inventory)

        item["product_name"] = (
            product.product_name
            if product
            else None
        )

        item["sku"] = (
            product.sku
            if product
            else None
        )

        item["location_name"] = (
            location.location_name
            if location
            else None
        )

        item["bin_code"] = (
            bin_record.bin_code
            if bin_record
            else None
        )

        result.append(item)

    return result


# =========================================================
# CREATE / UPDATE INVENTORY
# =========================================================

@app.post("/api/inventory")
def create_or_update_inventory(
    data: InventoryCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    product = (
        db.query(Product)
        .filter(Product.id == data.product_id)
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    location = (
        db.query(Location)
        .filter(Location.id == data.location_id)
        .first()
    )

    if not location:
        raise HTTPException(
            status_code=404,
            detail="Location not found"
        )

    inventory = get_inventory_record(
        db=db,
        location_id=data.location_id,
        product_id=data.product_id,
    )

    if inventory:

        inventory.bin_id = data.bin_id
        inventory.available_qty = data.available_qty
        inventory.reserved_qty = data.reserved_qty
        inventory.picked_qty = data.picked_qty
        inventory.packed_qty = data.packed_qty
        inventory.dispatched_qty = data.dispatched_qty
        inventory.damaged_qty = data.damaged_qty
        inventory.returned_qty = data.returned_qty
        inventory.quarantine_qty = data.quarantine_qty

        action = "UPDATE"

    else:

        inventory = Inventory(
            location_id=data.location_id,
            product_id=data.product_id,
            bin_id=data.bin_id,
            available_qty=data.available_qty,
            reserved_qty=data.reserved_qty,
            picked_qty=data.picked_qty,
            packed_qty=data.packed_qty,
            dispatched_qty=data.dispatched_qty,
            damaged_qty=data.damaged_qty,
            returned_qty=data.returned_qty,
            quarantine_qty=data.quarantine_qty,
        )

        db.add(inventory)

        action = "CREATE"

    db.flush()

    create_audit_log(
        db=db,
        employee=employee,
        action=action,
        module="INVENTORY",
        reference_id=inventory.id,
        description=f"Inventory updated for {product.sku}",
    )

    db.commit()
    db.refresh(inventory)

    return as_dict(inventory)


# =========================================================
# STOCK IN
# =========================================================

@app.post("/api/inventory/stock-in")
def stock_in(
    data: StockInRequest,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    if data.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than 0"
        )

    product = (
        db.query(Product)
        .filter(Product.id == data.product_id)
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    location = (
        db.query(Location)
        .filter(Location.id == data.location_id)
        .first()
    )

    if not location:
        raise HTTPException(
            status_code=404,
            detail="Location not found"
        )

    # Validate bin when supplied
    if data.bin_id is not None:

        bin_record = (
            db.query(Bin)
            .filter(
                Bin.id == data.bin_id,
                Bin.location_id == data.location_id,
            )
            .first()
        )

        if not bin_record:
            raise HTTPException(
                status_code=404,
                detail="Bin not found at selected location"
            )

    # IMPORTANT:
    # Use named arguments so product/location cannot be reversed.
    inventory = get_inventory_record(
        db=db,
        location_id=data.location_id,
        product_id=data.product_id,
    )

    # Create inventory record if SKU does not yet exist
    # at this location.
    if inventory is None:

        inventory = Inventory(
            product_id=data.product_id,
            location_id=data.location_id,
            bin_id=data.bin_id,
            available_qty=0,
            reserved_qty=0,
            picked_qty=0,
            packed_qty=0,
            dispatched_qty=0,
            damaged_qty=0,
            returned_qty=0,
            quarantine_qty=0,
        )

        db.add(inventory)
        db.flush()

    elif data.bin_id is not None:

        inventory.bin_id = data.bin_id

    # Add stock
    inventory.available_qty = (
        (inventory.available_qty or 0)
        + data.quantity
    )

    # Create movement
    movement = create_stock_movement(
        db=db,
        product_id=data.product_id,
        location_id=data.location_id,
        movement_type="STOCK_IN",
        quantity=data.quantity,
        reference_number=data.reference_number,
        remarks=data.remarks or "Stock received",
    )

    # Audit
    create_audit_log(
        db=db,
        employee=employee,
        action="STOCK_IN",
        module="INVENTORY",
        reference_id=inventory.id,
        description=(
            f"Added {data.quantity} units of "
            f"{product.sku} to {location.location_name}"
        ),
    )

    db.commit()

    db.refresh(inventory)
    db.refresh(movement)

    return {
        "message": "Stock added successfully",
        "inventory": as_dict(inventory),
        "movement": as_dict(movement),
    }


# =========================================================
# BINS
# =========================================================

@app.get("/api/bins")
def get_bins(
    location_id: int | None = None,
    db: Session = Depends(get_db),
):

    query = db.query(Bin)

    if location_id is not None:
        query = query.filter(
            Bin.location_id == location_id
        )

    bins = (
        query
        .order_by(Bin.id.desc())
        .all()
    )

    result = []

    for bin_record in bins:

        location = (
            db.query(Location)
            .filter(
                Location.id == bin_record.location_id
            )
            .first()
        )

        item = as_dict(bin_record)

        item["location_name"] = (
            location.location_name
            if location
            else None
        )

        result.append(item)

    return result


# =========================================================
# STOCK MOVEMENTS
# =========================================================
class StockMovementCreate(BaseModel):
    product_id: int
    location_id: int
    movement_type: str
    quantity: int
    reference_number: str | None = None
    remarks: str | None = None


def create_stock_movement(
    db: Session,
    product_id: int,
    location_id: int,
    movement_type: str,
    quantity: int,
    reference_number=None,
    remarks=None,
):

    movement = StockMovement(
        product_id=product_id,
        location_id=location_id,
        movement_type=movement_type,
        quantity=quantity,
        reference_number=reference_number,
        remarks=remarks,
        created_at=now(),
    )

    db.add(movement)

    return movement


@app.get("/api/stock-movements")
def get_stock_movements(
    db: Session = Depends(get_db)
):

    movements = (
        db.query(StockMovement)
        .order_by(StockMovement.id.desc())
        .all()
    )

    result = []

    for movement in movements:

        product = (
            db.query(Product)
            .filter(Product.id == movement.product_id)
            .first()
        )

        location = (
            db.query(Location)
            .filter(Location.id == movement.location_id)
            .first()
        )

        item = as_dict(movement)

        item["sku"] = (
            product.sku if product else None
        )

        item["product_name"] = (
            product.product_name if product else None
        )

        item["location_name"] = (
            location.location_name if location else None
        )

        result.append(item)

    return result


@app.post("/api/stock-movements")
def add_stock_movement(
    data: StockMovementCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    product = (
        db.query(Product)
        .filter(Product.id == data.product_id)
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    location = (
        db.query(Location)
        .filter(Location.id == data.location_id)
        .first()
    )

    if not location:
        raise HTTPException(
            status_code=404,
            detail="Location not found"
        )

    inventory = get_inventory_record(
        db,
        data.location_id,
        data.product_id,
    )

    if not inventory:

        inventory = Inventory(
            location_id=data.location_id,
            product_id=data.product_id,
            available_qty=0,
        )

        db.add(inventory)
        db.flush()

    movement_type = data.movement_type.upper()

    if movement_type in [
        "IN",
        "RECEIPT",
        "GRN",
        "PURCHASE",
        "TRANSFER_IN",
    ]:

        inventory.available_qty += data.quantity

    elif movement_type in [
        "OUT",
        "SALE",
        "TRANSFER_OUT",
    ]:

        if inventory.available_qty < data.quantity:
            raise HTTPException(
                status_code=400,
                detail="Insufficient available stock"
            )

        inventory.available_qty -= data.quantity

    elif movement_type == "DAMAGE":

        if inventory.available_qty < data.quantity:
            raise HTTPException(
                status_code=400,
                detail="Insufficient available stock"
            )

        inventory.available_qty -= data.quantity
        inventory.damaged_qty += data.quantity

    elif movement_type == "RETURN":

        inventory.returned_qty += data.quantity
        inventory.available_qty += data.quantity

    movement = create_stock_movement(
        db=db,
        product_id=data.product_id,
        location_id=data.location_id,
        movement_type=data.movement_type,
        quantity=data.quantity,
        reference_number=data.reference_number,
        remarks=data.remarks,
    )

    create_audit_log(
        db=db,
        employee=employee,
        action="CREATE",
        module="STOCK_MOVEMENT",
        reference_id=movement.id,
        description=f"{data.movement_type} stock movement",
    )

    db.commit()
    db.refresh(movement)

    return as_dict(movement)


# =========================================================
# SUPPLIERS
# =========================================================

class SupplierCreate(BaseModel):
    supplier_code: str
    company_name: str
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    gstin: str | None = None
    address: str | None = None
    payment_terms: int = 0
    active: bool = True


@app.get("/api/suppliers")
def get_suppliers(
    db: Session = Depends(get_db)
):

    suppliers = (
        db.query(Supplier)
        .order_by(Supplier.id.desc())
        .all()
    )

    return [as_dict(supplier) for supplier in suppliers]


@app.post("/api/suppliers")
def create_supplier(
    data: SupplierCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    existing = (
        db.query(Supplier)
        .filter(
            Supplier.supplier_code == data.supplier_code
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Supplier code already exists"
        )

    supplier = Supplier(
        supplier_code=data.supplier_code,
        company_name=data.company_name,
        contact_person=data.contact_person,
        phone=data.phone,
        email=data.email,
        gstin=data.gstin,
        address=data.address,
        payment_terms=data.payment_terms,
        active=data.active,
    )

    db.add(supplier)

    create_audit_log(
        db=db,
        employee=employee,
        action="CREATE",
        module="SUPPLIER",
        description=f"Created supplier {data.company_name}",
    )

    db.commit()
    db.refresh(supplier)

    return as_dict(supplier)


@app.put("/api/suppliers/{supplier_id}")
def update_supplier(
    supplier_id: int,
    data: SupplierCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    supplier = (
        db.query(Supplier)
        .filter(Supplier.id == supplier_id)
        .first()
    )

    if not supplier:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found"
        )

    supplier.supplier_code = data.supplier_code
    supplier.company_name = data.company_name
    supplier.contact_person = data.contact_person
    supplier.phone = data.phone
    supplier.email = data.email
    supplier.gstin = data.gstin
    supplier.address = data.address
    supplier.payment_terms = data.payment_terms
    supplier.active = data.active

    create_audit_log(
        db=db,
        employee=employee,
        action="UPDATE",
        module="SUPPLIER",
        reference_id=supplier_id,
        description="Supplier updated",
    )

    db.commit()
    db.refresh(supplier)

    return as_dict(supplier)


@app.get("/api/suppliers/{supplier_id}")
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db)
):

    supplier = (
        db.query(Supplier)
        .filter(Supplier.id == supplier_id)
        .first()
    )

    if not supplier:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found"
        )

    return as_dict(supplier)


@app.delete("/api/suppliers/{supplier_id}")
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    supplier = (
        db.query(Supplier)
        .filter(Supplier.id == supplier_id)
        .first()
    )

    if not supplier:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found"
        )

    supplier.active = False

    create_audit_log(
        db=db,
        employee=employee,
        action="DEACTIVATE",
        module="SUPPLIER",
        reference_id=supplier_id,
        description="Supplier deactivated",
    )

    db.commit()

    return {
        "message": "Supplier deactivated successfully"
    }


# =========================================================
# ORDER SCHEMAS
# =========================================================

class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_price: float | None = None


class OrderCreate(BaseModel):
    customer_name: str
    customer_phone: str | None = None
    delivery_address: str
    city: str | None = None
    location_id: int | None = None
    payment_mode: str = "COD"
    discount: float = 0
    items: list[OrderItemCreate]


class StatusUpdate(BaseModel):
    status: str


class RiderAssign(BaseModel):
    rider_id: int


# =========================================================
# ORDER PRICING
# =========================================================

def calculate_order_pricing(
    items,
    discount=0.0
):

    subtotal = sum(
        item.quantity * item.unit_price
        for item in items
    )

    discount = max(float(discount or 0), 0)

    if discount > subtotal:
        discount = subtotal

    net_subtotal = subtotal - discount

    if net_subtotal <= 0:
        delivery_charge = 0.0
    elif net_subtotal > FREE_DELIVERY_LIMIT:
        delivery_charge = 0.0
    else:
        delivery_charge = DELIVERY_CHARGE

    handling_charge = (
        HANDLING_CHARGE
        if net_subtotal > 0
        else 0.0
    )

    total = (
        net_subtotal
        + delivery_charge
        + handling_charge
    )

    return {
        "subtotal": round(subtotal, 2),
        "delivery_charge": round(delivery_charge, 2),
        "handling_charge": round(handling_charge, 2),
        "discount": round(discount, 2),
        "total_amount": round(total, 2),
    }


# =========================================================
# ORDERS
# =========================================================

@app.get("/api/orders")
def get_orders(
    status: str | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(Order)

    if status:
        query = query.filter(
            Order.status == status
        )

    orders = (
        query
        .order_by(Order.id.desc())
        .all()
    )

    result = []

    for order in orders:

        location = None
        rider = None

        if order.location_id:
            location = (
                db.query(Location)
                .filter(
                    Location.id == order.location_id
                )
                .first()
            )

        if order.rider_id:
            rider = (
                db.query(Rider)
                .filter(
                    Rider.id == order.rider_id
                )
                .first()
            )

        items = (
            db.query(OrderItem)
            .filter(
                OrderItem.order_id == order.id
            )
            .all()
        )

        item_list = [as_dict(item) for item in items]

        item = as_dict(order)

        item["location_name"] = (
            location.location_name
            if location else None
        )

        item["rider_name"] = (
            rider.name
            if rider else None
        )

        item["items"] = item_list

        result.append(item)

    return result


@app.post("/api/orders")
def create_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
):

    if not data.items:
        raise HTTPException(
            status_code=400,
            detail="Order must contain at least one item"
        )

    if data.location_id:

        location = (
            db.query(Location)
            .filter(
                Location.id == data.location_id
            )
            .first()
        )

        if not location:
            raise HTTPException(
                status_code=404,
                detail="Location not found"
            )

    order_number = (
        f"ZORD-{datetime.now().strftime('%Y%m%d')}-"
        f"{secrets.token_hex(3).upper()}"
    )

    while (
        db.query(Order)
        .filter(
            Order.order_number == order_number
        )
        .first()
    ):
        order_number = (
            f"ZORD-{datetime.now().strftime('%Y%m%d')}-"
            f"{secrets.token_hex(3).upper()}"
        )

    prepared_items = []

    for item_data in data.items:

        product = (
            db.query(Product)
            .filter(
                Product.id == item_data.product_id
            )
            .first()
        )

        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Product {item_data.product_id} not found"
            )

        price = (
            item_data.unit_price
            if item_data.unit_price is not None
            else product.selling_price
        )

        prepared_items.append({
            "product": product,
            "quantity": item_data.quantity,
            "unit_price": price,
        })

    class PricingItem:
        def __init__(self, quantity, unit_price):
            self.quantity = quantity
            self.unit_price = unit_price

    pricing_items = [
        PricingItem(
            item["quantity"],
            item["unit_price"]
        )
        for item in prepared_items
    ]

    pricing = calculate_order_pricing(
        pricing_items,
        data.discount
    )

    order = Order(
        order_number=order_number,
        customer_name=data.customer_name,
        customer_phone=data.customer_phone,
        delivery_address=data.delivery_address,
        city=data.city,
        location_id=data.location_id,
        status="NEW",
        payment_mode=data.payment_mode,
        payment_status=(
            "PAID"
            if data.payment_mode.upper() in ["ONLINE", "UPI", "CARD"]
            else "PENDING"
        ),
        subtotal=pricing["subtotal"],
        delivery_charge=pricing["delivery_charge"],
        handling_charge=pricing["handling_charge"],
        discount=pricing["discount"],
        total_amount=pricing["total_amount"],
        rider_id=None,
        created_at=now(),
        updated_at=now(),
    )

    db.add(order)
    db.flush()

    for item in prepared_items:

        product = item["product"]
        quantity = item["quantity"]
        unit_price = item["unit_price"]

        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            sku=product.sku,
            product_name=product.product_name,
            quantity=quantity,
            unit_price=unit_price,
            total_price=round(
                quantity * unit_price,
                2
            ),
            status="NEW",
        )

        db.add(order_item)

    db.commit()
    db.refresh(order)

    return {
        "message": "Order created successfully",
        "order": as_dict(order),
    }


# =========================================================
# ORDER ALLOCATION
# =========================================================

@app.post("/api/orders/{order_id}/allocate")
def allocate_order(
    order_id: int,
    db: Session = Depends(get_db),
):

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    items = (
        db.query(OrderItem)
        .filter(
            OrderItem.order_id == order.id
        )
        .all()
    )

    if not items:
        raise HTTPException(
            status_code=400,
            detail="Order has no items"
        )

    locations = (
        db.query(Location)
        .filter(Location.active == True)
        .all()
    )

    selected_location = None

    for location in locations:

        eligible = True

        for item in items:

            inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.location_id == location.id,
                    Inventory.product_id == item.product_id,
                )
                .first()
            )

            if not inventory:
                eligible = False
                break

            if inventory.available_qty < item.quantity:
                eligible = False
                break

        if eligible:
            selected_location = location
            break

    if not selected_location:
        raise HTTPException(
            status_code=400,
            detail="No location has all required products in stock"
        )

    for item in items:

        inventory = (
            db.query(Inventory)
            .filter(
                Inventory.location_id == selected_location.id,
                Inventory.product_id == item.product_id,
            )
            .first()
        )

        inventory.available_qty -= item.quantity
        inventory.reserved_qty += item.quantity

        item.status = "RESERVED"

    order.location_id = selected_location.id
    order.status = "ALLOCATED"
    order.updated_at = now()

    db.commit()
    db.refresh(order)

    return {
        "message": "Order allocated successfully",
        "order_id": order.id,
        "location_id": selected_location.id,
        "location_name": selected_location.location_name,
        "status": order.status,
    }


# =========================================================
# ORDER STATUS
# =========================================================

@app.put("/api/orders/{order_id}/status")
def update_order_status(
    order_id: int,
    data: StatusUpdate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    order.status = data.status.upper()
    order.updated_at = now()

    create_audit_log(
        db=db,
        employee=employee,
        action="STATUS_UPDATE",
        module="ORDER",
        reference_id=order.id,
        description=f"Order status changed to {order.status}",
    )

    db.commit()
    db.refresh(order)

    return as_dict(order)


# =========================================================
# RIDERS
# =========================================================

class RiderCreate(BaseModel):
    rider_code: str
    name: str
    phone: str | None = None
    vehicle_type: str = "BIKE"
    status: str = "OFFLINE"
    location_id: int | None = None
    active: bool = True


@app.get("/api/riders")
def get_riders(
    db: Session = Depends(get_db)
):

    riders = (
        db.query(Rider)
        .order_by(Rider.id.desc())
        .all()
    )

    result = []

    for rider in riders:

        item = as_dict(rider)

        location = None

        if rider.location_id:
            location = (
                db.query(Location)
                .filter(
                    Location.id == rider.location_id
                )
                .first()
            )

        item["location_name"] = (
            location.location_name
            if location else None
        )

        result.append(item)

    return result


@app.post("/api/riders")
def create_rider(
    data: RiderCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    existing = (
        db.query(Rider)
        .filter(
            Rider.rider_code == data.rider_code
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Rider code already exists"
        )

    rider = Rider(
        rider_code=data.rider_code,
        name=data.name,
        phone=data.phone,
        vehicle_type=data.vehicle_type,
        status=data.status,
        location_id=data.location_id,
        total_deliveries=0,
        active=data.active,
    )

    db.add(rider)

    create_audit_log(
        db=db,
        employee=employee,
        action="CREATE",
        module="RIDER",
        description=f"Created rider {data.rider_code}",
    )

    db.commit()
    db.refresh(rider)

    return as_dict(rider)


# =========================================================
# ASSIGN RIDER
# =========================================================

@app.post("/api/orders/{order_id}/assign-rider")
def assign_rider(
    order_id: int,
    data: RiderAssign,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    rider = (
        db.query(Rider)
        .filter(Rider.id == data.rider_id)
        .first()
    )

    if not rider:
        raise HTTPException(
            status_code=404,
            detail="Rider not found"
        )

    if not rider.active:
        raise HTTPException(
            status_code=400,
            detail="Rider is inactive"
        )

    order.rider_id = rider.id
    order.status = "OUT_FOR_DELIVERY"
    order.updated_at = now()

    rider.status = "BUSY"

    create_audit_log(
        db=db,
        employee=employee,
        action="ASSIGN_RIDER",
        module="ORDER",
        reference_id=order.id,
        description=f"Rider {rider.rider_code} assigned",
    )

    db.commit()

    return {
        "message": "Rider assigned successfully",
        "order_id": order.id,
        "rider_id": rider.id,
        "rider_name": rider.name,
        "status": order.status,
    }


# =========================================================
# RIDER STATUS
# =========================================================

@app.put("/api/riders/{rider_id}/status")
def update_rider_status(
    rider_id: int,
    data: StatusUpdate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    rider = (
        db.query(Rider)
        .filter(Rider.id == rider_id)
        .first()
    )

    if not rider:
        raise HTTPException(
            status_code=404,
            detail="Rider not found"
        )

    rider.status = data.status.upper()

    create_audit_log(
        db=db,
        employee=employee,
        action="STATUS_UPDATE",
        module="RIDER",
        reference_id=rider.id,
        description=f"Rider status changed to {rider.status}",
    )

    db.commit()

    return as_dict(rider)


# =========================================================
# COMPLETE ORDER
# =========================================================

@app.post("/api/orders/{order_id}/complete")
def complete_order(
    order_id: int,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    order.status = "DELIVERED"
    order.updated_at = now()

    if order.rider_id:

        rider = (
            db.query(Rider)
            .filter(Rider.id == order.rider_id)
            .first()
        )

        if rider:

            rider.status = "AVAILABLE"
            rider.total_deliveries += 1

    items = (
        db.query(OrderItem)
        .filter(
            OrderItem.order_id == order.id
        )
        .all()
    )

    for item in items:

        item.status = "DELIVERED"

        if order.location_id:

            inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.location_id == order.location_id,
                    Inventory.product_id == item.product_id,
                )
                .first()
            )

            if inventory:

                inventory.reserved_qty = max(
                    inventory.reserved_qty - item.quantity,
                    0
                )

                inventory.dispatched_qty += item.quantity

    create_audit_log(
        db=db,
        employee=employee,
        action="COMPLETE",
        module="ORDER",
        reference_id=order.id,
        description="Order delivered",
    )

    db.commit()

    return {
        "message": "Order completed successfully",
        "order_id": order.id,
        "status": order.status,
    }


# =========================================================
# PURCHASE ORDERS
# =========================================================

def generate_unique_po_number(db: Session) -> str:

    max_id = (
        db.query(func.max(PurchaseOrder.id))
        .scalar()
        or 0
    )

    candidate = max_id + 1

    while True:

        po_number = f"ZPO-{candidate:06d}"

        existing = (
            db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.po_number == po_number
            )
            .first()
        )

        if not existing:
            return po_number

        candidate += 1


class PurchaseOrderItemCreate(BaseModel):
    product_id: int | None = None
    sku: str | None = None
    product_name: str
    quantity: int = 0
    purchase_price: float = 0
    gst_percent: float = 0
    discount_percent: float = 0


class PurchaseOrderCreate(BaseModel):
    supplier_id: int | None = None
    location_id: int | None = None
    order_date: str | None = None
    expected_date: str | None = None
    status: str = "DRAFT"
    payment_terms: str | None = None
    discount_amount: float = 0
    notes: str | None = None
    items: list[PurchaseOrderItemCreate]


@app.get("/api/purchase-orders")
def get_purchase_orders(
    db: Session = Depends(get_db)
):

    purchase_orders = (
        db.query(PurchaseOrder)
        .order_by(PurchaseOrder.id.desc())
        .all()
    )

    result = []

    for po in purchase_orders:

        supplier = None
        location = None

        if po.supplier_id:
            supplier = (
                db.query(Supplier)
                .filter(
                    Supplier.id == po.supplier_id
                )
                .first()
            )

        if po.location_id:
            location = (
                db.query(Location)
                .filter(
                    Location.id == po.location_id
                )
                .first()
            )

        item = as_dict(po)

        item["supplier_name"] = (
            supplier.company_name
            if supplier else None
        )

        item["location_name"] = (
            location.location_name
            if location else None
        )

        result.append(item)

    return result


@app.post("/api/purchase-orders")
def create_purchase_order(
    data: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    if not data.items:
        raise HTTPException(
            status_code=400,
            detail="Purchase order must contain at least one item"
        )

    if data.supplier_id:

        supplier = (
            db.query(Supplier)
            .filter(
                Supplier.id == data.supplier_id
            )
            .first()
        )

        if not supplier:
            raise HTTPException(
                status_code=404,
                detail="Supplier not found"
            )

    if data.location_id:

        location = (
            db.query(Location)
            .filter(
                Location.id == data.location_id
            )
            .first()
        )

        if not location:
            raise HTTPException(
                status_code=404,
                detail="Location not found"
            )

    po_number = generate_unique_po_number(db)

    order_date = data.order_date or today()

    subtotal = 0.0
    gst_amount = 0.0
    discount_amount = 0.0

    prepared_items = []

    for item in data.items:

        if item.quantity < 0:
            raise HTTPException(
                status_code=400,
                detail="Quantity cannot be negative"
            )

        base = (
            item.quantity
            * item.purchase_price
        )

        discount = (
            base
            * item.discount_percent
            / 100
        )

        taxable = base - discount

        gst = (
            taxable
            * item.gst_percent
            / 100
        )

        line_total = taxable + gst

        subtotal += base
        discount_amount += discount
        gst_amount += gst

        prepared_items.append({
            "data": item,
            "gst_amount": gst,
            "discount_amount": discount,
            "line_total": line_total,
        })

    total_amount = (
        subtotal
        - discount_amount
        + gst_amount
    )

    po = PurchaseOrder(
        po_number=po_number,
        supplier_id=data.supplier_id,
        location_id=data.location_id,
        order_date=order_date,
        expected_date=data.expected_date,
        status=data.status,
        payment_terms=data.payment_terms,
        subtotal=round(subtotal, 2),
        gst_amount=round(gst_amount, 2),
        discount_amount=round(
            discount_amount,
            2
        ),
        total_amount=round(
            total_amount,
            2
        ),
        notes=data.notes,
        created_by=employee.id,
        created_at=now(),
        updated_at=now(),
    )

    db.add(po)
    db.flush()

    for prepared in prepared_items:

        item = prepared["data"]

        po_item = PurchaseOrderItem(
            purchase_order_id=po.id,
            product_id=item.product_id,
            sku=item.sku,
            product_name=item.product_name,
            quantity=item.quantity,
            purchase_price=item.purchase_price,
            gst_percent=item.gst_percent,
            gst_amount=prepared["gst_amount"],
            discount_percent=item.discount_percent,
            discount_amount=prepared["discount_amount"],
            line_total=prepared["line_total"],
            status="OPEN",
        )

        db.add(po_item)

    create_audit_log(
        db=db,
        employee=employee,
        action="CREATE",
        module="PURCHASE_ORDER",
        reference_id=po.id,
        description=f"Created {po_number}",
    )

    db.commit()
    db.refresh(po)

    return {
        "message": "Purchase order created successfully",
        "purchase_order": as_dict(po),
    }


@app.get("/api/purchase-orders/{po_id}")
def get_purchase_order(
    po_id: int,
    db: Session = Depends(get_db)
):

    po = (
        db.query(PurchaseOrder)
        .filter(
            PurchaseOrder.id == po_id
        )
        .first()
    )

    if not po:
        raise HTTPException(
            status_code=404,
            detail="Purchase order not found"
        )

    supplier = None
    location = None

    if po.supplier_id:
        supplier = (
            db.query(Supplier)
            .filter(
                Supplier.id == po.supplier_id
            )
            .first()
        )

    if po.location_id:
        location = (
            db.query(Location)
            .filter(
                Location.id == po.location_id
            )
            .first()
        )

    items = (
        db.query(PurchaseOrderItem)
        .filter(
            PurchaseOrderItem.purchase_order_id == po.id
        )
        .order_by(PurchaseOrderItem.id.asc())
        .all()
    )

    return {
        "purchase_order": as_dict(po),
        "supplier_name": (
            supplier.company_name
            if supplier else None
        ),
        "location_name": (
            location.location_name
            if location else None
        ),
        "items": [
            as_dict(item)
            for item in items
        ],
    }


# =========================================================
# GRN
# =========================================================

def generate_unique_grn_number(
    db: Session
) -> str:

    max_id = (
        db.query(func.max(GoodsReceiptNote.id))
        .scalar()
        or 0
    )

    candidate = max_id + 1

    while True:

        grn_number = f"ZGRN-{candidate:06d}"

        existing = (
            db.query(GoodsReceiptNote)
            .filter(
                GoodsReceiptNote.grn_number
                == grn_number
            )
            .first()
        )

        if not existing:
            return grn_number

        candidate += 1


class GRNItemCreate(BaseModel):
    purchase_order_item_id: int | None = None
    product_id: int | None = None
    sku: str | None = None
    product_name: str
    ordered_quantity: int = 0
    received_quantity: int = 0
    damaged_quantity: int = 0
    accepted_quantity: int = 0
    purchase_price: float = 0
    batch_number: str | None = None
    expiry_date: str | None = None
    qc_status: str = "PENDING"
    notes: str | None = None


class GRNCreate(BaseModel):
    purchase_order_id: int | None = None
    supplier_id: int | None = None
    location_id: int | None = None
    received_date: str | None = None
    received_time: str | None = None
    status: str = "DRAFT"
    qc_status: str = "PENDING"
    notes: str | None = None
    items: list[GRNItemCreate]


@app.get("/api/grn")
def get_grns(
    db: Session = Depends(get_db)
):

    grns = (
        db.query(GoodsReceiptNote)
        .order_by(GoodsReceiptNote.id.desc())
        .all()
    )

    result = []

    for grn in grns:

        supplier = None
        location = None
        po = None

        if grn.supplier_id:

            supplier = (
                db.query(Supplier)
                .filter(
                    Supplier.id == grn.supplier_id
                )
                .first()
            )

        if grn.location_id:

            location = (
                db.query(Location)
                .filter(
                    Location.id == grn.location_id
                )
                .first()
            )

        if grn.purchase_order_id:

            po = (
                db.query(PurchaseOrder)
                .filter(
                    PurchaseOrder.id
                    == grn.purchase_order_id
                )
                .first()
            )

        item = as_dict(grn)

        item["supplier_name"] = (
            supplier.company_name
            if supplier else None
        )

        item["location_name"] = (
            location.location_name
            if location else None
        )

        item["po_number"] = (
            po.po_number
            if po else None
        )

        result.append(item)

    return result


@app.get("/api/grn/{grn_id}")
def get_grn(
    grn_id: int,
    db: Session = Depends(get_db)
):

    grn = (
        db.query(GoodsReceiptNote)
        .filter(
            GoodsReceiptNote.id == grn_id
        )
        .first()
    )

    if not grn:
        raise HTTPException(
            status_code=404,
            detail="GRN not found"
        )

    supplier = None
    location = None
    po = None

    if grn.supplier_id:

        supplier = (
            db.query(Supplier)
            .filter(
                Supplier.id == grn.supplier_id
            )
            .first()
        )

    if grn.location_id:

        location = (
            db.query(Location)
            .filter(
                Location.id == grn.location_id
            )
            .first()
        )

    if grn.purchase_order_id:

        po = (
            db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.id
                == grn.purchase_order_id
            )
            .first()
        )

    items = (
        db.query(GoodsReceiptNoteItem)
        .filter(
            GoodsReceiptNoteItem.grn_id == grn.id
        )
        .order_by(
            GoodsReceiptNoteItem.id.asc()
        )
        .all()
    )

    return {
        "grn": as_dict(grn),
        "grn_number": grn.grn_number,
        "supplier_name": (
            supplier.company_name
            if supplier else None
        ),
        "location_name": (
            location.location_name
            if location else None
        ),
        "po_number": (
            po.po_number
            if po else None
        ),
        "items": [
            as_dict(item)
            for item in items
        ],
    }


@app.get("/api/purchase-orders/{po_id}/grn-data")
def get_po_grn_data(
    po_id: int,
    db: Session = Depends(get_db)
):

    po = (
        db.query(PurchaseOrder)
        .filter(
            PurchaseOrder.id == po_id
        )
        .first()
    )

    if not po:
        raise HTTPException(
            status_code=404,
            detail="Purchase order not found"
        )

    supplier = None

    if po.supplier_id:

        supplier = (
            db.query(Supplier)
            .filter(
                Supplier.id == po.supplier_id
            )
            .first()
        )

    location = None

    if po.location_id:

        location = (
            db.query(Location)
            .filter(
                Location.id == po.location_id
            )
            .first()
        )

    items = (
        db.query(PurchaseOrderItem)
        .filter(
            PurchaseOrderItem.purchase_order_id
            == po.id
        )
        .order_by(
            PurchaseOrderItem.id.asc()
        )
        .all()
    )

    return {
        "purchase_order": as_dict(po),
        "supplier": (
            as_dict(supplier)
            if supplier
            else None
        ),
        "location": (
            as_dict(location)
            if location
            else None
        ),
        "items": [
            as_dict(item)
            for item in items
        ],
    }

@app.post("/api/grn")
def create_grn(
    data: GRNCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):
    if not data.items:
        raise HTTPException(
            status_code=400,
            detail="GRN must contain at least one item"
        )

    try:
        # =================================================
        # 1. GET PURCHASE ORDER
        # =================================================

        po = None

        if data.purchase_order_id:
            po = (
                db.query(PurchaseOrder)
                .filter(
                    PurchaseOrder.id == data.purchase_order_id
                )
                .first()
            )

            if not po:
                raise HTTPException(
                    status_code=404,
                    detail="Purchase order not found"
                )

        # =================================================
        # 2. USE PO DETAILS IF NOT SENT FROM FRONTEND
        # =================================================

        supplier_id = (
            data.supplier_id
            if data.supplier_id is not None
            else (po.supplier_id if po else None)
        )

        location_id = (
            data.location_id
            if data.location_id is not None
            else (po.location_id if po else None)
        )

        if supplier_id:
            supplier = (
                db.query(Supplier)
                .filter(Supplier.id == supplier_id)
                .first()
            )

            if not supplier:
                raise HTTPException(
                    status_code=404,
                    detail="Supplier not found"
                )

        if location_id:
            location = (
                db.query(Location)
                .filter(Location.id == location_id)
                .first()
            )

            if not location:
                raise HTTPException(
                    status_code=404,
                    detail="Location not found"
                )

        if not location_id:
            raise HTTPException(
                status_code=400,
                detail="Location is required for GRN"
            )

        # =================================================
        # 3. CREATE GRN HEADER
        # =================================================

        current_time = now()
        grn_number = generate_unique_grn_number(db)

        grn = GoodsReceiptNote(
            grn_number=grn_number,

            purchase_order_id=(
                po.id if po else data.purchase_order_id
            ),

            supplier_id=supplier_id,

            location_id=location_id,

            received_date=(
                data.received_date
                or today()
            ),

            received_time=(
                data.received_time
                or datetime.now().strftime("%H:%M:%S")
            ),

            status=data.status,

            qc_status=data.qc_status,

            notes=data.notes,

            created_by=employee.id,

            created_at=current_time,

            updated_at=current_time,
        )

        db.add(grn)
        db.flush()

        total_received = 0
        total_accepted = 0
        total_damaged = 0

        # =================================================
        # 4. PROCESS EACH GRN ITEM
        # =================================================

        for item in data.items:

            received_quantity = max(
                int(item.received_quantity or 0),
                0
            )

            damaged_quantity = max(
                int(item.damaged_quantity or 0),
                0
            )

            if damaged_quantity > received_quantity:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Damaged quantity cannot exceed "
                        f"received quantity for "
                        f"{item.product_name}"
                    )
                )

            # Automatically calculate accepted quantity
            # when frontend sends 0.
            if item.accepted_quantity > 0:
                accepted_quantity = int(
                    item.accepted_quantity
                )
            else:
                accepted_quantity = (
                    received_quantity
                    - damaged_quantity
                )

            if accepted_quantity > received_quantity:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Accepted quantity cannot exceed "
                        f"received quantity for "
                        f"{item.product_name}"
                    )
                )

            # =================================================
            # 5. CREATE GRN ITEM
            # =================================================

            grn_item = GoodsReceiptNoteItem(
                grn_id=grn.id,

                purchase_order_item_id=(
                    item.purchase_order_item_id
                ),

                product_id=item.product_id,

                sku=item.sku,

                product_name=item.product_name,

                ordered_quantity=(
                    item.ordered_quantity
                ),

                received_quantity=received_quantity,

                damaged_quantity=damaged_quantity,

                accepted_quantity=accepted_quantity,

                purchase_price=item.purchase_price,

                batch_number=item.batch_number,

                expiry_date=item.expiry_date,

                qc_status=item.qc_status,

                notes=item.notes,
            )

            db.add(grn_item)

            # =================================================
            # 6. UPDATE INVENTORY
            # =================================================

            if item.product_id:

                inventory = get_inventory_record(
                    db=db,
                    location_id=location_id,
                    product_id=item.product_id,
                )

                # Create inventory record if it doesn't exist
                if not inventory:

                    inventory = Inventory(
                        location_id=location_id,
                        product_id=item.product_id,
                        available_qty=0,
                        reserved_qty=0,
                        picked_qty=0,
                        packed_qty=0,
                        dispatched_qty=0,
                        damaged_qty=0,
                        returned_qty=0,
                        quarantine_qty=0,
                    )

                    db.add(inventory)
                    db.flush()

                # ---------------------------------------------
                # ACCEPTED STOCK
                # ---------------------------------------------

                if accepted_quantity > 0:

                    inventory.available_qty = (
                        inventory.available_qty
                        + accepted_quantity
                    )

                    create_stock_movement(
                        db=db,
                        product_id=item.product_id,
                        location_id=location_id,
                        movement_type="GRN",
                        quantity=accepted_quantity,
                        reference_number=grn_number,
                        remarks=(
                            f"Accepted stock received "
                            f"through {grn_number}"
                        ),
                    )

                # ---------------------------------------------
                # DAMAGED STOCK
                # ---------------------------------------------

                if damaged_quantity > 0:

                    inventory.damaged_qty = (
                        inventory.damaged_qty
                        + damaged_quantity
                    )

                    create_stock_movement(
                        db=db,
                        product_id=item.product_id,
                        location_id=location_id,
                        movement_type="DAMAGE",
                        quantity=damaged_quantity,
                        reference_number=grn_number,
                        remarks=(
                            f"Damaged stock received "
                            f"through {grn_number}"
                        ),
                    )

            # =================================================
            # 7. UPDATE PURCHASE ORDER ITEM
            # =================================================

            if item.purchase_order_item_id:

                po_item = (
                    db.query(PurchaseOrderItem)
                    .filter(
                        PurchaseOrderItem.id
                        == item.purchase_order_item_id
                    )
                    .first()
                )

                if po_item:

                    ordered_qty = (
                        po_item.quantity or 0
                    )

                    received_total = (
                        accepted_quantity
                        + damaged_quantity
                    )

                    if received_total >= ordered_qty:
                        po_item.status = "RECEIVED"
                    else:
                        po_item.status = (
                            "PARTIALLY_RECEIVED"
                        )

            total_received += received_quantity
            total_accepted += accepted_quantity
            total_damaged += damaged_quantity

        # =================================================
        # 8. UPDATE PURCHASE ORDER STATUS
        # =================================================

        if po:

            po_items = (
                db.query(PurchaseOrderItem)
                .filter(
                    PurchaseOrderItem.purchase_order_id
                    == po.id
                )
                .all()
            )

            if po_items:

                all_received = all(
                    item.status == "RECEIVED"
                    for item in po_items
                )

                if all_received:
                    po.status = "RECEIVED"
                else:
                    po.status = "PARTIALLY_RECEIVED"

                po.updated_at = current_time

        # =================================================
        # 9. AUDIT LOG
        # =================================================

        create_audit_log(
            db=db,
            employee=employee,
            action="CREATE",
            module="GRN",
            reference_id=grn.id,
            description=(
                f"Created {grn_number}; "
                f"received={total_received}, "
                f"accepted={total_accepted}, "
                f"damaged={total_damaged}"
            ),
        )

        # =================================================
        # 10. SAVE EVERYTHING
        # =================================================

        db.commit()
        db.refresh(grn)

        return {
            "message": "GRN created successfully",

            "grn": as_dict(grn),

            "grn_number": grn_number,

            "purchase_order_id": (
                grn.purchase_order_id
            ),

            "supplier_id": grn.supplier_id,

            "location_id": grn.location_id,

            "total_received_quantity": total_received,

            "total_accepted_quantity": total_accepted,

            "total_damaged_quantity": total_damaged,

            "inventory_updated": True,
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to create GRN: {str(e)}"
        )
# =========================================================
# PUTAWAY
# =========================================================

def generate_unique_putaway_number(db: Session):
    last_task = (
        db.query(PutawayTask)
        .order_by(PutawayTask.id.desc())
        .first()
    )

    next_number = (last_task.id + 1) if last_task else 1

    return f"ZPT-{next_number:06d}"


class PutawayTaskCreate(BaseModel):
    location_id: int
    product_id: int
    quantity: int = Field(gt=0)

    grn_id: int | None = None
    grn_item_id: int | None = None

    assigned_employee_id: int | None = None
    assigned_bin_id: int | None = None

    priority: str = "NORMAL"
    remarks: str | None = None


class PutawayAssignRequest(BaseModel):
    employee_id: int
    bin_id: int


class PutawayScanRequest(BaseModel):
    scanned_sku: str
    scanned_bin_code: str
    confirmed_quantity: int = Field(gt=0)


@app.get("/api/putaway")
def get_putaway_tasks(
    status: str | None = None,
    location_id: int | None = None,
    db: Session = Depends(get_db)
):
    query = db.query(PutawayTask)

    if status:
        query = query.filter(
            PutawayTask.status == status.upper()
        )

    if location_id is not None:
        query = query.filter(
            PutawayTask.location_id == location_id
        )

    tasks = (
        query
        .order_by(PutawayTask.id.desc())
        .all()
    )

    result = []

    for task in tasks:

        item = as_dict(task)

        location = (
            db.query(Location)
            .filter(Location.id == task.location_id)
            .first()
        )

        product = (
            db.query(Product)
            .filter(Product.id == task.product_id)
            .first()
        )

        employee = None

        if task.assigned_employee_id:
            employee = (
                db.query(Employee)
                .filter(
                    Employee.id ==
                    task.assigned_employee_id
                )
                .first()
            )

        bin_record = None

        if task.assigned_bin_id:
            bin_record = (
                db.query(Bin)
                .filter(
                    Bin.id ==
                    task.assigned_bin_id
                )
                .first()
            )

        item["location_name"] = (
            location.location_name
            if location else None
        )

        item["product_name"] = (
            product.product_name
            if product else task.product_name
        )

        item["employee_name"] = (
            employee.full_name
            if employee else None
        )

        item["bin_code"] = (
            bin_record.bin_code
            if bin_record else None
        )

        result.append(item)

    return result


@app.get("/api/putaway/{task_id}")
def get_putaway_task(
    task_id: int,
    db: Session = Depends(get_db)
):
    task = (
        db.query(PutawayTask)
        .filter(PutawayTask.id == task_id)
        .first()
    )

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Putaway task not found"
        )

    return as_dict(task)


@app.post("/api/putaway")
def create_putaway_task(
    data: PutawayTaskCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    location = (
        db.query(Location)
        .filter(Location.id == data.location_id)
        .first()
    )

    if not location:
        raise HTTPException(
            status_code=404,
            detail="Location not found"
        )

    product = (
        db.query(Product)
        .filter(Product.id == data.product_id)
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    assigned_bin = None

    if data.assigned_bin_id:

        assigned_bin = (
            db.query(Bin)
            .filter(
                Bin.id ==
                data.assigned_bin_id
            )
            .first()
        )

        if not assigned_bin:
            raise HTTPException(
                status_code=404,
                detail="Assigned bin not found"
            )

        if assigned_bin.location_id != data.location_id:
            raise HTTPException(
                status_code=400,
                detail="Bin does not belong to selected location"
            )

        if assigned_bin.status != "ACTIVE":
            raise HTTPException(
                status_code=400,
                detail="Assigned bin is not active"
            )

    assigned_employee = None

    if data.assigned_employee_id:

        assigned_employee = (
            db.query(Employee)
            .filter(
                Employee.id ==
                data.assigned_employee_id
            )
            .first()
        )

        if not assigned_employee:
            raise HTTPException(
                status_code=404,
                detail="Assigned employee not found"
            )

    task_number = generate_unique_putaway_number(db)

    status = "PENDING"

    if assigned_employee and assigned_bin:
        status = "ASSIGNED"

    task = PutawayTask(
        task_number=task_number,
        grn_id=data.grn_id,
        grn_item_id=data.grn_item_id,
        location_id=data.location_id,
        product_id=data.product_id,
        sku=product.sku,
        product_name=product.product_name,
        quantity=data.quantity,
        confirmed_quantity=0,
        assigned_employee_id=data.assigned_employee_id,
        assigned_bin_id=data.assigned_bin_id,
        status=status,
        priority=data.priority.upper(),
        remarks=data.remarks,
        created_by=employee.id,
        created_at=now(),
    )

    db.add(task)

    db.flush()

    create_audit_log(
        db=db,
        employee=employee,
        action="CREATE",
        module="PUTAWAY",
        reference_id=task.id,
        description=f"Created putaway task {task.task_number}",
    )

    db.commit()
    db.refresh(task)

    return {
        "message": "Putaway task created successfully",
        "task": as_dict(task),
    }


@app.put("/api/putaway/{task_id}/assign")
def assign_putaway_task(
    task_id: int,
    data: PutawayAssignRequest,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    task = (
        db.query(PutawayTask)
        .filter(PutawayTask.id == task_id)
        .first()
    )

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Putaway task not found"
        )

    assigned_employee = (
        db.query(Employee)
        .filter(Employee.id == data.employee_id)
        .first()
    )

    if not assigned_employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )

    bin_record = (
        db.query(Bin)
        .filter(Bin.id == data.bin_id)
        .first()
    )

    if not bin_record:
        raise HTTPException(
            status_code=404,
            detail="Bin not found"
        )

    if bin_record.location_id != task.location_id:
        raise HTTPException(
            status_code=400,
            detail="Bin does not belong to task location"
        )

    if bin_record.status != "ACTIVE":
        raise HTTPException(
            status_code=400,
            detail="Bin is not active"
        )

    task.assigned_employee_id = assigned_employee.id
    task.assigned_bin_id = bin_record.id
    task.status = "ASSIGNED"
    task.assigned_at = now()

    create_audit_log(
        db=db,
        employee=employee,
        action="ASSIGN",
        module="PUTAWAY",
        reference_id=task.id,
        description=(
            f"Putaway {task.task_number} assigned to "
            f"{assigned_employee.employee_id} "
            f"and bin {bin_record.bin_code}"
        ),
    )

    db.commit()
    db.refresh(task)

    return {
        "message": "Putaway task assigned successfully",
        "task": as_dict(task),
    }


@app.put("/api/putaway/{task_id}/start")
def start_putaway_task(
    task_id: int,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    task = (
        db.query(PutawayTask)
        .filter(PutawayTask.id == task_id)
        .first()
    )

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Putaway task not found"
        )

    if task.status != "ASSIGNED":
        raise HTTPException(
            status_code=400,
            detail="Only assigned tasks can be started"
        )

    if not task.assigned_employee_id:
        raise HTTPException(
            status_code=400,
            detail="Putaway employee is not assigned"
        )

    if not task.assigned_bin_id:
        raise HTTPException(
            status_code=400,
            detail="Putaway bin is not assigned"
        )

    task.status = "IN_PROGRESS"
    task.started_at = now()

    create_audit_log(
        db=db,
        employee=employee,
        action="START",
        module="PUTAWAY",
        reference_id=task.id,
        description=f"Started putaway {task.task_number}",
    )

    db.commit()
    db.refresh(task)

    return {
        "message": "Putaway task started",
        "task": as_dict(task),
    }


@app.post("/api/putaway/{task_id}/complete")
def complete_putaway_task(
    task_id: int,
    data: PutawayScanRequest,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    task = (
        db.query(PutawayTask)
        .filter(PutawayTask.id == task_id)
        .first()
    )

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Putaway task not found"
        )

    if task.status not in ["ASSIGNED", "IN_PROGRESS"]:
        raise HTTPException(
            status_code=400,
            detail="Putaway task cannot be completed"
        )

    if not task.assigned_employee_id:
        raise HTTPException(
            status_code=400,
            detail="No employee assigned"
        )

    if not task.assigned_bin_id:
        raise HTTPException(
            status_code=400,
            detail="No bin assigned"
        )

    if data.scanned_sku.strip().upper() != task.sku.upper():
        raise HTTPException(
            status_code=400,
            detail="SKU scan does not match task SKU"
        )

    bin_record = (
        db.query(Bin)
        .filter(Bin.id == task.assigned_bin_id)
        .first()
    )

    if not bin_record:
        raise HTTPException(
            status_code=404,
            detail="Assigned bin not found"
        )

    if (
        data.scanned_bin_code.strip().upper()
        != bin_record.bin_code.upper()
    ):
        raise HTTPException(
            status_code=400,
            detail="Bin scan does not match assigned bin"
        )

    if data.confirmed_quantity > task.quantity:
        raise HTTPException(
            status_code=400,
            detail="Confirmed quantity cannot exceed task quantity"
        )

    bin_inventory = (
        db.query(BinInventory)
        .filter(
            BinInventory.location_id == task.location_id,
            BinInventory.bin_id == task.assigned_bin_id,
            BinInventory.product_id == task.product_id,
        )
        .first()
    )

    if not bin_inventory:

        bin_inventory = BinInventory(
            location_id=task.location_id,
            bin_id=task.assigned_bin_id,
            product_id=task.product_id,
            sku=task.sku,
            available_qty=0,
            reserved_qty=0,
            picked_qty=0,
            damaged_qty=0,
            quarantine_qty=0,
            created_at=now(),
            updated_at=now(),
        )

        db.add(bin_inventory)
        db.flush()

    bin_inventory.available_qty += data.confirmed_quantity
    bin_inventory.updated_at = now()

    task.confirmed_quantity = data.confirmed_quantity
    task.scanned_sku = data.scanned_sku
    task.scanned_bin_code = data.scanned_bin_code
    task.status = "COMPLETED"
    task.completed_by = employee.id
    task.completed_at = now()

    audit_number = f"ZPA-{task.id:06d}"

    audit_task = PutawayAuditTask(
        task_number=audit_number,
        putaway_task_id=task.id,
        location_id=task.location_id,
        bin_id=task.assigned_bin_id,
        product_id=task.product_id,
        sku=task.sku,
        system_quantity=bin_inventory.available_qty,
        physical_quantity=None,
        variance_quantity=0,
        status="PENDING",
        assigned_employee_id=None,
        verified_by=None,
        reason=None,
        created_at=now(),
        completed_at=None,
    )

    db.add(audit_task)

    create_audit_log(
        db=db,
        employee=employee,
        action="COMPLETE",
        module="PUTAWAY",
        reference_id=task.id,
        description=(
            f"Completed putaway {task.task_number}; "
            f"quantity {data.confirmed_quantity}; "
            f"bin {bin_record.bin_code}"
        ),
    )

    db.commit()

    db.refresh(task)
    db.refresh(bin_inventory)
    db.refresh(audit_task)

    return {
        "message": "Putaway completed successfully",
        "task": as_dict(task),
        "bin_inventory": as_dict(bin_inventory),
        "audit_task_number": audit_task.task_number,
    }


@app.get("/api/putaway-audits")
def get_putaway_audits(
    status: str | None = None,
    location_id: int | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(PutawayAuditTask)

    if status:
        query = query.filter(
            PutawayAuditTask.status == status.upper()
        )

    if location_id is not None:
        query = query.filter(
            PutawayAuditTask.location_id == location_id
        )

    audits = (
        query
        .order_by(PutawayAuditTask.id.desc())
        .all()
    )

    result = []

    for audit in audits:

        item = as_dict(audit)

        bin_record = (
            db.query(Bin)
            .filter(Bin.id == audit.bin_id)
            .first()
        )

        product = (
            db.query(Product)
            .filter(Product.id == audit.product_id)
            .first()
        )

        location = (
            db.query(Location)
            .filter(Location.id == audit.location_id)
            .first()
        )

        item["bin_code"] = (
            bin_record.bin_code
            if bin_record else None
        )

        item["product_name"] = (
            product.product_name
            if product else None
        )

        item["location_name"] = (
            location.location_name
            if location else None
        )

        result.append(item)

    return result
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import secrets


from .database import Base, engine, get_db
from . import models

from .models import (
    Location,
    Product,
    Supplier,
    Inventory,
    StockMovement,
    Bin,
    Order,
    OrderItem,
    Rider,
    Employee,
    Role,
    Permission,
    RolePermission,
    OTPVerification,
    LoginSession,
    AuditLog,
    PurchaseOrder,
    PurchaseOrderItem,
    GoodsReceiptNote,
    GoodsReceiptNoteItem,
)


# =========================================================
# DATABASE
# =========================================================

Base.metadata.create_all(bind=engine)


# =========================================================
# FASTAPI APP
# =========================================================

app = FastAPI(
    title="Zippzo Warehouse Management System",
    version="3.0.0",
    description="Zippzo WMS Backend API"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


FRONTEND_DIR = Path(__file__).resolve().parent / "FRONTEND"


# =========================================================
# CONSTANTS
# =========================================================

DELIVERY_CHARGE = 50.0
HANDLING_CHARGE = 5.0
FREE_DELIVERY_LIMIT = 100.0
SESSION_HOURS = 24


# =========================================================
# GENERAL HELPERS
# =========================================================

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.now().strftime("%Y-%m-%d")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def parse_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    return None
def as_dict(obj):
    if obj is None:
        return None

    result = {}

    for column in obj.__table__.columns:
        # Get the Python attribute value
        value = getattr(obj, column.key, None)

        # Product model:
        # database column "name" -> Python attribute "product_name"
        if hasattr(obj, "product_name") and column.name == "name":
            value = obj.product_name

        # Location model:
        # database column "code" -> Python attribute "location_code"
        elif hasattr(obj, "location_code") and column.name == "code":
            value = obj.location_code

        # Location model:
        # database column "name" -> Python attribute "location_name"
        elif hasattr(obj, "location_name") and column.name == "name":
            value = obj.location_name

        # Supplier model:
        # database column "credit_days" -> Python attribute "payment_terms"
        elif hasattr(obj, "payment_terms") and column.name == "credit_days":
            value = obj.payment_terms

        result[column.name] = value

    return result
def create_audit_log(
    db: Session,
    employee=None,
    action="",
    module="",
    reference_id=None,
    description=None,
    ip_address=None,
):
    log = AuditLog(
        employee_id=employee.id if employee else None,
        employee_name=employee.full_name if employee else None,
        action=action,
        module=module,
        reference_id=str(reference_id) if reference_id is not None else None,
        description=description,
        ip_address=ip_address,
        created_at=now(),
    )

    db.add(log)


# =========================================================
# AUTHENTICATION SCHEMAS
# =========================================================

class LoginRequest(BaseModel):
    identifier: str
    password: str


class LogoutRequest(BaseModel):
    session_token: str


class LoginResponse(BaseModel):
    message: str
    session_token: str
    expires_at: str
    user: dict


# =========================================================
# AUTHENTICATION
# =========================================================

@app.post("/api/auth/login", response_model=LoginResponse)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db)
):

    employee = (
        db.query(Employee)
        .filter(
            (
                (Employee.email == data.identifier)
                | (Employee.employee_id == data.identifier)
                | (Employee.mobile == data.identifier)
            )
        )
        .first()
    )

    if not employee:
        raise HTTPException(
            status_code=401,
            detail="Invalid login credentials"
        )

    if employee.status != "ACTIVE":
        raise HTTPException(
            status_code=403,
            detail="Employee account is not active"
        )

    if not employee.password_hash:
        raise HTTPException(
            status_code=401,
            detail="Password is not configured"
        )

    if hash_password(data.password) != employee.password_hash:
        raise HTTPException(
            status_code=401,
            detail="Invalid login credentials"
        )

    token = generate_session_token()

    expires = datetime.now() + timedelta(hours=SESSION_HOURS)

    session = LoginSession(
        employee_id=employee.id,
        session_token=token,
        login_method="PASSWORD",
        device_name=None,
        ip_address=None,
        expires_at=expires.strftime("%Y-%m-%d %H:%M:%S"),
        revoked=False,
        created_at=now(),
    )

    employee.last_login = now()

    db.add(session)

    create_audit_log(
        db=db,
        employee=employee,
        action="LOGIN",
        module="AUTH",
        description="Employee logged in",
    )

    db.commit()

    return {
        "message": "Login successful",
        "session_token": token,
        "expires_at": expires.strftime("%Y-%m-%d %H:%M:%S"),
        "user": {
            "id": employee.id,
            "employee_id": employee.employee_id,
            "full_name": employee.full_name,
            "email": employee.email,
            "mobile": employee.mobile,
            "role": employee.role,
            "department": employee.department,
            "location_id": employee.location_id,
            "status": employee.status,
        },
    }


def get_current_employee(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization required"
        )

    token = authorization

    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

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
            detail="Invalid session"
        )

    expiry = parse_datetime(session.expires_at)

    if expiry and datetime.now() > expiry:
        session.revoked = True
        db.commit()

        raise HTTPException(
            status_code=401,
            detail="Session expired"
        )

    employee = (
        db.query(Employee)
        .filter(Employee.id == session.employee_id)
        .first()
    )

    if not employee:
        raise HTTPException(
            status_code=401,
            detail="Employee not found"
        )

    return employee


@app.get("/api/auth/me")
def auth_me(
    employee: Employee = Depends(get_current_employee)
):

    return {
        "authenticated": True,
        "user": {
            "id": employee.id,
            "employee_id": employee.employee_id,
            "full_name": employee.full_name,
            "email": employee.email,
            "mobile": employee.mobile,
            "role": employee.role,
            "department": employee.department,
            "location_id": employee.location_id,
            "status": employee.status,
        },
    }


@app.post("/api/auth/logout")
def logout(
    data: LogoutRequest,
    db: Session = Depends(get_db)
):

    session = (
        db.query(LoginSession)
        .filter(
            LoginSession.session_token == data.session_token
        )
        .first()
    )

    if session:
        session.revoked = True

        employee = (
            db.query(Employee)
            .filter(Employee.id == session.employee_id)
            .first()
        )

        create_audit_log(
            db=db,
            employee=employee,
            action="LOGOUT",
            module="AUTH",
            description="Employee logged out",
        )

        db.commit()

    return {
        "message": "Logout successful"
    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/api/health")
def health():
    return {
        "status": "OK",
        "application": "Zippzo WMS",
        "version": "3.0.0",
        "time": now(),
    }


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():

    index_file = FRONTEND_DIR / "index.html"

    if index_file.exists():
        return FileResponse(index_file)

    return {
        "application": "Zippzo Warehouse Management System",
        "status": "running",
        "version": "3.0.0",
    }


@app.get("/purchase-orders.html")
def purchase_orders_page():

    file = FRONTEND_DIR / "purchase-orders.html"

    if file.exists():
        return FileResponse(file)

    raise HTTPException(
        status_code=404,
        detail="Purchase Orders page not found"
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.get("/api/dashboard")
def dashboard(
    db: Session = Depends(get_db)
):

    total_products = db.query(Product).count()
    total_locations = db.query(Location).count()
    total_inventory = db.query(Inventory).count()
    total_orders = db.query(Order).count()
    total_riders = db.query(Rider).count()
    total_suppliers = db.query(Supplier).count()
    total_purchase_orders = db.query(PurchaseOrder).count()
    total_grns = db.query(GoodsReceiptNote).count()

    available_stock = (
        db.query(func.coalesce(func.sum(Inventory.available_qty), 0))
        .scalar()
        or 0
    )

    order_value = (
        db.query(func.coalesce(func.sum(Order.total_amount), 0))
        .scalar()
        or 0
    )

    return {
        "total_products": total_products,
        "total_locations": total_locations,
        "total_inventory_records": total_inventory,
        "total_stock": available_stock,
        "total_orders": total_orders,
        "total_riders": total_riders,
        "total_suppliers": total_suppliers,
        "total_purchase_orders": total_purchase_orders,
        "total_grns": total_grns,
        "total_order_value": order_value,
    }


# =========================================================
# PRODUCT SCHEMA
# =========================================================

class ProductCreate(BaseModel):
    sku: str
    barcode: str | None = None
    image_url: str | None = None
    product_name: str
    category: str | None = None
    brand: str | None = None
    uom: str = "PCS"
    mrp: float = 0
    selling_price: float = 0
    purchase_price: float = 0
    gst_percent: float = 0
    weight: float = 0
    reorder_level: int = 0
    minimum_stock: int = 0
    maximum_stock: int = 0
    active: bool = True


@app.get("/api/products")
def get_products(
    db: Session = Depends(get_db)
):

    products = (
        db.query(Product)
        .order_by(Product.id.desc())
        .all()
    )

    return [as_dict(product) for product in products]


@app.post("/api/products")
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    existing = (
        db.query(Product)
        .filter(Product.sku == data.sku)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="SKU already exists"
        )

    product = Product(
        sku=data.sku,
        barcode=data.barcode,
        image_url=data.image_url,
        product_name=data.product_name,
        category=data.category,
        brand=data.brand,
        uom=data.uom,
        mrp=data.mrp,
        selling_price=data.selling_price,
        purchase_price=data.purchase_price,
        gst_percent=data.gst_percent,
        weight=data.weight,
        reorder_level=data.reorder_level,
        minimum_stock=data.minimum_stock,
        maximum_stock=data.maximum_stock,
        active=data.active,
    )

    db.add(product)

    create_audit_log(
        db=db,
        employee=employee,
        action="CREATE",
        module="PRODUCT",
        description=f"Created product {data.sku}",
    )

    db.commit()
    db.refresh(product)

    return as_dict(product)


# =========================================================
# LOCATION SCHEMA
# =========================================================

class LocationCreate(BaseModel):
    location_code: str
    location_name: str
    location_type: str
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    manager_name: str | None = None
    capacity: int = 0
    active: bool = True


@app.get("/api/locations")
def get_locations(
    db: Session = Depends(get_db)
):

    locations = (
        db.query(Location)
        .order_by(Location.id.desc())
        .all()
    )

    return [as_dict(location) for location in locations]


@app.post("/api/locations")
def create_location(
    data: LocationCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    existing = (
        db.query(Location)
        .filter(Location.location_code == data.location_code)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Location code already exists"
        )

    location = Location(
        location_code=data.location_code,
        location_name=data.location_name,
        location_type=data.location_type,
        address=data.address,
        city=data.city,
        state=data.state,
        pincode=data.pincode,
        manager_name=data.manager_name,
        capacity=data.capacity,
        active=data.active,
    )

    db.add(location)

    create_audit_log(
        db=db,
        employee=employee,
        action="CREATE",
        module="LOCATION",
        description=f"Created location {data.location_code}",
    )

    db.commit()
    db.refresh(location)

    return as_dict(location)


# =========================================================
# INVENTORY
# =========================================================
class StockInRequest(BaseModel):
    product_id: int
    location_id: int
    bin_id: int | None = None
    quantity: int
    reference_number: str | None = None
    remarks: str | None = None


class StockTransferRequest(BaseModel):
    product_id: int
    from_location_id: int
    to_location_id: int
    quantity: int
    from_bin_id: int | None = None
    to_bin_id: int | None = None
    reference_number: str | None = None
    remarks: str | None = None


class StockAdjustmentRequest(BaseModel):
    product_id: int
    location_id: int
    quantity: int
    bin_id: int | None = None
    reason: str
    reference_number: str | None = None

class InventoryCreate(BaseModel):
    location_id: int
    product_id: int
    bin_id: int | None = None
    available_qty: int = 0
    reserved_qty: int = 0
    picked_qty: int = 0
    packed_qty: int = 0
    dispatched_qty: int = 0
    damaged_qty: int = 0
    returned_qty: int = 0
    quarantine_qty: int = 0


def get_inventory_record(
    db: Session,
    location_id: int,
    product_id: int,
):

    return (
        db.query(Inventory)
        .filter(
            Inventory.location_id == location_id,
            Inventory.product_id == product_id,
        )
        .first()
    )


@app.get("/api/inventory")
def get_inventory(
    location_id: int | None = None,
    product_id: int | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(Inventory)

    if location_id is not None:
        query = query.filter(
            Inventory.location_id == location_id
        )

    if product_id is not None:
        query = query.filter(
            Inventory.product_id == product_id
        )

    records = query.order_by(Inventory.id.desc()).all()

    result = []

    for inventory in records:

        product = (
            db.query(Product)
            .filter(Product.id == inventory.product_id)
            .first()
        )

        location = (
            db.query(Location)
            .filter(Location.id == inventory.location_id)
            .first()
        )

        bin_record = None

        if inventory.bin_id:
            bin_record = (
                db.query(Bin)
                .filter(Bin.id == inventory.bin_id)
                .first()
            )

        item = as_dict(inventory)

        item["product_name"] = (
            product.product_name if product else None
        )

        item["sku"] = (
            product.sku if product else None
        )

        item["location_name"] = (
            location.location_name if location else None
        )

        item["bin_code"] = (
            bin_record.bin_code if bin_record else None
        )

        result.append(item)

    return result


@app.post("/api/inventory")
def create_or_update_inventory(
    data: InventoryCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    product = (
        db.query(Product)
        .filter(Product.id == data.product_id)
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    location = (
        db.query(Location)
        .filter(Location.id == data.location_id)
        .first()
    )

    if not location:
        raise HTTPException(
            status_code=404,
            detail="Location not found"
        )

    inventory = get_inventory_record(
        db,
        data.location_id,
        data.product_id,
    )

    if inventory:

        inventory.bin_id = data.bin_id
        inventory.available_qty = data.available_qty
        inventory.reserved_qty = data.reserved_qty
        inventory.picked_qty = data.picked_qty
        inventory.packed_qty = data.packed_qty
        inventory.dispatched_qty = data.dispatched_qty
        inventory.damaged_qty = data.damaged_qty
        inventory.returned_qty = data.returned_qty
        inventory.quarantine_qty = data.quarantine_qty

        action = "UPDATE"

    else:

        inventory = Inventory(
            location_id=data.location_id,
            product_id=data.product_id,
            bin_id=data.bin_id,
            available_qty=data.available_qty,
            reserved_qty=data.reserved_qty,
            picked_qty=data.picked_qty,
            packed_qty=data.packed_qty,
            dispatched_qty=data.dispatched_qty,
            damaged_qty=data.damaged_qty,
            returned_qty=data.returned_qty,
            quarantine_qty=data.quarantine_qty,
        )

        db.add(inventory)

        action = "CREATE"

    create_audit_log(
        db=db,
        employee=employee,
        action=action,
        module="INVENTORY",
        reference_id=inventory.id,
        description=f"Inventory updated for {product.sku}",
    )

    db.commit()
    db.refresh(inventory)

    return as_dict(inventory)


# =========================================================
# BINS
# =========================================================
class StockInRequest(BaseModel):
    product_id: int
    location_id: int
    bin_id: int | None = None
    quantity: int
    reference_number: str | None = None
    remarks: str | None = None


@app.post("/api/inventory/stock-in")
def stock_in(
    data: StockInRequest,
    db: Session = Depends(get_db)
):
    if data.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than 0"
        )

    product = db.query(Product).filter(
        Product.id == data.product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    location = db.query(Location).filter(
        Location.id == data.location_id
    ).first()

    if not location:
        raise HTTPException(
            status_code=404,
            detail="Location not found"
        )

    inventory = get_inventory_record(
        db,
        data.product_id,
        data.location_id
    )

    if inventory is None:
        inventory = Inventory(
            product_id=data.product_id,
            location_id=data.location_id,
            bin_id=data.bin_id,
            available_qty=0,
            reserved_qty=0,
            picked_qty=0,
            packed_qty=0,
            dispatched_qty=0,
            damaged_qty=0,
            returned_qty=0,
            quarantine_qty=0
        )

        db.add(inventory)
        db.flush()

    elif data.bin_id is not None:
        inventory.bin_id = data.bin_id

    inventory.available_qty = (
        inventory.available_qty + data.quantity
    )

    movement = create_stock_movement(
        db,
        data.product_id,
        data.location_id,
        "STOCK_IN",
        data.quantity,
        data.reference_number,
        data.remarks or "Stock received"
    )

    db.commit()

    db.refresh(inventory)

    if movement is not None:
        db.refresh(movement)

    return {
        "message": "Stock added successfully",
        "inventory": as_dict(inventory),
        "movement": as_dict(movement)
    }


@app.get("/api/bins")
def get_inventory_record(
    db,
    product_id: int,
    location_id: int
):
    inventory = (
        db.query(Inventory)
        .filter(
            Inventory.product_id == product_id,
            Inventory.location_id == location_id
        )
        .first()
    )

    if inventory:
        return inventory

    inventory = Inventory(
        product_id=product_id,
        location_id=location_id,
        bin_id=None,
        available_qty=0,
        reserved_qty=0,
        picked_qty=0,
        packed_qty=0,
        dispatched_qty=0,
        damaged_qty=0,
        returned_qty=0,
        quarantine_qty=0
    )

    db.add(inventory)
    db.flush()

    return inventory

    query = db.query(Bin)

    if location_id is not None:
        query = query.filter(
            Bin.location_id == location_id
        )

    bins = query.order_by(Bin.id.desc()).all()

    result = []

    for bin_record in bins:

        location = (
            db.query(Location)
            .filter(Location.id == bin_record.location_id)
            .first()
        )

        item = as_dict(bin_record)

        item["location_name"] = (
            location.location_name if location else None
        )

        result.append(item)

    return result


# =========================================================
# STOCK MOVEMENTS
# =========================================================

class StockMovementCreate(BaseModel):
    product_id: int
    location_id: int
    movement_type: str
    quantity: int
    reference_number: str | None = None
    remarks: str | None = None


def create_stock_movement(
    db: Session,
    product_id: int,
    location_id: int,
    movement_type: str,
    quantity: int,
    reference_number=None,
    remarks=None,
):

    movement = StockMovement(
        product_id=product_id,
        location_id=location_id,
        movement_type=movement_type,
        quantity=quantity,
        reference_number=reference_number,
        remarks=remarks,
        created_at=now(),
    )

    db.add(movement)

    return movement


@app.get("/api/stock-movements")
def get_stock_movements(
    db: Session = Depends(get_db)
):

    movements = (
        db.query(StockMovement)
        .order_by(StockMovement.id.desc())
        .all()
    )

    result = []

    for movement in movements:

        product = (
            db.query(Product)
            .filter(Product.id == movement.product_id)
            .first()
        )

        location = (
            db.query(Location)
            .filter(Location.id == movement.location_id)
            .first()
        )

        item = as_dict(movement)

        item["sku"] = (
            product.sku if product else None
        )

        item["product_name"] = (
            product.product_name if product else None
        )

        item["location_name"] = (
            location.location_name if location else None
        )

        result.append(item)

    return result


@app.post("/api/stock-movements")
def add_stock_movement(
    data: StockMovementCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    product = (
        db.query(Product)
        .filter(Product.id == data.product_id)
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    location = (
        db.query(Location)
        .filter(Location.id == data.location_id)
        .first()
    )

    if not location:
        raise HTTPException(
            status_code=404,
            detail="Location not found"
        )

    inventory = get_inventory_record(
        db,
        data.location_id,
        data.product_id,
    )

    if not inventory:

        inventory = Inventory(
            location_id=data.location_id,
            product_id=data.product_id,
            available_qty=0,
        )

        db.add(inventory)
        db.flush()

    movement_type = data.movement_type.upper()

    if movement_type in [
        "IN",
        "RECEIPT",
        "GRN",
        "PURCHASE",
        "TRANSFER_IN",
    ]:

        inventory.available_qty += data.quantity

    elif movement_type in [
        "OUT",
        "SALE",
        "TRANSFER_OUT",
    ]:

        if inventory.available_qty < data.quantity:
            raise HTTPException(
                status_code=400,
                detail="Insufficient available stock"
            )

        inventory.available_qty -= data.quantity

    elif movement_type == "DAMAGE":

        if inventory.available_qty < data.quantity:
            raise HTTPException(
                status_code=400,
                detail="Insufficient available stock"
            )

        inventory.available_qty -= data.quantity
        inventory.damaged_qty += data.quantity

    elif movement_type == "RETURN":

        inventory.returned_qty += data.quantity
        inventory.available_qty += data.quantity

    movement = create_stock_movement(
        db=db,
        product_id=data.product_id,
        location_id=data.location_id,
        movement_type=data.movement_type,
        quantity=data.quantity,
        reference_number=data.reference_number,
        remarks=data.remarks,
    )

    create_audit_log(
        db=db,
        employee=employee,
        action="CREATE",
        module="STOCK_MOVEMENT",
        reference_id=movement.id,
        description=f"{data.movement_type} stock movement",
    )

    db.commit()
    db.refresh(movement)

    return as_dict(movement)


# =========================================================
# SUPPLIERS
# =========================================================

class SupplierCreate(BaseModel):
    supplier_code: str
    company_name: str
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    gstin: str | None = None
    address: str | None = None
    payment_terms: int = 0
    active: bool = True


@app.get("/api/suppliers")
def get_suppliers(
    db: Session = Depends(get_db)
):

    suppliers = (
        db.query(Supplier)
        .order_by(Supplier.id.desc())
        .all()
    )

    return [as_dict(supplier) for supplier in suppliers]


@app.post("/api/suppliers")
def create_supplier(
    data: SupplierCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    existing = (
        db.query(Supplier)
        .filter(
            Supplier.supplier_code == data.supplier_code
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Supplier code already exists"
        )

    supplier = Supplier(
        supplier_code=data.supplier_code,
        company_name=data.company_name,
        contact_person=data.contact_person,
        phone=data.phone,
        email=data.email,
        gstin=data.gstin,
        address=data.address,
        payment_terms=data.payment_terms,
        active=data.active,
    )

    db.add(supplier)

    create_audit_log(
        db=db,
        employee=employee,
        action="CREATE",
        module="SUPPLIER",
        description=f"Created supplier {data.company_name}",
    )

    db.commit()
    db.refresh(supplier)

    return as_dict(supplier)


@app.put("/api/suppliers/{supplier_id}")
def update_supplier(
    supplier_id: int,
    data: SupplierCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    supplier = (
        db.query(Supplier)
        .filter(Supplier.id == supplier_id)
        .first()
    )

    if not supplier:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found"
        )

    supplier.supplier_code = data.supplier_code
    supplier.company_name = data.company_name
    supplier.contact_person = data.contact_person
    supplier.phone = data.phone
    supplier.email = data.email
    supplier.gstin = data.gstin
    supplier.address = data.address
    supplier.payment_terms = data.payment_terms
    supplier.active = data.active

    create_audit_log(
        db=db,
        employee=employee,
        action="UPDATE",
        module="SUPPLIER",
        reference_id=supplier_id,
        description="Supplier updated",
    )

    db.commit()
    db.refresh(supplier)

    return as_dict(supplier)


@app.get("/api/suppliers/{supplier_id}")
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db)
):

    supplier = (
        db.query(Supplier)
        .filter(Supplier.id == supplier_id)
        .first()
    )

    if not supplier:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found"
        )

    return as_dict(supplier)


@app.delete("/api/suppliers/{supplier_id}")
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    supplier = (
        db.query(Supplier)
        .filter(Supplier.id == supplier_id)
        .first()
    )

    if not supplier:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found"
        )

    supplier.active = False

    create_audit_log(
        db=db,
        employee=employee,
        action="DEACTIVATE",
        module="SUPPLIER",
        reference_id=supplier_id,
        description="Supplier deactivated",
    )

    db.commit()

    return {
        "message": "Supplier deactivated successfully"
    }


# =========================================================
# ORDER SCHEMAS
# =========================================================

class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_price: float | None = None


class OrderCreate(BaseModel):
    customer_name: str
    customer_phone: str | None = None
    delivery_address: str
    city: str | None = None
    location_id: int | None = None
    payment_mode: str = "COD"
    discount: float = 0
    items: list[OrderItemCreate]


class StatusUpdate(BaseModel):
    status: str


class RiderAssign(BaseModel):
    rider_id: int


# =========================================================
# ORDER PRICING
# =========================================================

def calculate_order_pricing(
    items,
    discount=0.0
):

    subtotal = sum(
        item.quantity * item.unit_price
        for item in items
    )

    discount = max(float(discount or 0), 0)

    if discount > subtotal:
        discount = subtotal

    net_subtotal = subtotal - discount

    if net_subtotal <= 0:
        delivery_charge = 0.0
    elif net_subtotal > FREE_DELIVERY_LIMIT:
        delivery_charge = 0.0
    else:
        delivery_charge = DELIVERY_CHARGE

    handling_charge = (
        HANDLING_CHARGE
        if net_subtotal > 0
        else 0.0
    )

    total = (
        net_subtotal
        + delivery_charge
        + handling_charge
    )

    return {
        "subtotal": round(subtotal, 2),
        "delivery_charge": round(delivery_charge, 2),
        "handling_charge": round(handling_charge, 2),
        "discount": round(discount, 2),
        "total_amount": round(total, 2),
    }


# =========================================================
# ORDERS
# =========================================================

@app.get("/api/orders")
def get_orders(
    status: str | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(Order)

    if status:
        query = query.filter(
            Order.status == status
        )

    orders = (
        query
        .order_by(Order.id.desc())
        .all()
    )

    result = []

    for order in orders:

        location = None
        rider = None

        if order.location_id:
            location = (
                db.query(Location)
                .filter(
                    Location.id == order.location_id
                )
                .first()
            )

        if order.rider_id:
            rider = (
                db.query(Rider)
                .filter(
                    Rider.id == order.rider_id
                )
                .first()
            )

        items = (
            db.query(OrderItem)
            .filter(
                OrderItem.order_id == order.id
            )
            .all()
        )

        item_list = [as_dict(item) for item in items]

        item = as_dict(order)

        item["location_name"] = (
            location.location_name
            if location else None
        )

        item["rider_name"] = (
            rider.name
            if rider else None
        )

        item["items"] = item_list

        result.append(item)

    return result


@app.post("/api/orders")
def create_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
):

    if not data.items:
        raise HTTPException(
            status_code=400,
            detail="Order must contain at least one item"
        )

    if data.location_id:

        location = (
            db.query(Location)
            .filter(
                Location.id == data.location_id
            )
            .first()
        )

        if not location:
            raise HTTPException(
                status_code=404,
                detail="Location not found"
            )

    order_number = (
        f"ZORD-{datetime.now().strftime('%Y%m%d')}-"
        f"{secrets.token_hex(3).upper()}"
    )

    while (
        db.query(Order)
        .filter(
            Order.order_number == order_number
        )
        .first()
    ):
        order_number = (
            f"ZORD-{datetime.now().strftime('%Y%m%d')}-"
            f"{secrets.token_hex(3).upper()}"
        )

    prepared_items = []

    for item_data in data.items:

        product = (
            db.query(Product)
            .filter(
                Product.id == item_data.product_id
            )
            .first()
        )

        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Product {item_data.product_id} not found"
            )

        price = (
            item_data.unit_price
            if item_data.unit_price is not None
            else product.selling_price
        )

        prepared_items.append({
            "product": product,
            "quantity": item_data.quantity,
            "unit_price": price,
        })

    class PricingItem:
        def __init__(self, quantity, unit_price):
            self.quantity = quantity
            self.unit_price = unit_price

    pricing_items = [
        PricingItem(
            item["quantity"],
            item["unit_price"]
        )
        for item in prepared_items
    ]

    pricing = calculate_order_pricing(
        pricing_items,
        data.discount
    )

    order = Order(
        order_number=order_number,
        customer_name=data.customer_name,
        customer_phone=data.customer_phone,
        delivery_address=data.delivery_address,
        city=data.city,
        location_id=data.location_id,
        status="NEW",
        payment_mode=data.payment_mode,
        payment_status=(
            "PAID"
            if data.payment_mode.upper() in ["ONLINE", "UPI", "CARD"]
            else "PENDING"
        ),
        subtotal=pricing["subtotal"],
        delivery_charge=pricing["delivery_charge"],
        handling_charge=pricing["handling_charge"],
        discount=pricing["discount"],
        total_amount=pricing["total_amount"],
        rider_id=None,
        created_at=now(),
        updated_at=now(),
    )

    db.add(order)
    db.flush()

    for item in prepared_items:

        product = item["product"]
        quantity = item["quantity"]
        unit_price = item["unit_price"]

        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            sku=product.sku,
            product_name=product.product_name,
            quantity=quantity,
            unit_price=unit_price,
            total_price=round(
                quantity * unit_price,
                2
            ),
            status="NEW",
        )

        db.add(order_item)

    db.commit()
    db.refresh(order)

    return {
        "message": "Order created successfully",
        "order": as_dict(order),
    }


# =========================================================
# ORDER ALLOCATION
# =========================================================

@app.post("/api/orders/{order_id}/allocate")
def allocate_order(
    order_id: int,
    db: Session = Depends(get_db),
):

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    items = (
        db.query(OrderItem)
        .filter(
            OrderItem.order_id == order.id
        )
        .all()
    )

    if not items:
        raise HTTPException(
            status_code=400,
            detail="Order has no items"
        )

    locations = (
        db.query(Location)
        .filter(Location.active == True)
        .all()
    )

    selected_location = None

    for location in locations:

        eligible = True

        for item in items:

            inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.location_id == location.id,
                    Inventory.product_id == item.product_id,
                )
                .first()
            )

            if not inventory:
                eligible = False
                break

            if inventory.available_qty < item.quantity:
                eligible = False
                break

        if eligible:
            selected_location = location
            break

    if not selected_location:
        raise HTTPException(
            status_code=400,
            detail="No location has all required products in stock"
        )

    for item in items:

        inventory = (
            db.query(Inventory)
            .filter(
                Inventory.location_id == selected_location.id,
                Inventory.product_id == item.product_id,
            )
            .first()
        )

        inventory.available_qty -= item.quantity
        inventory.reserved_qty += item.quantity

        item.status = "RESERVED"

    order.location_id = selected_location.id
    order.status = "ALLOCATED"
    order.updated_at = now()

    db.commit()
    db.refresh(order)

    return {
        "message": "Order allocated successfully",
        "order_id": order.id,
        "location_id": selected_location.id,
        "location_name": selected_location.location_name,
        "status": order.status,
    }


# =========================================================
# ORDER STATUS
# =========================================================

@app.put("/api/orders/{order_id}/status")
def update_order_status(
    order_id: int,
    data: StatusUpdate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    order.status = data.status.upper()
    order.updated_at = now()

    create_audit_log(
        db=db,
        employee=employee,
        action="STATUS_UPDATE",
        module="ORDER",
        reference_id=order.id,
        description=f"Order status changed to {order.status}",
    )

    db.commit()
    db.refresh(order)

    return as_dict(order)


# =========================================================
# RIDERS
# =========================================================

class RiderCreate(BaseModel):
    rider_code: str
    name: str
    phone: str | None = None
    vehicle_type: str = "BIKE"
    status: str = "OFFLINE"
    location_id: int | None = None
    active: bool = True


@app.get("/api/riders")
def get_riders(
    db: Session = Depends(get_db)
):

    riders = (
        db.query(Rider)
        .order_by(Rider.id.desc())
        .all()
    )

    result = []

    for rider in riders:

        item = as_dict(rider)

        location = None

        if rider.location_id:
            location = (
                db.query(Location)
                .filter(
                    Location.id == rider.location_id
                )
                .first()
            )

        item["location_name"] = (
            location.location_name
            if location else None
        )

        result.append(item)

    return result


@app.post("/api/riders")
def create_rider(
    data: RiderCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    existing = (
        db.query(Rider)
        .filter(
            Rider.rider_code == data.rider_code
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Rider code already exists"
        )

    rider = Rider(
        rider_code=data.rider_code,
        name=data.name,
        phone=data.phone,
        vehicle_type=data.vehicle_type,
        status=data.status,
        location_id=data.location_id,
        total_deliveries=0,
        active=data.active,
    )

    db.add(rider)

    create_audit_log(
        db=db,
        employee=employee,
        action="CREATE",
        module="RIDER",
        description=f"Created rider {data.rider_code}",
    )

    db.commit()
    db.refresh(rider)

    return as_dict(rider)


# =========================================================
# ASSIGN RIDER
# =========================================================

@app.post("/api/orders/{order_id}/assign-rider")
def assign_rider(
    order_id: int,
    data: RiderAssign,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    rider = (
        db.query(Rider)
        .filter(Rider.id == data.rider_id)
        .first()
    )

    if not rider:
        raise HTTPException(
            status_code=404,
            detail="Rider not found"
        )

    if not rider.active:
        raise HTTPException(
            status_code=400,
            detail="Rider is inactive"
        )

    order.rider_id = rider.id
    order.status = "OUT_FOR_DELIVERY"
    order.updated_at = now()

    rider.status = "BUSY"

    create_audit_log(
        db=db,
        employee=employee,
        action="ASSIGN_RIDER",
        module="ORDER",
        reference_id=order.id,
        description=f"Rider {rider.rider_code} assigned",
    )

    db.commit()

    return {
        "message": "Rider assigned successfully",
        "order_id": order.id,
        "rider_id": rider.id,
        "rider_name": rider.name,
        "status": order.status,
    }


# =========================================================
# RIDER STATUS
# =========================================================

@app.put("/api/riders/{rider_id}/status")
def update_rider_status(
    rider_id: int,
    data: StatusUpdate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    rider = (
        db.query(Rider)
        .filter(Rider.id == rider_id)
        .first()
    )

    if not rider:
        raise HTTPException(
            status_code=404,
            detail="Rider not found"
        )

    rider.status = data.status.upper()

    create_audit_log(
        db=db,
        employee=employee,
        action="STATUS_UPDATE",
        module="RIDER",
        reference_id=rider.id,
        description=f"Rider status changed to {rider.status}",
    )

    db.commit()

    return as_dict(rider)


# =========================================================
# COMPLETE ORDER
# =========================================================

@app.post("/api/orders/{order_id}/complete")
def complete_order(
    order_id: int,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    order.status = "DELIVERED"
    order.updated_at = now()

    if order.rider_id:

        rider = (
            db.query(Rider)
            .filter(Rider.id == order.rider_id)
            .first()
        )

        if rider:

            rider.status = "AVAILABLE"
            rider.total_deliveries += 1

    items = (
        db.query(OrderItem)
        .filter(
            OrderItem.order_id == order.id
        )
        .all()
    )

    for item in items:

        item.status = "DELIVERED"

        if order.location_id:

            inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.location_id == order.location_id,
                    Inventory.product_id == item.product_id,
                )
                .first()
            )

            if inventory:

                inventory.reserved_qty = max(
                    inventory.reserved_qty - item.quantity,
                    0
                )

                inventory.dispatched_qty += item.quantity

    create_audit_log(
        db=db,
        employee=employee,
        action="COMPLETE",
        module="ORDER",
        reference_id=order.id,
        description="Order delivered",
    )

    db.commit()

    return {
        "message": "Order completed successfully",
        "order_id": order.id,
        "status": order.status,
    }


# =========================================================
# PURCHASE ORDERS
# =========================================================

def generate_unique_po_number(db: Session) -> str:

    max_id = (
        db.query(func.max(PurchaseOrder.id))
        .scalar()
        or 0
    )

    candidate = max_id + 1

    while True:

        po_number = f"ZPO-{candidate:06d}"

        existing = (
            db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.po_number == po_number
            )
            .first()
        )

        if not existing:
            return po_number

        candidate += 1


class PurchaseOrderItemCreate(BaseModel):
    product_id: int | None = None
    sku: str | None = None
    product_name: str
    quantity: int = 0
    purchase_price: float = 0
    gst_percent: float = 0
    discount_percent: float = 0


class PurchaseOrderCreate(BaseModel):
    supplier_id: int | None = None
    location_id: int | None = None
    order_date: str | None = None
    expected_date: str | None = None
    status: str = "DRAFT"
    payment_terms: str | None = None
    discount_amount: float = 0
    notes: str | None = None
    items: list[PurchaseOrderItemCreate]


@app.get("/api/purchase-orders")
def get_purchase_orders(
    db: Session = Depends(get_db)
):

    purchase_orders = (
        db.query(PurchaseOrder)
        .order_by(PurchaseOrder.id.desc())
        .all()
    )

    result = []

    for po in purchase_orders:

        supplier = None
        location = None

        if po.supplier_id:
            supplier = (
                db.query(Supplier)
                .filter(
                    Supplier.id == po.supplier_id
                )
                .first()
            )

        if po.location_id:
            location = (
                db.query(Location)
                .filter(
                    Location.id == po.location_id
                )
                .first()
            )

        item = as_dict(po)

        item["supplier_name"] = (
            supplier.company_name
            if supplier else None
        )

        item["location_name"] = (
            location.location_name
            if location else None
        )

        result.append(item)

    return result


@app.post("/api/purchase-orders")
def create_purchase_order(
    data: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):

    if not data.items:
        raise HTTPException(
            status_code=400,
            detail="Purchase order must contain at least one item"
        )

    if data.supplier_id:

        supplier = (
            db.query(Supplier)
            .filter(
                Supplier.id == data.supplier_id
            )
            .first()
        )

        if not supplier:
            raise HTTPException(
                status_code=404,
                detail="Supplier not found"
            )

    if data.location_id:

        location = (
            db.query(Location)
            .filter(
                Location.id == data.location_id
            )
            .first()
        )

        if not location:
            raise HTTPException(
                status_code=404,
                detail="Location not found"
            )

    po_number = generate_unique_po_number(db)

    order_date = data.order_date or today()

    subtotal = 0.0
    gst_amount = 0.0
    discount_amount = 0.0

    prepared_items = []

    for item in data.items:

        if item.quantity < 0:
            raise HTTPException(
                status_code=400,
                detail="Quantity cannot be negative"
            )

        base = (
            item.quantity
            * item.purchase_price
        )

        discount = (
            base
            * item.discount_percent
            / 100
        )

        taxable = base - discount

        gst = (
            taxable
            * item.gst_percent
            / 100
        )

        line_total = taxable + gst

        subtotal += base
        discount_amount += discount
        gst_amount += gst

        prepared_items.append({
            "data": item,
            "gst_amount": gst,
            "discount_amount": discount,
            "line_total": line_total,
        })

    total_amount = (
        subtotal
        - discount_amount
        + gst_amount
    )

    po = PurchaseOrder(
        po_number=po_number,
        supplier_id=data.supplier_id,
        location_id=data.location_id,
        order_date=order_date,
        expected_date=data.expected_date,
        status=data.status,
        payment_terms=data.payment_terms,
        subtotal=round(subtotal, 2),
        gst_amount=round(gst_amount, 2),
        discount_amount=round(
            discount_amount,
            2
        ),
        total_amount=round(
            total_amount,
            2
        ),
        notes=data.notes,
        created_by=employee.id,
        created_at=now(),
        updated_at=now(),
    )

    db.add(po)
    db.flush()

    for prepared in prepared_items:

        item = prepared["data"]

        po_item = PurchaseOrderItem(
            purchase_order_id=po.id,
            product_id=item.product_id,
            sku=item.sku,
            product_name=item.product_name,
            quantity=item.quantity,
            purchase_price=item.purchase_price,
            gst_percent=item.gst_percent,
            gst_amount=prepared["gst_amount"],
            discount_percent=item.discount_percent,
            discount_amount=prepared["discount_amount"],
            line_total=prepared["line_total"],
            status="OPEN",
        )

        db.add(po_item)

    create_audit_log(
        db=db,
        employee=employee,
        action="CREATE",
        module="PURCHASE_ORDER",
        reference_id=po.id,
        description=f"Created {po_number}",
    )

    db.commit()
    db.refresh(po)

    return {
        "message": "Purchase order created successfully",
        "purchase_order": as_dict(po),
    }


@app.get("/api/purchase-orders/{po_id}")
def get_purchase_order(
    po_id: int,
    db: Session = Depends(get_db)
):

    po = (
        db.query(PurchaseOrder)
        .filter(
            PurchaseOrder.id == po_id
        )
        .first()
    )

    if not po:
        raise HTTPException(
            status_code=404,
            detail="Purchase order not found"
        )

    supplier = None
    location = None

    if po.supplier_id:
        supplier = (
            db.query(Supplier)
            .filter(
                Supplier.id == po.supplier_id
            )
            .first()
        )

    if po.location_id:
        location = (
            db.query(Location)
            .filter(
                Location.id == po.location_id
            )
            .first()
        )

    items = (
        db.query(PurchaseOrderItem)
        .filter(
            PurchaseOrderItem.purchase_order_id == po.id
        )
        .order_by(PurchaseOrderItem.id.asc())
        .all()
    )

    return {
        "purchase_order": as_dict(po),
        "supplier_name": (
            supplier.company_name
            if supplier else None
        ),
        "location_name": (
            location.location_name
            if location else None
        ),
        "items": [
            as_dict(item)
            for item in items
        ],
    }


# =========================================================
# GRN
# =========================================================

def generate_unique_grn_number(
    db: Session
) -> str:

    max_id = (
        db.query(func.max(GoodsReceiptNote.id))
        .scalar()
        or 0
    )

    candidate = max_id + 1

    while True:

        grn_number = f"ZGRN-{candidate:06d}"

        existing = (
            db.query(GoodsReceiptNote)
            .filter(
                GoodsReceiptNote.grn_number
                == grn_number
            )
            .first()
        )

        if not existing:
            return grn_number

        candidate += 1


class GRNItemCreate(BaseModel):
    purchase_order_item_id: int | None = None
    product_id: int | None = None
    sku: str | None = None
    product_name: str
    ordered_quantity: int = 0
    received_quantity: int = 0
    damaged_quantity: int = 0
    accepted_quantity: int = 0
    purchase_price: float = 0
    batch_number: str | None = None
    expiry_date: str | None = None
    qc_status: str = "PENDING"
    notes: str | None = None


class GRNCreate(BaseModel):
    purchase_order_id: int | None = None
    supplier_id: int | None = None
    location_id: int | None = None
    received_date: str | None = None
    received_time: str | None = None
    status: str = "DRAFT"
    qc_status: str = "PENDING"
    notes: str | None = None
    items: list[GRNItemCreate]


@app.get("/api/grn")
def get_grns(
    db: Session = Depends(get_db)
):

    grns = (
        db.query(GoodsReceiptNote)
        .order_by(GoodsReceiptNote.id.desc())
        .all()
    )

    result = []

    for grn in grns:

        supplier = None
        location = None
        po = None

        if grn.supplier_id:

            supplier = (
                db.query(Supplier)
                .filter(
                    Supplier.id == grn.supplier_id
                )
                .first()
            )

        if grn.location_id:

            location = (
                db.query(Location)
                .filter(
                    Location.id == grn.location_id
                )
                .first()
            )

        if grn.purchase_order_id:

            po = (
                db.query(PurchaseOrder)
                .filter(
                    PurchaseOrder.id
                    == grn.purchase_order_id
                )
                .first()
            )

        item = as_dict(grn)

        item["supplier_name"] = (
            supplier.company_name
            if supplier else None
        )

        item["location_name"] = (
            location.location_name
            if location else None
        )

        item["po_number"] = (
            po.po_number
            if po else None
        )

        result.append(item)

    return result


@app.get("/api/grn/{grn_id}")
def get_grn(
    grn_id: int,
    db: Session = Depends(get_db)
):

    grn = (
        db.query(GoodsReceiptNote)
        .filter(
            GoodsReceiptNote.id == grn_id
        )
        .first()
    )

    if not grn:
        raise HTTPException(
            status_code=404,
            detail="GRN not found"
        )

    supplier = None
    location = None
    po = None

    if grn.supplier_id:

        supplier = (
            db.query(Supplier)
            .filter(
                Supplier.id == grn.supplier_id
            )
            .first()
        )

    if grn.location_id:

        location = (
            db.query(Location)
            .filter(
                Location.id == grn.location_id
            )
            .first()
        )

    if grn.purchase_order_id:

        po = (
            db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.id
                == grn.purchase_order_id
            )
            .first()
        )

    items = (
        db.query(GoodsReceiptNoteItem)
        .filter(
            GoodsReceiptNoteItem.grn_id == grn.id
        )
        .order_by(
            GoodsReceiptNoteItem.id.asc()
        )
        .all()
    )

    return {
        "grn": as_dict(grn),
        "grn_number": grn.grn_number,
        "supplier_name": (
            supplier.company_name
            if supplier else None
        ),
        "location_name": (
            location.location_name
            if location else None
        ),
        "po_number": (
            po.po_number
            if po else None
        ),
        "items": [
            as_dict(item)
            for item in items
        ],
    }


@app.get("/api/purchase-orders/{po_id}/grn-data")
def get_po_grn_data(
    po_id: int,
    db: Session = Depends(get_db)
):

    po = (
        db.query(PurchaseOrder)
        .filter(
            PurchaseOrder.id == po_id
        )
        .first()
    )

    if not po:
        raise HTTPException(
            status_code=404,
            detail="Purchase order not found"
        )

    supplier = None

    if po.supplier_id:

        supplier = (
            db.query(Supplier)
            .filter(
                Supplier.id == po.supplier_id
            )
            .first()
        )

    location = None

    if po.location_id:

        location = (
            db.query(Location)
            .filter(
                Location.id == po.location_id
            )
            .first()
        )

    items = (
        db.query(PurchaseOrderItem)
        .filter(
            PurchaseOrderItem.purchase_order_id
            == po.id
        )
        .order_by(
            PurchaseOrderItem.id.asc()
        )
        .all()
    )

    return {
        "purchase_order": as_dict(po),
        "supplier": (
            as_dict(supplier)
            if supplier
            else None
        ),
        "location": (
            as_dict(location)
            if location
            else None
        ),
        "items": [
            as_dict(item)
            for item in items
        ],
    }

@app.post("/api/grn")
def create_grn(
    data: GRNCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):
    if not data.items:
        raise HTTPException(
            status_code=400,
            detail="GRN must contain at least one item"
        )

    try:
        # =================================================
        # 1. GET PURCHASE ORDER
        # =================================================

        po = None

        if data.purchase_order_id:
            po = (
                db.query(PurchaseOrder)
                .filter(
                    PurchaseOrder.id == data.purchase_order_id
                )
                .first()
            )

            if not po:
                raise HTTPException(
                    status_code=404,
                    detail="Purchase order not found"
                )

        # =================================================
        # 2. USE PO DETAILS IF NOT SENT FROM FRONTEND
        # =================================================

        supplier_id = (
            data.supplier_id
            if data.supplier_id is not None
            else (po.supplier_id if po else None)
        )

        location_id = (
            data.location_id
            if data.location_id is not None
            else (po.location_id if po else None)
        )

        if supplier_id:
            supplier = (
                db.query(Supplier)
                .filter(Supplier.id == supplier_id)
                .first()
            )

            if not supplier:
                raise HTTPException(
                    status_code=404,
                    detail="Supplier not found"
                )

        if location_id:
            location = (
                db.query(Location)
                .filter(Location.id == location_id)
                .first()
            )

            if not location:
                raise HTTPException(
                    status_code=404,
                    detail="Location not found"
                )

        if not location_id:
            raise HTTPException(
                status_code=400,
                detail="Location is required for GRN"
            )

        # =================================================
        # 3. CREATE GRN HEADER
        # =================================================

        current_time = now()
        grn_number = generate_unique_grn_number(db)

        grn = GoodsReceiptNote(
            grn_number=grn_number,

            purchase_order_id=(
                po.id if po else data.purchase_order_id
            ),

            supplier_id=supplier_id,

            location_id=location_id,

            received_date=(
                data.received_date
                or today()
            ),

            received_time=(
                data.received_time
                or datetime.now().strftime("%H:%M:%S")
            ),

            status=data.status,

            qc_status=data.qc_status,

            notes=data.notes,

            created_by=employee.id,

            created_at=current_time,

            updated_at=current_time,
        )

        db.add(grn)
        db.flush()

        total_received = 0
        total_accepted = 0
        total_damaged = 0

        # =================================================
        # 4. PROCESS EACH GRN ITEM
        # =================================================

        for item in data.items:

            received_quantity = max(
                int(item.received_quantity or 0),
                0
            )

            damaged_quantity = max(
                int(item.damaged_quantity or 0),
                0
            )

            if damaged_quantity > received_quantity:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Damaged quantity cannot exceed "
                        f"received quantity for "
                        f"{item.product_name}"
                    )
                )

            # Automatically calculate accepted quantity
            # when frontend sends 0.
            if item.accepted_quantity > 0:
                accepted_quantity = int(
                    item.accepted_quantity
                )
            else:
                accepted_quantity = (
                    received_quantity
                    - damaged_quantity
                )

            if accepted_quantity > received_quantity:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Accepted quantity cannot exceed "
                        f"received quantity for "
                        f"{item.product_name}"
                    )
                )

            # =================================================
            # 5. CREATE GRN ITEM
            # =================================================

            grn_item = GoodsReceiptNoteItem(
                grn_id=grn.id,

                purchase_order_item_id=(
                    item.purchase_order_item_id
                ),

                product_id=item.product_id,

                sku=item.sku,

                product_name=item.product_name,

                ordered_quantity=(
                    item.ordered_quantity
                ),

                received_quantity=received_quantity,

                damaged_quantity=damaged_quantity,

                accepted_quantity=accepted_quantity,

                purchase_price=item.purchase_price,

                batch_number=item.batch_number,

                expiry_date=item.expiry_date,

                qc_status=item.qc_status,

                notes=item.notes,
            )

            db.add(grn_item)

            # =================================================
            # 6. UPDATE INVENTORY
            # =================================================

            if item.product_id:

                inventory = get_inventory_record(
                    db=db,
                    location_id=location_id,
                    product_id=item.product_id,
                )

                # Create inventory record if it doesn't exist
                if not inventory:

                    inventory = Inventory(
                        location_id=location_id,
                        product_id=item.product_id,
                        available_qty=0,
                        reserved_qty=0,
                        picked_qty=0,
                        packed_qty=0,
                        dispatched_qty=0,
                        damaged_qty=0,
                        returned_qty=0,
                        quarantine_qty=0,
                    )

                    db.add(inventory)
                    db.flush()

                # ---------------------------------------------
                # ACCEPTED STOCK
                # ---------------------------------------------

                if accepted_quantity > 0:

                    inventory.available_qty = (
                        inventory.available_qty
                        + accepted_quantity
                    )

                    create_stock_movement(
                        db=db,
                        product_id=item.product_id,
                        location_id=location_id,
                        movement_type="GRN",
                        quantity=accepted_quantity,
                        reference_number=grn_number,
                        remarks=(
                            f"Accepted stock received "
                            f"through {grn_number}"
                        ),
                    )

                # ---------------------------------------------
                # DAMAGED STOCK
                # ---------------------------------------------

                if damaged_quantity > 0:

                    inventory.damaged_qty = (
                        inventory.damaged_qty
                        + damaged_quantity
                    )

                    create_stock_movement(
                        db=db,
                        product_id=item.product_id,
                        location_id=location_id,
                        movement_type="DAMAGE",
                        quantity=damaged_quantity,
                        reference_number=grn_number,
                        remarks=(
                            f"Damaged stock received "
                            f"through {grn_number}"
                        ),
                    )

            # =================================================
            # 7. UPDATE PURCHASE ORDER ITEM
            # =================================================

            if item.purchase_order_item_id:

                po_item = (
                    db.query(PurchaseOrderItem)
                    .filter(
                        PurchaseOrderItem.id
                        == item.purchase_order_item_id
                    )
                    .first()
                )

                if po_item:

                    ordered_qty = (
                        po_item.quantity or 0
                    )

                    received_total = (
                        accepted_quantity
                        + damaged_quantity
                    )

                    if received_total >= ordered_qty:
                        po_item.status = "RECEIVED"
                    else:
                        po_item.status = (
                            "PARTIALLY_RECEIVED"
                        )

            total_received += received_quantity
            total_accepted += accepted_quantity
            total_damaged += damaged_quantity

        # =================================================
        # 8. UPDATE PURCHASE ORDER STATUS
        # =================================================

        if po:

            po_items = (
                db.query(PurchaseOrderItem)
                .filter(
                    PurchaseOrderItem.purchase_order_id
                    == po.id
                )
                .all()
            )

            if po_items:

                all_received = all(
                    item.status == "RECEIVED"
                    for item in po_items
                )

                if all_received:
                    po.status = "RECEIVED"
                else:
                    po.status = "PARTIALLY_RECEIVED"

                po.updated_at = current_time

        # =================================================
        # 9. AUDIT LOG
        # =================================================

        create_audit_log(
            db=db,
            employee=employee,
            action="CREATE",
            module="GRN",
            reference_id=grn.id,
            description=(
                f"Created {grn_number}; "
                f"received={total_received}, "
                f"accepted={total_accepted}, "
                f"damaged={total_damaged}"
            ),
        )

        # =================================================
        # 10. SAVE EVERYTHING
        # =================================================

        db.commit()
        db.refresh(grn)

        return {
            "message": "GRN created successfully",

            "grn": as_dict(grn),

            "grn_number": grn_number,

            "purchase_order_id": (
                grn.purchase_order_id
            ),

            "supplier_id": grn.supplier_id,

            "location_id": grn.location_id,

            "total_received_quantity": total_received,

            "total_accepted_quantity": total_accepted,

            "total_damaged_quantity": total_damaged,

            "inventory_updated": True,
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to create GRN: {str(e)}"
        )


# =========================================================
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
# ROLES
# =========================================================

@app.get("/api/roles")
def get_roles(
    db: Session = Depends(get_db)
):

    roles = (
        db.query(Role)
        .order_by(Role.id.asc())
        .all()
    )

    return [as_dict(role) for role in roles]


# =========================================================
# PERMISSIONS
# =========================================================

@app.get("/api/permissions")
def get_permissions(
    db: Session = Depends(get_db)
):

    permissions = (
        db.query(Permission)
        .order_by(Permission.id.asc())
        .all()
    )

    return [
        as_dict(permission)
        for permission in permissions
    ]


# =========================================================
# ROLE PERMISSIONS
# =========================================================

@app.get("/api/role-permissions")
def get_role_permissions(
    db: Session = Depends(get_db)
):

    records = (
        db.query(RolePermission)
        .order_by(RolePermission.id.asc())
        .all()
    )

    return [
        as_dict(record)
        for record in records
    ]


# =========================================================
# AUDIT LOGS
# =========================================================

@app.get("/api/audit-logs")
def get_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db)
):

    limit = min(max(limit, 1), 500)

    logs = (
        db.query(AuditLog)
        .order_by(AuditLog.id.desc())
        .limit(limit)
        .all()
    )

    return [
        as_dict(log)
        for log in logs
    ]


# =========================================================
# PUTAWAY
# =========================================================

def generate_unique_putaway_number(db: Session) -> str:
    max_id = (
        db.query(func.max(PutawayTask.id))
        .scalar()
        or 0
    )

    candidate = max_id + 1

    while True:
        task_number = f"ZPT-{candidate:06d}"

        existing = (
            db.query(PutawayTask)
            .filter(
                PutawayTask.task_number == task_number
            )
            .first()
        )

        if not existing:
            return task_number

        candidate += 1


class PutawayTaskCreate(BaseModel):
    location_id: int
    product_id: int
    quantity: int = Field(gt=0)
    grn_id: int | None = None
    grn_item_id: int | None = None
    assigned_employee_id: int | None = None
    assigned_bin_id: int | None = None
    priority: str = "NORMAL"
    remarks: str | None = None


class PutawayAssignRequest(BaseModel):
    employee_id: int
    bin_id: int


class PutawayScanRequest(BaseModel):
    scanned_sku: str
    scanned_bin_code: str
    confirmed_quantity: int = Field(gt=0)


# ---------------------------------------------------------
# GET PUTAWAY TASKS
# ---------------------------------------------------------

@app.get("/api/putaway")
def get_putaway_tasks(
    status: str | None = None,
    location_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(PutawayTask)

    if status:
        query = query.filter(
            PutawayTask.status == status.upper()
        )

    if location_id:
        query = query.filter(
            PutawayTask.location_id == location_id
        )

    tasks = (
        query
        .order_by(PutawayTask.id.desc())
        .all()
    )

    result = []

    for task in tasks:

        item = as_dict(task)

        employee = None
        bin_record = None
        location = None

        if task.assigned_employee_id:
            employee = (
                db.query(Employee)
                .filter(
                    Employee.id
                    == task.assigned_employee_id
                )
                .first()
            )

        if task.assigned_bin_id:
            bin_record = (
                db.query(Bin)
                .filter(
                    Bin.id
                    == task.assigned_bin_id
                )
                .first()
            )

        if task.location_id:
            location = (
                db.query(Location)
                .filter(
                    Location.id
                    == task.location_id
                )
                .first()
            )

        item["employee_name"] = (
            employee.full_name
            if employee else None
        )

        item["bin_code"] = (
            bin_record.bin_code
            if bin_record else None
        )

        item["location_name"] = (
            location.location_name
            if location else None
        )

        result.append(item)

    return result


# ---------------------------------------------------------
# GET SINGLE PUTAWAY TASK
# ---------------------------------------------------------

@app.get("/api/putaway/{task_id}")
def get_putaway_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    task = (
        db.query(PutawayTask)
        .filter(
            PutawayTask.id == task_id
        )
        .first()
    )

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Putaway task not found"
        )

    item = as_dict(task)

    employee = None
    bin_record = None
    location = None

    if task.assigned_employee_id:
        employee = (
            db.query(Employee)
            .filter(
                Employee.id
                == task.assigned_employee_id
            )
            .first()
        )

    if task.assigned_bin_id:
        bin_record = (
            db.query(Bin)
            .filter(
                Bin.id
                == task.assigned_bin_id
            )
            .first()
        )

    if task.location_id:
        location = (
            db.query(Location)
            .filter(
                Location.id
                == task.location_id
            )
            .first()
        )

    item["employee_name"] = (
        employee.full_name
        if employee else None
    )

    item["bin_code"] = (
        bin_record.bin_code
        if bin_record else None
    )

    item["location_name"] = (
        location.location_name
        if location else None
    )

    return item


# ---------------------------------------------------------
# CREATE PUTAWAY TASK
# ---------------------------------------------------------

@app.post("/api/putaway")
def create_putaway_task(
    data: PutawayTaskCreate,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):
    location = (
        db.query(Location)
        .filter(
            Location.id == data.location_id
        )
        .first()
    )

    if not location:
        raise HTTPException(
            status_code=404,
            detail="Location not found"
        )

    product = (
        db.query(Product)
        .filter(
            Product.id == data.product_id
        )
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    if data.assigned_bin_id:

        bin_record = (
            db.query(Bin)
            .filter(
                Bin.id == data.assigned_bin_id
            )
            .first()
        )

        if not bin_record:
            raise HTTPException(
                status_code=404,
                detail="Assigned bin not found"
            )

        if bin_record.location_id != data.location_id:
            raise HTTPException(
                status_code=400,
                detail="Bin does not belong to selected location"
            )

        if bin_record.status != "ACTIVE":
            raise HTTPException(
                status_code=400,
                detail="Assigned bin is not active"
            )

    if data.assigned_employee_id:

        assigned_employee = (
            db.query(Employee)
            .filter(
                Employee.id
                == data.assigned_employee_id
            )
            .first()
        )

        if not assigned_employee:
            raise HTTPException(
                status_code=404,
                detail="Assigned employee not found"
            )

    task_number = generate_unique_putaway_number(db)

    current_time = now()

    task_status = (
        "ASSIGNED"
        if data.assigned_employee_id
        and data.assigned_bin_id
        else "PENDING"
    )

    task = PutawayTask(
        task_number=task_number,
        grn_id=data.grn_id,
        grn_item_id=data.grn_item_id,
        location_id=data.location_id,
        product_id=data.product_id,
        sku=product.sku,
        product_name=product.product_name,
        quantity=data.quantity,
        confirmed_quantity=0,
        assigned_employee_id=data.assigned_employee_id,
        assigned_bin_id=data.assigned_bin_id,
        status=task_status,
        priority=data.priority.upper(),
        remarks=data.remarks,
        created_by=employee.id,
        created_at=current_time,
        assigned_at=(
            current_time
            if task_status == "ASSIGNED"
            else None
        ),
    )

    db.add(task)

    create_audit_log(
        db=db,
        employee=employee,
        action="CREATE",
        module="PUTAWAY",
        reference_id=None,
        description=(
            f"Created putaway task "
            f"{task_number} for {product.sku}, "
            f"quantity={data.quantity}"
        ),
    )

    db.commit()
    db.refresh(task)

    return {
        "message": "Putaway task created successfully",
        "task": as_dict(task),
    }


# ---------------------------------------------------------
# ASSIGN PUTAWAY EMPLOYEE + BIN
# ---------------------------------------------------------

@app.put("/api/putaway/{task_id}/assign")
def assign_putaway_task(
    task_id: int,
    data: PutawayAssignRequest,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):
    task = (
        db.query(PutawayTask)
        .filter(
            PutawayTask.id == task_id
        )
        .first()
    )

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Putaway task not found"
        )

    assigned_employee = (
        db.query(Employee)
        .filter(
            Employee.id == data.employee_id
        )
        .first()
    )

    if not assigned_employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )

    bin_record = (
        db.query(Bin)
        .filter(
            Bin.id == data.bin_id
        )
        .first()
    )

    if not bin_record:
        raise HTTPException(
            status_code=404,
            detail="Bin not found"
        )

    if bin_record.location_id != task.location_id:
        raise HTTPException(
            status_code=400,
            detail="Bin does not belong to task location"
        )

    if bin_record.status != "ACTIVE":
        raise HTTPException(
            status_code=400,
            detail="Bin is not active"
        )

    current_time = now()

    task.assigned_employee_id = data.employee_id
    task.assigned_bin_id = data.bin_id
    task.status = "ASSIGNED"
    task.assigned_at = current_time

    create_audit_log(
        db=db,
        employee=employee,
        action="ASSIGN",
        module="PUTAWAY",
        reference_id=task.id,
        description=(
            f"Assigned {task.task_number} "
            f"to employee {assigned_employee.employee_id} "
            f"and bin {bin_record.bin_code}"
        ),
    )

    db.commit()
    db.refresh(task)

    return {
        "message": "Putaway task assigned successfully",
        "task": as_dict(task),
        "employee_id": assigned_employee.employee_id,
        "employee_name": assigned_employee.full_name,
        "bin_code": bin_record.bin_code,
    }


# ---------------------------------------------------------
# START PUTAWAY
# ---------------------------------------------------------

@app.put("/api/putaway/{task_id}/start")
def start_putaway_task(
    task_id: int,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):
    task = (
        db.query(PutawayTask)
        .filter(
            PutawayTask.id == task_id
        )
        .first()
    )

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Putaway task not found"
        )

    if task.status not in [
        "ASSIGNED",
        "PENDING",
    ]:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Task cannot be started "
                f"from status {task.status}"
            )
        )

    if not task.assigned_employee_id:
        raise HTTPException(
            status_code=400,
            detail="Putaway employee is not assigned"
        )

    if not task.assigned_bin_id:
        raise HTTPException(
            status_code=400,
            detail="Putaway bin is not assigned"
        )

    current_time = now()

    task.status = "IN_PROGRESS"
    task.started_at = current_time

    create_audit_log(
        db=db,
        employee=employee,
        action="START",
        module="PUTAWAY",
        reference_id=task.id,
        description=(
            f"Started putaway task "
            f"{task.task_number}"
        ),
    )

    db.commit()
    db.refresh(task)

    return {
        "message": "Putaway task started",
        "task": as_dict(task),
    }


# ---------------------------------------------------------
# SCAN SKU + BIN + COMPLETE PUTAWAY
# ---------------------------------------------------------

@app.post("/api/putaway/{task_id}/complete")
def complete_putaway_task(
    task_id: int,
    data: PutawayScanRequest,
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):
    task = (
        db.query(PutawayTask)
        .filter(
            PutawayTask.id == task_id
        )
        .first()
    )

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Putaway task not found"
        )

    if task.status not in [
        "ASSIGNED",
        "IN_PROGRESS",
    ]:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Task cannot be completed "
                f"from status {task.status}"
            )
        )

    if not task.assigned_employee_id:
        raise HTTPException(
            status_code=400,
            detail="No putaway employee assigned"
        )

    if not task.assigned_bin_id:
        raise HTTPException(
            status_code=400,
            detail="No putaway bin assigned"
        )

    # -----------------------------------------------------
    # VERIFY SKU
    # -----------------------------------------------------

    scanned_sku = data.scanned_sku.strip().upper()

    if scanned_sku != task.sku.upper():
        raise HTTPException(
            status_code=400,
            detail=(
                f"SKU mismatch. Expected "
                f"{task.sku}, scanned "
                f"{data.scanned_sku}"
            )
        )

    # -----------------------------------------------------
    # VERIFY BIN
    # -----------------------------------------------------

    bin_record = (
        db.query(Bin)
        .filter(
            Bin.id == task.assigned_bin_id
        )
        .first()
    )

    if not bin_record:
        raise HTTPException(
            status_code=404,
            detail="Assigned bin not found"
        )

    scanned_bin = (
        data.scanned_bin_code
        .strip()
        .upper()
    )

    if scanned_bin != bin_record.bin_code.upper():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Bin mismatch. Expected "
                f"{bin_record.bin_code}, "
                f"scanned {data.scanned_bin_code}"
            )
        )

    # -----------------------------------------------------
    # VERIFY QUANTITY
    # -----------------------------------------------------

    confirmed_quantity = int(
        data.confirmed_quantity
    )

    if confirmed_quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Confirmed quantity must be greater than zero"
        )

    if confirmed_quantity > task.quantity:
        raise HTTPException(
            status_code=400,
            detail=(
                "Confirmed quantity cannot exceed "
                "task quantity"
            )
        )

    current_time = now()

    # -----------------------------------------------------
    # FIND / CREATE BIN INVENTORY
    # -----------------------------------------------------

    bin_inventory = (
        db.query(BinInventory)
        .filter(
            BinInventory.location_id
            == task.location_id,
            BinInventory.bin_id
            == task.assigned_bin_id,
            BinInventory.product_id
            == task.product_id,
        )
        .first()
    )

    if not bin_inventory:

        bin_inventory = BinInventory(
            location_id=task.location_id,
            bin_id=task.assigned_bin_id,
            product_id=task.product_id,
            sku=task.sku,
            available_qty=0,
            reserved_qty=0,
            picked_qty=0,
            damaged_qty=0,
            quarantine_qty=0,
            created_at=current_time,
            updated_at=current_time,
        )

        db.add(bin_inventory)
        db.flush()

    # -----------------------------------------------------
    # UPDATE BIN STOCK
    # -----------------------------------------------------

    bin_inventory.available_qty += confirmed_quantity
    bin_inventory.updated_at = current_time

    # -----------------------------------------------------
    # UPDATE TASK
    # -----------------------------------------------------

    task.confirmed_quantity = confirmed_quantity
    task.scanned_sku = data.scanned_sku
    task.scanned_bin_code = data.scanned_bin_code
    task.status = "COMPLETED"
    task.completed_by = employee.id
    task.completed_at = current_time

    # -----------------------------------------------------
    # CREATE INVENTORY AUDIT TASK
    # -----------------------------------------------------

    audit_task_number = (
        f"ZPA-{task.id:06d}"
    )

    existing_audit = (
        db.query(PutawayAuditTask)
        .filter(
            PutawayAuditTask.putaway_task_id
            == task.id
        )
        .first()
    )

    if not existing_audit:

        audit_task = PutawayAuditTask(
            task_number=audit_task_number,
            putaway_task_id=task.id,
            location_id=task.location_id,
            bin_id=task.assigned_bin_id,
            product_id=task.product_id,
            sku=task.sku,
            system_quantity=bin_inventory.available_qty,
            physical_quantity=None,
            variance_quantity=0,
            status="PENDING",
            assigned_employee_id=None,
            verified_by=None,
            reason=None,
            created_at=current_time,
            completed_at=None,
        )

        db.add(audit_task)

    # -----------------------------------------------------
    # AUDIT LOG
    # -----------------------------------------------------

    create_audit_log(
        db=db,
        employee=employee,
        action="COMPLETE",
        module="PUTAWAY",
        reference_id=task.id,
        description=(
            f"Completed {task.task_number}; "
            f"SKU={task.sku}; "
            f"BIN={bin_record.bin_code}; "
            f"quantity={confirmed_quantity}"
        ),
    )

    db.commit()
    db.refresh(task)
    db.refresh(bin_inventory)

    return {
        "message": "Putaway completed successfully",
        "task": as_dict(task),
        "bin_inventory": as_dict(bin_inventory),
        "audit_task_created": True,
        "audit_task_number": audit_task_number,
    }


# ---------------------------------------------------------
# PUTAWAY AUDIT TASKS
# ---------------------------------------------------------

@app.get("/api/putaway-audits")
def get_putaway_audits(
    status: str | None = None,
    location_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(PutawayAuditTask)

    if status:
        query = query.filter(
            PutawayAuditTask.status
            == status.upper()
        )

    if location_id:
        query = query.filter(
            PutawayAuditTask.location_id
            == location_id
        )

    audits = (
        query
        .order_by(PutawayAuditTask.id.desc())
        .all()
    )

    result = []

    for audit in audits:

        item = as_dict(audit)

        bin_record = (
            db.query(Bin)
            .filter(
                Bin.id == audit.bin_id
            )
            .first()
        )

        product = (
            db.query(Product)
            .filter(
                Product.id == audit.product_id
            )
            .first()
        )

        location = (
            db.query(Location)
            .filter(
                Location.id == audit.location_id
            )
            .first()
        )

        item["bin_code"] = (
            bin_record.bin_code
            if bin_record else None
        )

        item["product_name"] = (
            product.product_name
            if product else None
        )

        item["location_name"] = (
            location.location_name
            if location else None
        )

        result.append(item)

    return result

# =========================================================
# ROLES
# =========================================================

# =========================================================
# BIN INVENTORY
# =========================================================

@app.get("/api/bin-inventory")
def get_bin_inventory(
    location_id: int | None = None,
    bin_id: int | None = None,
    product_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.BinInventory)

    if location_id is not None:
        query = query.filter(
            models.BinInventory.location_id == location_id
        )

    if bin_id is not None:
        query = query.filter(
            models.BinInventory.bin_id == bin_id
        )

    if product_id is not None:
        query = query.filter(
            models.BinInventory.product_id == product_id
        )

    records = (
        query
        .order_by(models.BinInventory.id.desc())
        .all()
    )

    result = []

    for record in records:
        location = (
            db.query(Location)
            .filter(Location.id == record.location_id)
            .first()
        )

        bin_record = (
            db.query(Bin)
            .filter(Bin.id == record.bin_id)
            .first()
        )

        product = (
            db.query(Product)
            .filter(Product.id == record.product_id)
            .first()
        )

        result.append({
            "id": record.id,
            "location_id": record.location_id,
            "location_name": (
                location.location_name
                if location else None
            ),
            "bin_id": record.bin_id,
            "bin_code": (
                bin_record.bin_code
                if bin_record else None
            ),
            "product_id": record.product_id,
            "product_name": (
                product.product_name
                if product else None
            ),
            "sku": (
                record.sku
                if record.sku
                else (
                    product.sku
                    if product else None
                )
            ),
            "available_qty": record.available_qty or 0,
            "reserved_qty": record.reserved_qty or 0,
            "picked_qty": record.picked_qty or 0,
            "damaged_qty": record.damaged_qty or 0,
            "quarantine_qty": record.quarantine_qty or 0,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        })

    return result


# =========================================================
# FINAL STATIC FRONTEND MOUNT
# =========================================================

if FRONTEND_DIR.exists():
    app.mount(
        "/",
        StaticFiles(
            directory=FRONTEND_DIR,
            html=True
        ),
        name="frontend"
    )
