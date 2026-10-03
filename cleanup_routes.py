from pathlib import Path

p = Path("APP/main.py")
s = p.read_text(encoding="utf-8")

marker = "# BIN INVENTORY"
starts = [i for i in range(len(s)) if s.startswith(marker, i)]

if len(starts) != 3:
    raise SystemExit(f"STOP: expected 3 BIN INVENTORY sections, found {len(starts)}")

# Keep everything before the first duplicate Bin Inventory section.
# The actual Putaway logic before this point remains untouched.
prefix = s[:starts[0]]

bin_endpoint = '''# =========================================================
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
'''

p.write_text(prefix.rstrip() + "\n\n" + bin_endpoint, encoding="utf-8")

print("CLEANUP COMPLETE")
print("Database was NOT modified.")
print("Kept Putaway logic before the duplicate Bin Inventory sections.")
print("Created exactly one Bin Inventory endpoint and one final frontend mount.")
