from sqlalchemy import Column, Integer, String, Float, Boolean, UniqueConstraint, Table
from .database import Base


# =========================================================
# LOCATIONS
# =========================================================

class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    location_code = Column("code", String, unique=True, index=True, nullable=False)
    location_name = Column("name", String, nullable=False)
    location_type = Column(String, nullable=False)
    address = Column(String)
    city = Column(String)
    state = Column(String)
    pincode = Column(String)
    manager_name = Column(String)
    capacity = Column(Integer, default=0)
    active = Column(Boolean, default=True)


# =========================================================
# PRODUCTS
# =========================================================

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True, nullable=False)
    barcode = Column(String)
    image_url = Column(String, nullable=True)
    product_name = Column("name", String, nullable=False)
    category = Column(String)
    brand = Column(String)
    uom = Column(String, default="PCS")
    mrp = Column(Float, default=0)
    selling_price = Column(Float, default=0)
    purchase_price = Column(Float, default=0)
    gst_percent = Column(Float, default=0)
    weight = Column(Float, default=0)
    reorder_level = Column(Integer, default=0)
    minimum_stock = Column(Integer, default=0)
    maximum_stock = Column(Integer, default=0)
    active = Column(Boolean, default=True)


# =========================================================
# SUPPLIERS
# =========================================================

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    supplier_code = Column(String, unique=True, index=True)
    company_name = Column(String, nullable=False)
    contact_person = Column(String)
    phone = Column(String)
    email = Column(String)
    gstin = Column(String)
    address = Column(String)
    payment_terms = Column("credit_days", Integer, default=0)
    active = Column(Boolean, default=True)


# =========================================================
# INVENTORY
# =========================================================

class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, nullable=False)
    bin_id = Column(Integer, nullable=True)
    product_id = Column(Integer, nullable=False)

    available_qty = Column(Integer, default=0)
    reserved_qty = Column(Integer, default=0)
    picked_qty = Column(Integer, default=0)
    packed_qty = Column(Integer, default=0)
    dispatched_qty = Column(Integer, default=0)
    damaged_qty = Column(Integer, default=0)
    returned_qty = Column(Integer, default=0)
    quarantine_qty = Column(Integer, default=0)


# =========================================================
# STOCK MOVEMENTS
# =========================================================

class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, nullable=False)
    location_id = Column(Integer, nullable=False)
    movement_type = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    reference_number = Column(String)
    remarks = Column(String)
    created_at = Column(String, nullable=False)


# =========================================================
# BINS
# =========================================================

class Bin(Base):
    __tablename__ = "bins"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, nullable=False)
    bin_code = Column(String, unique=True, nullable=False, index=True)
    zone = Column(String, nullable=False)
    aisle = Column(String, nullable=False)
    rack = Column(String, nullable=False)
    shelf = Column(String, nullable=False)
    bin_type = Column(String, default="STORAGE")
    capacity = Column(Integer, default=0)
    status = Column(String, default="ACTIVE")
    created_at = Column(String, nullable=False)


# =========================================================
# ORDERS
# =========================================================

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String, unique=True, index=True, nullable=False)

    customer_name = Column(String, nullable=False)
    customer_phone = Column(String)
    delivery_address = Column(String, nullable=False)
    city = Column(String)

    location_id = Column(Integer, nullable=True)

    status = Column(String, default="NEW", index=True)

    payment_mode = Column(String, default="COD")
    payment_status = Column(String, default="PENDING")

    subtotal = Column(Float, default=0)
    delivery_charge = Column(Float, default=0)
    handling_charge = Column(Float, default=0)
    discount = Column(Float, default=0)
    total_amount = Column(Float, default=0)

    rider_id = Column(Integer, nullable=True)

    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


# =========================================================
# ORDER ITEMS
# =========================================================

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, nullable=False)
    product_id = Column(Integer, nullable=False)

    sku = Column(String, nullable=False)
    product_name = Column(String, nullable=False)

    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, default=0)
    total_price = Column(Float, default=0)

    status = Column(String, default="NEW")


# =========================================================
# RIDERS
# =========================================================

class Rider(Base):
    __tablename__ = "riders"

    id = Column(Integer, primary_key=True, index=True)
    rider_code = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String)

    vehicle_type = Column(String, default="BIKE")
    status = Column(String, default="OFFLINE")

    location_id = Column(Integer, nullable=True)

    total_deliveries = Column(Integer, default=0)
    active = Column(Boolean, default=True)


# =========================================================
# EMPLOYEES
# =========================================================

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, unique=True, index=True, nullable=False)

    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    mobile = Column(String, unique=True, index=True, nullable=False)

    password_hash = Column(String, nullable=True)

    role = Column(String, default="EMPLOYEE", index=True)
    department = Column(String, nullable=True)
    location_id = Column(Integer, nullable=True)

    status = Column(String, default="ACTIVE", index=True)

    email_verified = Column(Boolean, default=False)
    mobile_verified = Column(Boolean, default=False)

    last_login = Column(String, nullable=True)

    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


# =========================================================
# ROLES
# =========================================================

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)

    role_code = Column(String, unique=True, index=True, nullable=False)
    role_name = Column(String, nullable=False)

    description = Column(String, nullable=True)

    active = Column(Boolean, default=True)


# =========================================================
# PERMISSIONS
# =========================================================

class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)

    permission_code = Column(String, unique=True, index=True, nullable=False)
    permission_name = Column(String, nullable=False)

    module = Column(String, nullable=False)

    active = Column(Boolean, default=True)


# =========================================================
# ROLE PERMISSIONS
# =========================================================

class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, index=True)

    role_code = Column(String, nullable=False, index=True)
    permission_code = Column(String, nullable=False, index=True)

    allowed = Column(Boolean, default=True)


# =========================================================
# OTP VERIFICATION
# =========================================================

class OTPVerification(Base):
    __tablename__ = "otp_verifications"

    id = Column(Integer, primary_key=True, index=True)

    employee_id = Column(Integer, nullable=True, index=True)

    identifier = Column(String, nullable=False, index=True)
    identifier_type = Column(String, nullable=False)

    otp_code = Column(String, nullable=False)

    purpose = Column(String, default="LOGIN")

    expires_at = Column(String, nullable=False)

    verified = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)

    created_at = Column(String, nullable=False)


# =========================================================
# LOGIN SESSIONS
# =========================================================

class LoginSession(Base):
    __tablename__ = "login_sessions"

    id = Column(Integer, primary_key=True, index=True)

    employee_id = Column(Integer, nullable=False, index=True)

    session_token = Column(
        String,
        unique=True,
        index=True,
        nullable=False
    )

    login_method = Column(String, nullable=False)

    device_name = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)

    expires_at = Column(String, nullable=False)

    revoked = Column(Boolean, default=False)

    created_at = Column(String, nullable=False)


# =========================================================
# AUDIT LOGS
# =========================================================

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    employee_id = Column(Integer, nullable=True, index=True)
    employee_name = Column(String, nullable=True)

    action = Column(String, nullable=False)
    module = Column(String, nullable=False)

    reference_id = Column(String, nullable=True)
    description = Column(String, nullable=True)

    ip_address = Column(String, nullable=True)

    created_at = Column(String, nullable=False)


# =========================================================
# PURCHASE ORDERS
# =========================================================

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, index=True)

    po_number = Column(
        String,
        unique=True,
        index=True,
        nullable=False
    )

    supplier_id = Column(Integer, nullable=True)
    location_id = Column(Integer, nullable=True)

    order_date = Column(String, nullable=False)
    expected_date = Column(String, nullable=True)

    status = Column(String, default="DRAFT", index=True)

    payment_terms = Column(String, nullable=True)

    subtotal = Column(Float, default=0)
    gst_amount = Column(Float, default=0)
    discount_amount = Column(Float, default=0)
    total_amount = Column(Float, default=0)

    notes = Column(String, nullable=True)

    created_by = Column(Integer, nullable=True)

    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


# =========================================================
# PURCHASE ORDER ITEMS
# =========================================================

class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id = Column(Integer, primary_key=True, index=True)

    purchase_order_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    product_id = Column(Integer, nullable=True)

    sku = Column(String, nullable=True)
    product_name = Column(String, nullable=False)

    quantity = Column(Integer, default=0)

    purchase_price = Column(Float, default=0)

    gst_percent = Column(Float, default=0)
    gst_amount = Column(Float, default=0)

    discount_percent = Column(Float, default=0)
    discount_amount = Column(Float, default=0)

    line_total = Column(Float, default=0)

    status = Column(String, default="OPEN") 
    # ============================================================
# GOODS RECEIPT NOTE (GRN)
# ============================================================

class GoodsReceiptNote(Base):
    __tablename__ = "goods_receipt_notes"

    id = Column(Integer, primary_key=True, index=True)

    grn_number = Column(
        String,
        unique=True,
        index=True,
        nullable=False
    )

    purchase_order_id = Column(
        Integer,
        nullable=True,
        index=True
    )

    supplier_id = Column(
        Integer,
        nullable=True
    )

    location_id = Column(
        Integer,
        nullable=True
    )

    received_date = Column(
        String,
        nullable=False
    )

    received_time = Column(
        String,
        nullable=True
    )

    status = Column(
        String,
        default="DRAFT",
        index=True
    )

    qc_status = Column(
        String,
        default="PENDING"
    )

    notes = Column(
        String,
        nullable=True
    )

    created_by = Column(
        Integer,
        nullable=True
    )

    created_at = Column(
        String,
        nullable=False
    )

    updated_at = Column(
        String,
        nullable=False
    )


class GoodsReceiptNoteItem(Base):
    __tablename__ = "goods_receipt_note_items"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    grn_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    purchase_order_item_id = Column(
        Integer,
        nullable=True
    )

    product_id = Column(
        Integer,
        nullable=True
    )

    sku = Column(
        String,
        nullable=True
    )

    product_name = Column(
        String,
        nullable=False
    )

    ordered_quantity = Column(
        Integer,
        default=0
    )

    received_quantity = Column(
        Integer,
        default=0
    )

    damaged_quantity = Column(
        Integer,
        default=0
    )

    accepted_quantity = Column(
        Integer,
        default=0
    )

    purchase_price = Column(
        Float,
        default=0
    )

    batch_number = Column(
        String,
        nullable=True
    )

    expiry_date = Column(
        String,
        nullable=True
    )

    qc_status = Column(
        String,
        default="PENDING"
    )

    notes = Column(
        String,
        nullable=True
    )
    # =========================================================
# PUTAWAY TASKS
# =========================================================

class PutawayTask(Base):
    __tablename__ = "putaway_tasks"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    task_number = Column(
        String,
        unique=True,
        index=True,
        nullable=False
    )

    grn_id = Column(
        Integer,
        nullable=True,
        index=True
    )

    grn_item_id = Column(
        Integer,
        nullable=True,
        index=True
    )

    location_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    product_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    sku = Column(
        String,
        nullable=False,
        index=True
    )

    product_name = Column(
        String,
        nullable=False
    )

    quantity = Column(
        Integer,
        nullable=False,
        default=0
    )

    confirmed_quantity = Column(
        Integer,
        default=0
    )

    assigned_employee_id = Column(
        Integer,
        nullable=True,
        index=True
    )

    assigned_bin_id = Column(
        Integer,
        nullable=True,
        index=True
    )

    scanned_sku = Column(
        String,
        nullable=True
    )

    scanned_bin_code = Column(
        String,
        nullable=True
    )

    status = Column(
        String,
        default="PENDING",
        index=True
    )

    priority = Column(
        String,
        default="NORMAL"
    )

    remarks = Column(
        String,
        nullable=True
    )

    created_by = Column(
        Integer,
        nullable=True
    )

    completed_by = Column(
        Integer,
        nullable=True
    )

    created_at = Column(
        String,
        nullable=False
    )

    assigned_at = Column(
        String,
        nullable=True
    )

    started_at = Column(
        String,
        nullable=True
    )

    completed_at = Column(
        String,
        nullable=True
    )


# =========================================================
# PUTAWAY AUDIT TASKS
# =========================================================

class PutawayAuditTask(Base):
    __tablename__ = "putaway_audit_tasks"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    task_number = Column(
        String,
        unique=True,
        index=True,
        nullable=False
    )

    putaway_task_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    location_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    bin_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    product_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    sku = Column(
        String,
        nullable=False,
        index=True
    )

    system_quantity = Column(
        Integer,
        default=0
    )

    physical_quantity = Column(
        Integer,
        nullable=True
    )

    variance_quantity = Column(
        Integer,
        default=0
    )

    status = Column(
        String,
        default="PENDING",
        index=True
    )

    assigned_employee_id = Column(
        Integer,
        nullable=True
    )

    verified_by = Column(
        Integer,
        nullable=True
    )

    reason = Column(
        String,
        nullable=True
    )

    created_at = Column(
        String,
        nullable=False
    )

    completed_at = Column(
        String,
        nullable=True
    )
    # =========================================================
# BIN INVENTORY
# =========================================================

class BinInventory(Base):
    __tablename__ = "bin_inventory"

    id = Column(Integer, primary_key=True, index=True)

    location_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    bin_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    product_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    sku = Column(
        String,
        nullable=False,
        index=True
    )

    available_qty = Column(
        Integer,
        default=0
    )

    reserved_qty = Column(
        Integer,
        default=0
    )

    picked_qty = Column(
        Integer,
        default=0
    )

    damaged_qty = Column(
        Integer,
        default=0
    )

    quarantine_qty = Column(
        Integer,
        default=0
    )

    created_at = Column(
        String,
        nullable=False
    )

    updated_at = Column(
        String,
        nullable=False
    )