from pathlib import Path

p = Path("APP/batch_backend_v2_corrected.py")
s = p.read_text(encoding="utf-8")

# ------------------------------------------------------------
# 1. Import V4 models
# ------------------------------------------------------------
old_import = 'from .database import Base, engine, get_db\n'

new_import = '''from .database import Base, engine, get_db
from .models_v4 import WMSBatch, WMSBatchOrder
'''

if "from .models_v4 import WMSBatch, WMSBatchOrder" not in s:
    if old_import not in s:
        raise SystemExit("Could not find database import line")
    s = s.replace(old_import, new_import, 1)

# ------------------------------------------------------------
# 2. Remove legacy ORM model definitions
# ------------------------------------------------------------
start = s.find("class Batch(Base):")
end = s.find("def seed_batch_permissions", start)

if start == -1 or end == -1:
    raise SystemExit("Could not locate legacy Batch classes")

s = s[:start] + s[end:]

# ------------------------------------------------------------
# 3. Use V4 ORM classes everywhere
# ------------------------------------------------------------
s = s.replace("BatchOrder", "WMSBatchOrder")
s = s.replace("Batch", "WMSBatch")

# Undo accidental double replacement if any
s = s.replace("WMSWMSBatchOrder", "WMSBatchOrder")
s = s.replace("WMSWMSBatch", "WMSBatch")

# ------------------------------------------------------------
# 4. V2 field compatibility
# ------------------------------------------------------------
s = s.replace("batch.order_count", "batch.total_orders")
s = s.replace("batch.order_status", '"ALLOCATED"')

# Fields that do not exist in V4
s = s.replace("batch.notes", "None")
s = s.replace("batch.created_by_name", "None")
s = s.replace("batch.cancelled_by", "None")
s = s.replace("batch.cancelled_by_name", "None")

# ------------------------------------------------------------
# 5. Replace V2 Batch constructor fields
# ------------------------------------------------------------
s = s.replace(
    "order_count=0,\n"
    "        total_units=0,\n"
    "        priority=",
    "total_orders=0,\n"
    "        total_units=0,\n"
    "        priority=",
)

s = s.replace(
    'status="CREATED",\n'
    '        order_status=requested_status,\n'
    '        notes=data.notes,\n'
    '        created_by=employee.id,\n'
    '        created_by_name=employee.full_name,',
    'status="CREATED",\n'
    '        created_by=employee.id,',
)

# Excel-created batches
s = s.replace(
    'order_count=0,\n'
    '            total_units=0,\n'
    '            priority=priority,\n'
    '            status="CREATED",\n'
    '            order_status=order_status,\n'
    '            notes=(\n'
    '                "Created from Excel upload: "\n'
    '                f"{file.filename}"\n'
    '            ),\n'
    '            created_by=employee.id,\n'
    '            created_by_name=employee.full_name,',
    'total_orders=0,\n'
    '            total_units=0,\n'
    '            priority=priority,\n'
    '            status="CREATED",\n'
    '            created_by=employee.id,',
)

# ------------------------------------------------------------
# 6. V2 BatchOrder constructor -> V4 BatchOrder
# ------------------------------------------------------------
s = s.replace(
    'WMSBatchOrder(\n'
    '                batch_id=batch.id,\n'
    '                order_id=order.id,\n'
    '                order_number=order.order_number,\n'
    '                quantity=quantity,\n'
    '                status="IN_BATCH",\n'
    '                created_at=created_time,\n'
    '            )',
    'WMSBatchOrder(\n'
    '                batch_id=batch.id,\n'
    '                order_id=order.id,\n'
    '                order_status_before=order.status,\n'
    '                created_at=created_time,\n'
    '            )',
)

s = s.replace(
    'WMSBatchOrder(\n'
    '                    batch_id=batch.id,\n'
    '                    order_id=item["order_id"],\n'
    '                    order_number=item["order_number"],\n'
    '                    quantity=quantity,\n'
    '                    status="IN_BATCH",\n'
    '                    created_at=batch_time,\n'
    '                )',
    'WMSBatchOrder(\n'
    '                    batch_id=batch.id,\n'
    '                    order_id=item["order_id"],\n'
    '                    order_status_before=order_status,\n'
    '                    created_at=batch_time,\n'
    '                )',
)

# ------------------------------------------------------------
# 7. V4 has no BatchOrder.status column
# ------------------------------------------------------------
s = s.replace(
    '        batch_order.status = "BATCH_CANCELLED"\n',
    ''
)

p.write_text(s, encoding="utf-8")
print("V4 batch migration patch applied successfully")
