from .database import Base, engine
from . import models
from .models_v4 import (
    WMSBatch, WMSBatchOrder,
    WMSPickList, WMSPickItem,
    WMSSortList, WMSSortItem,
    WMSGridPutaway, WMSGridPutawayItem,
)

def main():
    # create_all ONLY creates missing tables; it does not drop or reset existing data.
    Base.metadata.create_all(bind=engine)
    print("Zippzo WMS V4 tables created/verified successfully.")
    for name in [
        "wms_batches", "wms_batch_orders",
        "wms_pick_lists", "wms_pick_items",
        "wms_sort_lists", "wms_sort_items",
        "wms_grid_putaway", "wms_grid_putaway_items",
    ]:
        print("  OK:", name)

if __name__ == "__main__":
    main()
