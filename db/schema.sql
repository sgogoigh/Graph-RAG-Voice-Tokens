-- Loomora records database (PLAN.md §5)
-- Note: `delivered_date` was added beyond the original plan sketch because every
-- return-window calculation anchors to DELIVERY date, not order date.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    customer_id   TEXT PRIMARY KEY,          -- C001...
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    phone         TEXT NOT NULL,
    loyalty_tier  TEXT NOT NULL CHECK (loyalty_tier IN ('Basic', 'Silver', 'Gold')),
    created_at    TEXT NOT NULL              -- ISO date
);

CREATE TABLE IF NOT EXISTS products (
    product_id  TEXT PRIMARY KEY,            -- P001...
    name        TEXT NOT NULL,
    category    TEXT NOT NULL CHECK (category IN ('tops', 'bottoms', 'outerwear', 'dresses', 'accessories')),
    size        TEXT NOT NULL,               -- S/M/L, waist size, or 'One Size'
    color       TEXT NOT NULL,
    price       REAL NOT NULL,
    stock_qty   INTEGER NOT NULL,
    final_sale  INTEGER NOT NULL DEFAULT 0,  -- boolean
    care_notes  TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    order_id          TEXT PRIMARY KEY,      -- O1001...
    customer_id       TEXT NOT NULL REFERENCES customers(customer_id),
    order_date        TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN
                        ('placed', 'processing', 'shipped', 'delivered', 'delayed', 'lost', 'cancelled')),
    carrier           TEXT,                  -- NULL until shipped
    tracking_no       TEXT,
    ship_address      TEXT NOT NULL,
    expected_delivery TEXT,
    delivered_date    TEXT,                  -- NULL unless delivered
    total             REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id    TEXT NOT NULL REFERENCES orders(order_id),
    product_id  TEXT NOT NULL REFERENCES products(product_id),
    qty         INTEGER NOT NULL,
    unit_price  REAL NOT NULL,
    PRIMARY KEY (order_id, product_id)
);

CREATE TABLE IF NOT EXISTS returns (
    return_id      TEXT PRIMARY KEY,         -- R2001...
    order_id       TEXT NOT NULL REFERENCES orders(order_id),
    product_id     TEXT NOT NULL REFERENCES products(product_id),
    reason         TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN
                     ('requested', 'label_sent', 'received', 'refunded', 'rejected')),
    refund_amount  REAL,                     -- NULL until refunded
    initiated_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS promos (
    code          TEXT PRIMARY KEY,
    discount_pct  INTEGER NOT NULL,
    valid_from    TEXT NOT NULL,
    valid_to      TEXT NOT NULL,
    min_order     REAL NOT NULL DEFAULT 0,
    active        INTEGER NOT NULL DEFAULT 1 -- boolean; expiry is enforced by dates too
);

-- Human-handoff queue; empty at seed time, written by agents at runtime.
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT REFERENCES customers(customer_id),
    vertical    TEXT NOT NULL,
    summary     TEXT NOT NULL,
    priority    TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('normal', 'priority')),
    created_at  TEXT NOT NULL
);
