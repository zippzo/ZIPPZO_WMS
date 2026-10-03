"""
Zippzo WMS - Batch V2 Setup / Test

Run from the ZIPPZO_WMS project root:
python -m APP.batch_setup_v2

This script creates only the new Batch tables and Batch permissions.
It does NOT delete or reset existing WMS data.
It does NOT modify main.py.
"""

from .database import Base, engine, SessionLocal
from .batch_backend_v2_corrected import Batch, BatchOrder, seed_batch_permissions


def main():
    print("=" * 60)
    print("ZIPPZO WMS - BATCH V2 SETUP")
    print("=" * 60)

    print("\n[1/3] Creating Batch tables...")
    Base.metadata.create_all(bind=engine)
    print("OK - wms_batches")
    print("OK - wms_batch_orders")

    print("\n[2/3] Setting Batch permissions...")
    db = SessionLocal()

    try:
        seed_batch_permissions(db)
        print("OK - BATCH_VIEW")
        print("OK - BATCH_UPLOAD")
        print("OK - BATCH_CREATE")
        print("OK - BATCH_CANCEL")
        print("OK - Admin permissions")
        print("OK - Operations Manager permissions")
    finally:
        db.close()

    print("\n[3/3] Setup verification...")
    db = SessionLocal()

    try:
        batch_count = db.query(Batch).count()
        batch_order_count = db.query(BatchOrder).count()

        print(f"Existing batches preserved: {batch_count}")
        print(f"Existing batch-order links preserved: {batch_order_count}")
    finally:
        db.close()

    print("\n" + "=" * 60)
    print("BATCH V2 SETUP COMPLETED")
    print("No existing WMS records were deleted.")
    print("=" * 60)


if __name__ == "__main__":
    main()

