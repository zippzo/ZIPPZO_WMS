from pathlib import Path

p = Path("APP/batch_backend_v2_corrected.py")
s = p.read_text(encoding="utf-8")

# Add V4 model imports
old = "from .database import Base, engine, get_db\n"

new = """from .database import Base, engine, get_db
from .models_v4 import WMSBatch, WMSBatchOrder
"""

if "from .models_v4 import WMSBatch, WMSBatchOrder" not in s:
    if old not in s:
        raise SystemExit("Database import line not found")
    s = s.replace(old, new, 1)

# Replace ONLY the two legacy ORM classes.
start = s.index("class Batch(Base):")
end = s.index("# Only creates missing Batch tables.", start)

replacement = """Batch = WMSBatch
BatchOrder = WMSBatchOrder

"""

s = s[:start] + replacement + s[end:]

# Do not let this legacy module create duplicate ORM tables.
s = s.replace(
    "# Only creates missing Batch tables.\n"
    "Base.metadata.create_all(bind=engine)\n",
    ""
)

p.write_text(s, encoding="utf-8")
print("CONTROLLED MODEL FIX APPLIED")
