"""Deterministic seed for the Loomora records DB (PLAN.md §5, Checklist.md data table).

Idempotent: drops and rebuilds all tables from db/schema.sql, then inserts fixed rows.
After seeding it ASSERTS every data dependency named in Checklist.md — including the
day-count math for the return-window edge cases — so M2's acceptance criterion
("every Checklist scenario's Data: rows exist") is machine-checked on every run.

Run:  .venv/Scripts/python db/seed.py
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

SCHEMA = Path(__file__).with_name("schema.sql")

CUSTOMERS = [
    # id, name, email, phone, tier, created_at
    ("C001", "Maya Fernandes", "maya.fernandes@example.com", "+1-555-0101", "Gold",   "2023-04-12"),
    ("C002", "Rohan Iyer",     "rohan.iyer@example.com",     "+1-555-0102", "Basic",  "2025-11-03"),
    ("C003", "Sarah Kim",      "sarah.kim@example.com",      "+1-555-0103", "Silver", "2024-06-21"),
    ("C004", "David Okafor",   "david.okafor@example.com",   "+1-555-0104", "Basic",  "2026-01-15"),
    ("C005", "Emily Watson",   "emily.watson@example.com",   "+1-555-0105", "Gold",   "2022-09-30"),
    ("C006", "Lucas Meyer",    "lucas.meyer@example.com",    "+1-555-0106", "Basic",  "2026-05-02"),
    ("C007", "Priya Nair",     "priya.nair@example.com",     "+1-555-0107", "Silver", "2024-02-18"),
    ("C008", "Tom Alvarez",    "tom.alvarez@example.com",    "+1-555-0108", "Basic",  "2025-08-11"),
    ("C009", "Grace Liu",      "grace.liu@example.com",      "+1-555-0109", "Silver", "2023-12-05"),
    ("C010", "Omar Haddad",    "omar.haddad@example.com",    "+1-555-0110", "Basic",  "2026-03-27"),
]

PRODUCTS = [
    # id, name, category, size, color, price, stock, final_sale, care_notes
    ("P001", "Aurora Linen Shirt",      "tops",        "M", "White",        49.00, 25, 0, "Machine wash cold, hang dry"),
    ("P002", "Aurora Linen Shirt",      "tops",        "S", "White",        49.00,  0, 0, "Machine wash cold, hang dry"),
    ("P003", "Ridge Denim Jacket",      "outerwear",   "L", "Indigo",      129.00,  8, 0, "Machine wash cold inside out"),
    # P004 is priced BELOW O1012's unit_price (69.00) on purpose: S-V4-07 needs a real
    # price drop for the price-adjustment scenario ($10 store credit).
    ("P004", "Cloudsoft Hoodie",        "tops",        "M", "Heather Grey", 59.00, 40, 0, "Machine wash warm, tumble low"),
    ("P005", "Cloudsoft Hoodie",        "tops",        "L", "Heather Grey", 69.00, 35, 0, "Machine wash warm, tumble low"),
    ("P006", "Meridian Chinos",         "bottoms",     "32", "Khaki",       79.00, 15, 0, "Machine wash cold"),
    ("P007", "Solstice Maxi Dress",     "dresses",     "M", "Terracotta",   99.00, 12, 0, "Gentle cycle cold, line dry"),
    ("P008", "Solstice Maxi Dress",     "dresses",     "S", "Terracotta",   99.00,  0, 0, "Gentle cycle cold, line dry"),
    ("P009", "Ember Wool Coat",         "outerwear",   "M", "Camel",       249.00,  5, 0, "Dry clean only"),
    ("P010", "Drift Jogger",            "bottoms",     "M", "Black",        59.00, 30, 0, "Machine wash cold"),
    ("P011", "Halo Silk Scarf",         "accessories", "One Size", "Blush", 39.00, 18, 1, "Dry clean only"),
    ("P012", "Vertex Puffer Vest",      "outerwear",   "L", "Forest",       89.00,  7, 1, "Spot clean, do not wash"),
    ("P013", "Cascade Rib Knit Sweater","tops",        "M", "Cream",        85.00, 20, 0, "Hand wash cold, dry flat, do not tumble dry"),
    ("P014", "Basalt Graphic Tee",      "tops",        "L", "Black",        29.00, 50, 1, "Machine wash cold inside out"),
    ("P015", "Tidal Swim Shorts",       "bottoms",     "M", "Navy",         45.00, 22, 0, "Rinse after use, drip dry"),
    ("P016", "Nimbus Rain Shell",       "outerwear",   "M", "Slate",       119.00, 10, 0, "Machine wash cold, no fabric softener"),
    ("P017", "Terra Cargo Pants",       "bottoms",     "34", "Olive",       74.00, 14, 0, "Machine wash cold"),
    ("P018", "Lumen Slip Dress",        "dresses",     "M", "Black",        89.00,  9, 0, "Hand wash cold or dry clean"),
    ("P019", "Orbit Beanie",            "accessories", "One Size", "Rust",  25.00, 60, 0, "Hand wash cold, reshape and dry flat"),
    ("P020", "Strata Overshirt",        "tops",        "M", "Ochre",        95.00, 11, 0, "Machine wash cold, hang dry"),
]

ADDR = {c[0]: f"{i + 1}0{i + 2} {c[1].split()[1]} St, Springfield, IL" for i, c in enumerate(CUSTOMERS)}

ORDERS = [
    # id, customer, order_date, status, carrier, tracking, expected_delivery, delivered_date, total
    ("O1001", "C001", "2026-07-01", "shipped",    "SwiftShip", "SS-88231", "2026-07-07", None,         94.00),
    ("O1002", "C002", "2026-06-22", "delayed",    "SwiftShip", "SS-77120", "2026-06-28", None,        119.00),
    ("O1003", "C003", "2026-06-26", "delivered",  "ParcelPro", "PP-51002", "2026-06-30", "2026-06-30", 85.00),
    ("O1004", "C004", "2026-05-25", "delivered",  "ParcelPro", "PP-49881", "2026-05-30", "2026-05-30", 79.00),
    ("O1005", "C005", "2026-05-25", "delivered",  "SwiftShip", "SS-61200", "2026-05-30", "2026-05-30", 249.00),
    ("O1006", "C006", "2026-07-03", "placed",     None,        None,       "2026-07-09", None,         59.00),
    ("O1007", "C007", "2026-07-01", "shipped",    "SwiftShip", "SS-90111", "2026-07-06", None,         74.00),
    ("O1008", "C008", "2026-06-25", "delivered",  "ParcelPro", "PP-50990", "2026-06-29", "2026-06-29", 29.00),
    ("O1009", "C009", "2026-06-20", "delivered",  "ParcelPro", "PP-50761", "2026-06-24", "2026-06-24", 39.00),
    ("O1010", "C002", "2026-06-21", "delivered",  "SwiftShip", "SS-75210", "2026-06-26", "2026-06-26", 89.00),
    ("O1011", "C001", "2026-06-30", "processing", None,        None,       "2026-07-06", None,         95.00),
    ("O1012", "C003", "2026-06-28", "delivered",  "ParcelPro", "PP-51344", "2026-07-02", "2026-07-02", 69.00),
    ("O1013", "C004", "2026-05-29", "delivered",  "ParcelPro", "PP-50003", "2026-06-03", "2026-06-03", 89.00),
    ("O1014", "C007", "2026-07-03", "placed",     None,        None,       "2026-07-09", None,         94.00),
    ("O1015", "C005", "2026-07-02", "shipped",    "SwiftShip", "SS-91555", "2026-07-08", None,        129.00),
    ("O1016", "C009", "2026-06-24", "delivered",  "ParcelPro", "PP-50811", "2026-06-28", "2026-06-28", 99.00),
    ("O1017", "C010", "2026-06-12", "delivered",  "SwiftShip", "SS-70021", "2026-06-16", "2026-06-16", 59.00),
    ("O1018", "C008", "2026-06-29", "delivered",  "ParcelPro", "PP-51520", "2026-07-02", "2026-07-02", 99.00),
]

ORDER_ITEMS = [
    ("O1001", "P004", 1, 69.00), ("O1001", "P019", 1, 25.00),
    ("O1002", "P016", 1, 119.00),
    ("O1003", "P013", 1, 85.00),
    ("O1004", "P006", 1, 79.00),
    ("O1005", "P009", 1, 249.00),
    ("O1006", "P010", 1, 59.00),
    ("O1007", "P017", 1, 74.00),
    ("O1008", "P014", 1, 29.00),
    ("O1009", "P011", 1, 39.00),
    ("O1010", "P012", 1, 89.00),
    ("O1011", "P020", 1, 95.00),
    ("O1012", "P004", 1, 69.00),
    ("O1013", "P018", 1, 89.00),
    ("O1014", "P001", 1, 49.00), ("O1014", "P015", 1, 45.00),
    ("O1015", "P003", 1, 129.00),
    ("O1016", "P007", 1, 99.00),
    ("O1017", "P010", 1, 59.00),
    ("O1018", "P007", 1, 99.00),
]

RETURNS = [
    # id, order, product, reason, status, refund_amount, initiated
    ("R2001", "O1016", "P007", "too large",    "label_sent", None,  "2026-06-29"),
    ("R2002", "O1017", "P010", "changed mind", "refunded",   59.00, "2026-06-20"),
]

PROMOS = [
    # code, pct, from, to, min_order, active
    ("SUMMER20",  20, "2026-06-01", "2026-07-31",  75.00, 1),
    ("FLASH15",   15, "2026-06-20", "2026-07-03",   0.00, 1),  # expired by date, flag still on
    ("WELCOME10", 10, "2026-01-01", "2026-12-31",   0.00, 1),
    ("VIP25",     25, "2026-06-01", "2026-08-31", 150.00, 1),
]


def seed(conn: sqlite3.Connection) -> None:
    conn.executescript(
        "DROP TABLE IF EXISTS tickets; DROP TABLE IF EXISTS promos;"
        "DROP TABLE IF EXISTS returns; DROP TABLE IF EXISTS order_items;"
        "DROP TABLE IF EXISTS orders; DROP TABLE IF EXISTS products;"
        "DROP TABLE IF EXISTS customers;"
    )
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", CUSTOMERS)
    conn.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?)", PRODUCTS)
    conn.executemany(
        "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(o[0], o[1], o[2], o[3], o[4], o[5], ADDR[o[1]], o[6], o[7], o[8]) for o in ORDERS],
    )
    conn.executemany("INSERT INTO order_items VALUES (?,?,?,?)", ORDER_ITEMS)
    conn.executemany("INSERT INTO returns VALUES (?,?,?,?,?,?,?)", RETURNS)
    conn.executemany("INSERT INTO promos VALUES (?,?,?,?,?,?)", PROMOS)
    conn.commit()


def verify(conn: sqlite3.Connection) -> None:
    """Assert every Checklist.md data dependency. Raises AssertionError with the scenario id."""
    q = conn.execute
    ref = config.REFERENCE_DATE

    def one(sql: str, *args):
        row = q(sql, args).fetchone()
        assert row is not None, f"missing row: {sql} {args}"
        return row

    def days_since_delivery(order_id: str) -> int:
        (d,) = one("SELECT delivered_date FROM orders WHERE order_id=?", order_id)
        return (ref - date.fromisoformat(d)).days

    # --- integrity: order totals match their items
    for oid, total in [(o[0], o[8]) for o in ORDERS]:
        (s,) = one("SELECT SUM(qty*unit_price) FROM order_items WHERE order_id=?", oid)
        assert abs(s - total) < 0.01, f"{oid}: total {total} != items sum {s}"

    # --- customers & tiers (V2-03, V2-02, S-V5-05 …)
    assert q("SELECT COUNT(*) FROM customers").fetchone()[0] == 10
    for cid, tier in [("C001", "Gold"), ("C005", "Gold"), ("C003", "Silver"),
                      ("C007", "Silver"), ("C009", "Silver"), ("C004", "Basic")]:
        assert one("SELECT loyalty_tier FROM customers WHERE customer_id=?", cid)[0] == tier, cid

    # --- products (V3-01/02/04/05, V2-04/05/07)
    assert one("SELECT stock_qty FROM products WHERE product_id='P001'")[0] > 0, "S-V3-01"
    assert one("SELECT stock_qty FROM products WHERE product_id='P002'")[0] == 0, "S-V3-02"
    assert one("SELECT stock_qty FROM products WHERE product_id='P008'")[0] == 0, "S-V2-07/S-V3-05"
    assert one("SELECT stock_qty FROM products WHERE product_id='P005'")[0] > 0, "S-V2-06"
    for pid in ("P011", "P012", "P014"):
        assert one("SELECT final_sale FROM products WHERE product_id=?", pid)[0] == 1, pid
    assert "hand wash cold" in one("SELECT care_notes FROM products WHERE product_id='P013'")[0].lower(), "S-V3-04"
    assert one("SELECT color FROM products WHERE product_id='P003'")[0] == "Indigo", "S-V3-06"

    # --- order statuses (V1 flows)
    for oid, status in [("O1001", "shipped"), ("O1002", "delayed"), ("O1006", "placed"),
                        ("O1007", "shipped"), ("O1011", "processing"), ("O1014", "placed"),
                        ("O1015", "shipped")]:
        assert one("SELECT status FROM orders WHERE order_id=?", oid)[0] == status, oid
    assert one("SELECT expected_delivery FROM orders WHERE order_id='O1002'")[0] < ref.isoformat(), "S-V1-02 past due"
    assert one("SELECT tracking_no FROM orders WHERE order_id='O1001'")[0] == "SS-88231", "S-V1-01"
    assert one("SELECT COUNT(*) FROM orders WHERE customer_id='C002'")[0] == 2, "S-V1-08 two orders"

    # --- return-window day math (the heart of V2's edge cases)
    assert days_since_delivery("O1003") == 4,  "S-V2-01 expects day 4"
    assert days_since_delivery("O1013") == 31, "S-V2-02 expects day 31 (just outside 30)"
    assert days_since_delivery("O1004") == 35, "S-V6-04 expects day 35 (Basic, outside)"
    assert days_since_delivery("O1005") == 35, "S-V2-03 expects day 35 (Gold, inside 40)"
    assert days_since_delivery("O1012") in range(0, 8), "S-V4-07 price-adjust inside 7d of delivery"
    # price adjustment is measured from ORDER date, and needs an actual price drop:
    o12 = date.fromisoformat(one("SELECT order_date FROM orders WHERE order_id='O1012'")[0])
    assert (ref - o12).days <= config.PRICE_ADJUST_WINDOW_DAYS, "S-V4-07 inside 7-day window"
    paid = one("SELECT unit_price FROM order_items WHERE order_id='O1012' AND product_id='P004'")[0]
    now_price = one("SELECT price FROM products WHERE product_id='P004'")[0]
    assert now_price < paid, "S-V4-07 needs current price below the paid price"

    # --- final-sale orders (V2-04/05)
    assert one("SELECT product_id FROM order_items WHERE order_id='O1009'")[0] == "P011", "S-V2-04"
    assert one("SELECT product_id FROM order_items WHERE order_id='O1010'")[0] == "P012", "S-V2-05"

    # --- lost parcel: delivered scan older than the 48h wait (V1-05)
    assert days_since_delivery("O1008") * 24 >= config.LOST_PARCEL_WAIT_HOURS, "S-V1-05"

    # --- returns (V2-08/09, G-06)
    r1 = one("SELECT status, initiated_date FROM returns WHERE return_id='R2001'")
    assert r1[0] == "label_sent" and r1[1] == "2026-06-29", "S-V2-08"
    r2 = one("SELECT status, refund_amount FROM returns WHERE return_id='R2002'")
    assert r2[0] == "refunded" and abs(r2[1] - 59.00) < 0.01, "S-V2-09 / S-G-06"

    # --- promos (V4-02/03/04)
    s = one("SELECT valid_from, valid_to, min_order, active FROM promos WHERE code='SUMMER20'")
    assert s[0] <= ref.isoformat() <= s[1] and s[2] == 75.00 and s[3] == 1, "S-V4-02"
    f = one("SELECT valid_to, active FROM promos WHERE code='FLASH15'")
    assert f[0] < ref.isoformat() and f[1] == 1, "S-V4-03 expired-by-date"
    v = one("SELECT min_order FROM promos WHERE code='VIP25'")
    assert v[0] == 150.00, "S-V4-04"
    w = one("SELECT valid_from, valid_to FROM promos WHERE code='WELCOME10'")
    assert w[0] <= ref.isoformat() <= w[1], "S-V4-03 fallback code active"

    # --- tickets table exists and is empty at seed time
    assert q("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0

    # --- exchange scenarios (V2-06/07): duplicate-size SKUs exist
    assert one("SELECT name FROM products WHERE product_id='P005'")[0] == \
           one("SELECT name FROM products WHERE product_id='P004'")[0], "S-V2-06 same style, size L"
    assert one("SELECT name FROM products WHERE product_id='P008'")[0] == \
           one("SELECT name FROM products WHERE product_id='P007'")[0], "S-V2-07 same style, size S"


def main() -> None:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    try:
        seed(conn)
        verify(conn)
        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("customers", "products", "orders", "order_items", "returns", "promos", "tickets")
        }
        print(f"Seeded {config.DB_PATH}")
        print("  " + ", ".join(f"{t}={n}" for t, n in counts.items()))
        print("All Checklist.md data-dependency assertions PASSED.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
