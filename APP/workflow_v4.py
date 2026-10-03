from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .database import get_db
from .models import (
    Employee, Order, OrderItem, Product, Inventory, Bin,
    StockMovement, AuditLog
)
from .models_v4 import (
    WMSBatch, WMSBatchOrder,
    WMSPickList, WMSPickItem,
    WMSSortList, WMSSortItem,
    WMSGridPutaway, WMSGridPutawayItem,
)

router = APIRouter(prefix="/api/v4", tags=["Zippzo WMS V4 Workflow"])

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def actor(db, employee_id):
    e = db.query(Employee).filter(Employee.id == employee_id).first()
    if not e or str(e.status).upper() != "ACTIVE":
        raise HTTPException(403, "Active employee account required")
    return e

def audit(db, employee, action, module, ref, description):
    db.add(AuditLog(
        employee_id=employee.id,
        employee_name=employee.full_name,
        action=action,
        module=module,
        reference_id=str(ref) if ref is not None else None,
        description=description,
        created_at=now(),
    ))

def next_number(db, model, field, prefix):
    last = db.query(model).order_by(model.id.desc()).first()
    n = (last.id if last else 0) + 1
    return f"{prefix}-{n:06d}"

class ActionRequest(BaseModel):
    employee_id: int

class PickRequest(BaseModel):
    employee_id: int
    picked_qty: int = Field(ge=0)

class SortRequest(BaseModel):
    employee_id: int
    sorted_qty: int = Field(ge=0)

class GridPutawayRequest(BaseModel):
    employee_id: int
    bin_id: int
    quantity: int = Field(gt=0)

@router.get("/health")
def v4_health():
    return {"status": "OK", "version": "4.0.0", "workflow": "BATCH-PICK-SORT-GRID"}

@router.get("/batches")
def batches(db: Session = Depends(get_db)):
    rows = db.query(WMSBatch).order_by(WMSBatch.id.desc()).all()
    return [r.__dict__ | {"_sa_instance_state": None} for r in rows]

@router.post("/batches/{batch_id}/create-pick-list")
def create_pick_list(batch_id: int, data: ActionRequest, db: Session = Depends(get_db)):
    employee = actor(db, data.employee_id)
    batch = db.query(WMSBatch).filter(WMSBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "Batch not found")
    if str(batch.status).upper() in {"CANCELLED", "COMPLETED"}:
        raise HTTPException(409, "Batch is not available for picking")

    existing = db.query(WMSPickList).filter(WMSPickList.batch_id == batch_id).first()
    if existing:
        return {"message": "Pick list already exists", "pick_list_id": existing.id}

    links = db.query(WMSBatchOrder).filter(WMSBatchOrder.batch_id == batch_id).all()
    if not links:
        raise HTTPException(409, "Batch has no orders")

    pick = WMSPickList(
        pick_number=next_number(db, WMSPickList, WMSPickList.pick_number, "ZPK"),
        batch_id=batch.id, location_id=batch.location_id,
        status="CREATED", created_by=employee.id,
        created_at=now(), updated_at=now()
    )
    db.add(pick)
    db.flush()

    total_lines = total_units = 0
    for link in links:
        items = db.query(OrderItem).filter(OrderItem.order_id == link.order_id).all()
        for oi in items:
            qty = int(oi.quantity or 0)
            if qty <= 0:
                continue
            product = db.query(Product).filter(Product.id == oi.product_id).first()
            sku = oi.sku or (product.sku if product else f"PRODUCT-{oi.product_id}")
            name = oi.product_name or (product.product_name if product else sku)
            db.add(WMSPickItem(
                pick_list_id=pick.id, order_id=oi.order_id,
                order_item_id=oi.id, product_id=oi.product_id,
                sku=sku, product_name=name, requested_qty=qty,
                created_at=now(), updated_at=now()
            ))
            total_lines += 1
            total_units += qty

    pick.total_lines = total_lines
    pick.total_units = total_units
    pick.status = "READY"
    batch.status = "PICKING_READY"
    batch.updated_at = now()
    audit(db, employee, "CREATE", "PICKING", pick.pick_number, f"Created pick list for batch {batch.batch_number}")
    db.commit()
    return {"message": "Pick list created", "pick_list_id": pick.id, "pick_number": pick.pick_number}

@router.get("/pick-lists")
def pick_lists(db: Session = Depends(get_db)):
    rows = db.query(WMSPickList).order_by(WMSPickList.id.desc()).all()
    return [r.__dict__ | {"_sa_instance_state": None} for r in rows]

@router.post("/pick-lists/{pick_id}/assign")
def assign_picker(pick_id: int, data: ActionRequest, db: Session = Depends(get_db)):
    employee = actor(db, data.employee_id)
    pick = db.query(WMSPickList).filter(WMSPickList.id == pick_id).first()
    if not pick:
        raise HTTPException(404, "Pick list not found")
    pick.picker_id = employee.id
    pick.status = "ASSIGNED"
    pick.updated_at = now()
    audit(db, employee, "ASSIGN", "PICKING", pick.pick_number, f"Picker assigned: {employee.employee_id}")
    db.commit()
    return {"message": "Picker assigned"}

@router.post("/pick-lists/{pick_id}/remove-assignment")
def remove_picker(pick_id: int, data: ActionRequest, db: Session = Depends(get_db)):
    employee = actor(db, data.employee_id)
    pick = db.query(WMSPickList).filter(WMSPickList.id == pick_id).first()
    if not pick:
        raise HTTPException(404, "Pick list not found")
    pick.picker_id = None
    pick.status = "READY"
    pick.updated_at = now()
    audit(db, employee, "UNASSIGN", "PICKING", pick.pick_number, "Picker assignment removed")
    db.commit()
    return {"message": "Picker assignment removed"}

@router.post("/pick-items/{item_id}/pick")
def pick_item(item_id: int, data: PickRequest, db: Session = Depends(get_db)):
    employee = actor(db, data.employee_id)
    item = db.query(WMSPickItem).filter(WMSPickItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Pick item not found")
    pick = db.query(WMSPickList).filter(WMSPickList.id == item.pick_list_id).first()
    if not pick or pick.picker_id != employee.id:
        raise HTTPException(403, "This pick list is not assigned to you")

    if data.picked_qty > item.requested_qty:
        raise HTTPException(400, "Picked quantity cannot exceed requested quantity")

    item.picked_qty = data.picked_qty
    item.short_qty = item.requested_qty - data.picked_qty
    item.status = "PICKED" if data.picked_qty == item.requested_qty else "SHORT"
    item.updated_at = now()

    pick.picked_units = sum(int(x.picked_qty or 0) for x in db.query(WMSPickItem).filter(WMSPickItem.pick_list_id == pick.id))
    pick.short_units = sum(int(x.short_qty or 0) for x in db.query(WMSPickItem).filter(WMSPickItem.pick_list_id == pick.id))
    pick.status = "PICKING"
    pick.updated_at = now()
    audit(db, employee, "PICK", "PICKING", pick.pick_number, f"{item.sku}: {data.picked_qty}")
    db.commit()
    return {"message": "Pick quantity saved", "picked_qty": item.picked_qty, "short_qty": item.short_qty}

@router.post("/pick-lists/{pick_id}/complete")
def complete_pick(pick_id: int, data: ActionRequest, db: Session = Depends(get_db)):
    employee = actor(db, data.employee_id)
    pick = db.query(WMSPickList).filter(WMSPickList.id == pick_id).first()
    if not pick or pick.picker_id != employee.id:
        raise HTTPException(403, "Pick list is not assigned to you")
    items = db.query(WMSPickItem).filter(WMSPickItem.pick_list_id == pick.id).all()
    if not items or any(i.status == "PENDING" for i in items):
        raise HTTPException(409, "All pick lines must be processed")
    pick.status = "COMPLETED"
    pick.updated_at = now()
    batch = db.query(WMSBatch).filter(WMSBatch.id == pick.batch_id).first()
    if batch:
        batch.status = "PICKED"
        batch.updated_at = now()
    audit(db, employee, "COMPLETE", "PICKING", pick.pick_number, "Pick list completed")
    db.commit()
    return {"message": "Pick list completed"}

@router.post("/pick-lists/{pick_id}/create-sort-list")
def create_sort_list(pick_id: int, data: ActionRequest, db: Session = Depends(get_db)):
    employee = actor(db, data.employee_id)
    pick = db.query(WMSPickList).filter(WMSPickList.id == pick_id).first()
    if not pick or pick.status != "COMPLETED":
        raise HTTPException(409, "Pick list must be completed")
    existing = db.query(WMSSortList).filter(WMSSortList.pick_list_id == pick.id).first()
    if existing:
        return {"message": "Sort list already exists", "sort_list_id": existing.id}

    sort = WMSSortList(
        sort_number=next_number(db, WMSSortList, WMSSortList.sort_number, "ZSO"),
        pick_list_id=pick.id, location_id=pick.location_id,
        status="READY", created_by=employee.id, created_at=now(), updated_at=now()
    )
    db.add(sort)
    db.flush()

    items = db.query(WMSPickItem).filter(WMSPickItem.pick_list_id == pick.id, WMSPickItem.picked_qty > 0).all()
    for pi in items:
        db.add(WMSSortItem(
            sort_list_id=sort.id, order_id=pi.order_id, order_item_id=pi.order_item_id,
            product_id=pi.product_id, sku=pi.sku, product_name=pi.product_name,
            expected_qty=pi.picked_qty, created_at=now(), updated_at=now()
        ))
    sort.total_lines = len(items)
    sort.total_units = sum(int(i.picked_qty or 0) for i in items)
    audit(db, employee, "CREATE", "SORTING", sort.sort_number, "Sort list created")
    db.commit()
    return {"message": "Sort list created", "sort_list_id": sort.id, "sort_number": sort.sort_number}

@router.get("/sort-lists")
def sort_lists(db: Session = Depends(get_db)):
    rows = db.query(WMSSortList).order_by(WMSSortList.id.desc()).all()
    return [r.__dict__ | {"_sa_instance_state": None} for r in rows]

@router.post("/sort-lists/{sort_id}/assign")
def assign_sorter(sort_id: int, data: ActionRequest, db: Session = Depends(get_db)):
    employee = actor(db, data.employee_id)
    sort = db.query(WMSSortList).filter(WMSSortList.id == sort_id).first()
    if not sort:
        raise HTTPException(404, "Sort list not found")
    sort.sorter_id = employee.id
    sort.status = "ASSIGNED"
    sort.updated_at = now()
    audit(db, employee, "ASSIGN", "SORTING", sort.sort_number, f"Sorter assigned: {employee.employee_id}")
    db.commit()
    return {"message": "Sorter assigned"}

@router.post("/sort-items/{item_id}/sort")
def sort_item(item_id: int, data: SortRequest, db: Session = Depends(get_db)):
    employee = actor(db, data.employee_id)
    item = db.query(WMSSortItem).filter(WMSSortItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Sort item not found")
    sort = db.query(WMSSortList).filter(WMSSortList.id == item.sort_list_id).first()
    if not sort or sort.sorter_id != employee.id:
        raise HTTPException(403, "This sort list is not assigned to you")
    if data.sorted_qty > item.expected_qty:
        raise HTTPException(400, "Sorted quantity cannot exceed expected quantity")
    item.sorted_qty = data.sorted_qty
    item.status = "SORTED" if data.sorted_qty == item.expected_qty else "PARTIAL"
    item.updated_at = now()
    sort.sorted_units = sum(int(x.sorted_qty or 0) for x in db.query(WMSSortItem).filter(WMSSortItem.sort_list_id == sort.id))
    sort.status = "SORTING"
    sort.updated_at = now()
    audit(db, employee, "SORT", "SORTING", sort.sort_number, f"{item.sku}: {data.sorted_qty}")
    db.commit()
    return {"message": "Sorting quantity saved"}

@router.post("/sort-lists/{sort_id}/complete")
def complete_sort(sort_id: int, data: ActionRequest, db: Session = Depends(get_db)):
    employee = actor(db, data.employee_id)
    sort = db.query(WMSSortList).filter(WMSSortList.id == sort_id).first()
    if not sort or sort.sorter_id != employee.id:
        raise HTTPException(403, "This sort list is not assigned to you")
    items = db.query(WMSSortItem).filter(WMSSortItem.sort_list_id == sort.id).all()
    if not items or any(i.status == "PENDING" for i in items):
        raise HTTPException(409, "All sort lines must be processed")
    sort.status = "COMPLETED"
    sort.updated_at = now()
    audit(db, employee, "COMPLETE", "SORTING", sort.sort_number, "Sort list completed")
    db.commit()
    return {"message": "Sort list completed"}

@router.post("/sort-lists/{sort_id}/create-grid-putaway")
def create_grid_putaway(sort_id: int, data: ActionRequest, db: Session = Depends(get_db)):
    employee = actor(db, data.employee_id)
    sort = db.query(WMSSortList).filter(WMSSortList.id == sort_id).first()
    if not sort or sort.status != "COMPLETED":
        raise HTTPException(409, "Sort list must be completed")
    existing = db.query(WMSGridPutaway).filter(WMSGridPutaway.sort_list_id == sort.id).first()
    if existing:
        return {"message": "Grid putaway already exists", "grid_id": existing.id}

    grid = WMSGridPutaway(
        grid_number=next_number(db, WMSGridPutaway, WMSGridPutaway.grid_number, "ZGP"),
        sort_list_id=sort.id, location_id=sort.location_id,
        status="READY", created_by=employee.id, created_at=now(), updated_at=now()
    )
    db.add(grid)
    db.flush()

    items = db.query(WMSSortItem).filter(WMSSortItem.sort_list_id == sort.id, WMSSortItem.sorted_qty > 0).all()
    for si in items:
        db.add(WMSGridPutawayItem(
            grid_id=grid.id, order_id=si.order_id, order_item_id=si.order_item_id,
            product_id=si.product_id, sku=si.sku, product_name=si.product_name,
            quantity=si.sorted_qty, created_at=now(), updated_at=now()
        ))
    grid.total_lines = len(items)
    grid.total_units = sum(int(i.sorted_qty or 0) for i in items)
    audit(db, employee, "CREATE", "GRID_PUTAWAY", grid.grid_number, "Grid putaway created")
    db.commit()
    return {"message": "Grid putaway created", "grid_id": grid.id, "grid_number": grid.grid_number}

@router.get("/grid-putaway")
def grid_putaway(db: Session = Depends(get_db)):
    rows = db.query(WMSGridPutaway).order_by(WMSGridPutaway.id.desc()).all()
    return [r.__dict__ | {"_sa_instance_state": None} for r in rows]

@router.post("/grid-putaway/{grid_id}/putaway")
def complete_grid_item(grid_id: int, data: GridPutawayRequest, db: Session = Depends(get_db)):
    employee = actor(db, data.employee_id)
    grid = db.query(WMSGridPutaway).filter(WMSGridPutaway.id == grid_id).first()
    if not grid:
        raise HTTPException(404, "Grid putaway not found")

    item = db.query(WMSGridPutawayItem).filter(
        WMSGridPutawayItem.grid_id == grid_id,
        WMSGridPutawayItem.status != "COMPLETED"
    ).first()
    if not item:
        raise HTTPException(409, "No pending grid item")

    if data.quantity > item.quantity:
        raise HTTPException(400, "Quantity exceeds grid quantity")

    bin_record = db.query(Bin).filter(
        Bin.id == data.bin_id,
        Bin.location_id == grid.location_id
    ).first()
    if not bin_record:
        raise HTTPException(404, "Bin not found at grid location")

    item.bin_id = bin_record.id
    item.putaway_qty = data.quantity
    item.status = "COMPLETED" if data.quantity == item.quantity else "PARTIAL"
    item.updated_at = now()

    # Update bin inventory only after grid putaway.
    if data.quantity > 0:
        bi = None
        try:
            from .models import BinInventory
            bi = db.query(BinInventory).filter(
                BinInventory.location_id == grid.location_id,
                BinInventory.bin_id == bin_record.id,
                BinInventory.product_id == item.product_id,
            ).first()
            if not bi:
                bi = BinInventory(
                    location_id=grid.location_id, bin_id=bin_record.id,
                    product_id=item.product_id, sku=item.sku,
                    available_qty=0, reserved_qty=0, picked_qty=0,
                    damaged_qty=0, quarantine_qty=0,
                    created_at=now(), updated_at=now()
                )
                db.add(bi)
            bi.available_qty += data.quantity
            bi.updated_at = now()
        except Exception:
            db.rollback()
            raise

    grid.putaway_units = sum(int(x.putaway_qty or 0) for x in db.query(WMSGridPutawayItem).filter(WMSGridPutawayItem.grid_id == grid.id))
    grid.status = "COMPLETED" if grid.putaway_units >= grid.total_units else "IN_PROGRESS"
    grid.updated_at = now()
    audit(db, employee, "PUTAWAY", "GRID_PUTAWAY", grid.grid_number, f"{item.sku}: {data.quantity} to {bin_record.bin_code}")
    db.commit()
    return {"message": "Grid putaway saved", "grid_number": grid.grid_number, "bin_code": bin_record.bin_code}
