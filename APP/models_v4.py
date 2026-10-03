from sqlalchemy import (
    Column,
    Integer,
    String,
    UniqueConstraint,
)

from .database import Base


# ============================================================
# ZIPPZO WMS V4 DATA MODELS
# ============================================================
#
# IMPORTANT:
# These models use the existing SQLAlchemy Base.
#
# create_all() only creates missing database tables.
# It does NOT delete or reset existing data.
#
# Tables:
#
# wms_batches
# wms_batch_orders
# wms_pick_lists
# wms_pick_items
# wms_sort_lists
# wms_sort_items
# wms_grid_putaway
# wms_grid_putaway_items
# ============================================================


# ============================================================
# BATCH
# ============================================================

class WMSBatch(Base):

    __tablename__ = "wms_batches"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    batch_number = Column(
        String,
        unique=True,
        index=True,
        nullable=False,
    )

    location_id = Column(
        Integer,
        nullable=True,
        index=True,
    )

    status = Column(
        String,
        default="CREATED",
        index=True,
    )

    priority = Column(
        String,
        default="NORMAL",
        index=True,
    )

    total_orders = Column(
        Integer,
        default=0,
    )

    total_units = Column(
        Integer,
        default=0,
    )

    assigned_picker_id = Column(
        Integer,
        nullable=True,
        index=True,
    )

    created_by = Column(
        Integer,
        nullable=True,
    )

    created_at = Column(
        String,
        nullable=False,
    )

    updated_at = Column(
        String,
        nullable=False,
    )

    cancelled_at = Column(
        String,
        nullable=True,
    )

    cancellation_reason = Column(
        String,
        nullable=True,
    )


# ============================================================
# BATCH ORDERS
# ============================================================

class WMSBatchOrder(Base):

    __tablename__ = "wms_batch_orders"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    batch_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    order_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    order_status_before = Column(
        String,
        nullable=True,
    )

    created_at = Column(
        String,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "order_id",
            name="uq_wms_batch_order",
        ),
    )


# ============================================================
# PICK LIST
# ============================================================

class WMSPickList(Base):

    __tablename__ = "wms_pick_lists"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    pick_number = Column(
        String,
        unique=True,
        index=True,
        nullable=False,
    )

    batch_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    location_id = Column(
        Integer,
        nullable=True,
        index=True,
    )

    status = Column(
        String,
        default="CREATED",
        index=True,
    )

    picker_id = Column(
        Integer,
        nullable=True,
        index=True,
    )

    total_lines = Column(
        Integer,
        default=0,
    )

    total_units = Column(
        Integer,
        default=0,
    )

    picked_units = Column(
        Integer,
        default=0,
    )

    short_units = Column(
        Integer,
        default=0,
    )

    created_by = Column(
        Integer,
        nullable=True,
    )

    created_at = Column(
        String,
        nullable=False,
    )

    updated_at = Column(
        String,
        nullable=False,
    )


# ============================================================
# PICK ITEMS
# ============================================================

class WMSPickItem(Base):

    __tablename__ = "wms_pick_items"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    pick_list_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    order_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    order_item_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    product_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    sku = Column(
        String,
        nullable=False,
        index=True,
    )

    product_name = Column(
        String,
        nullable=False,
    )

    requested_qty = Column(
        Integer,
        nullable=False,
    )

    picked_qty = Column(
        Integer,
        default=0,
    )

    short_qty = Column(
        Integer,
        default=0,
    )

    status = Column(
        String,
        default="PENDING",
        index=True,
    )

    source_bin_id = Column(
        Integer,
        nullable=True,
        index=True,
    )

    created_at = Column(
        String,
        nullable=False,
    )

    updated_at = Column(
        String,
        nullable=False,
    )


# ============================================================
# SORT LIST
# ============================================================

class WMSSortList(Base):

    __tablename__ = "wms_sort_lists"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    sort_number = Column(
        String,
        unique=True,
        index=True,
        nullable=False,
    )

    pick_list_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    location_id = Column(
        Integer,
        nullable=True,
        index=True,
    )

    status = Column(
        String,
        default="CREATED",
        index=True,
    )

    sorter_id = Column(
        Integer,
        nullable=True,
        index=True,
    )

    total_lines = Column(
        Integer,
        default=0,
    )

    total_units = Column(
        Integer,
        default=0,
    )

    sorted_units = Column(
        Integer,
        default=0,
    )

    created_by = Column(
        Integer,
        nullable=True,
    )

    created_at = Column(
        String,
        nullable=False,
    )

    updated_at = Column(
        String,
        nullable=False,
    )


# ============================================================
# SORT ITEMS
# ============================================================

class WMSSortItem(Base):

    __tablename__ = "wms_sort_items"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    sort_list_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    order_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    order_item_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    product_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    sku = Column(
        String,
        nullable=False,
        index=True,
    )

    product_name = Column(
        String,
        nullable=False,
    )

    expected_qty = Column(
        Integer,
        nullable=False,
    )

    sorted_qty = Column(
        Integer,
        default=0,
    )

    status = Column(
        String,
        default="PENDING",
        index=True,
    )

    created_at = Column(
        String,
        nullable=False,
    )

    updated_at = Column(
        String,
        nullable=False,
    )


# ============================================================
# GRID PUTAWAY
# ============================================================

class WMSGridPutaway(Base):

    __tablename__ = "wms_grid_putaway"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    grid_number = Column(
        String,
        unique=True,
        index=True,
        nullable=False,
    )

    sort_list_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    location_id = Column(
        Integer,
        nullable=True,
        index=True,
    )

    status = Column(
        String,
        default="CREATED",
        index=True,
    )

    assigned_employee_id = Column(
        Integer,
        nullable=True,
        index=True,
    )

    total_lines = Column(
        Integer,
        default=0,
    )

    total_units = Column(
        Integer,
        default=0,
    )

    putaway_units = Column(
        Integer,
        default=0,
    )

    created_by = Column(
        Integer,
        nullable=True,
    )

    created_at = Column(
        String,
        nullable=False,
    )

    updated_at = Column(
        String,
        nullable=False,
    )


# ============================================================
# GRID PUTAWAY ITEMS
# ============================================================

class WMSGridPutawayItem(Base):

    __tablename__ = "wms_grid_putaway_items"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    grid_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    order_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    order_item_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    product_id = Column(
        Integer,
        nullable=False,
        index=True,
    )

    sku = Column(
        String,
        nullable=False,
        index=True,
    )

    product_name = Column(
        String,
        nullable=False,
    )

    quantity = Column(
        Integer,
        nullable=False,
    )

    putaway_qty = Column(
        Integer,
        default=0,
    )

    bin_id = Column(
        Integer,
        nullable=True,
        index=True,
    )

    status = Column(
        String,
        default="PENDING",
        index=True,
    )

    created_at = Column(
        String,
        nullable=False,
    )

    updated_at = Column(
        String,
        nullable=False,
    )


# ============================================================
# END OF ZIPPZO WMS V4 MODELS
# ============================================================