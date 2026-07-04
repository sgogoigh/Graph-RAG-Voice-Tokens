"""Shared DB tools — identical for Agent A and Agent B (PLAN.md §2 D8).

Design rule: tools are DUMB data access + physically-necessary integrity checks only
(e.g. you cannot cancel a shipped order). Policy decisions — return windows, final-sale
rules, promo validity, identity verification — are deliberately LEFT TO THE AGENT,
because policy adherence is part of what the experiment measures. A tool that enforced
policy would mask agent failures and equalize the two architectures artificially.

All functions return JSON strings (what the model sees as the tool result).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import config


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _rows(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------

def get_customer(email: str) -> str:
    with _conn() as c:
        row = c.execute(
            "SELECT customer_id, name, email, phone, loyalty_tier FROM customers WHERE lower(email)=lower(?)",
            (email.strip(),),
        ).fetchone()
    return _j(dict(row)) if row else _j({"error": "no customer with that email"})


def list_orders(email: str) -> str:
    with _conn() as c:
        rows = c.execute(
            """SELECT o.order_id, o.order_date, o.status, o.expected_delivery, o.delivered_date, o.total
               FROM orders o JOIN customers cu USING (customer_id)
               WHERE lower(cu.email)=lower(?) ORDER BY o.order_date DESC""",
            (email.strip(),),
        ).fetchall()
    return _j(_rows(rows)) if rows else _j({"error": "no orders for that email"})


def get_order(order_id: str) -> str:
    with _conn() as c:
        row = c.execute(
            """SELECT o.*, cu.name AS customer_name, cu.email AS customer_email,
                      cu.phone AS customer_phone, cu.loyalty_tier
               FROM orders o JOIN customers cu USING (customer_id) WHERE o.order_id=?""",
            (order_id.strip().upper(),),
        ).fetchone()
        if not row:
            return _j({"error": "no order with that ID"})
        items = c.execute(
            """SELECT p.product_id, p.name, p.size, p.color, i.qty, i.unit_price, p.final_sale
               FROM order_items i JOIN products p USING (product_id) WHERE i.order_id=?""",
            (row["order_id"],),
        ).fetchall()
    out = dict(row)
    out["items"] = _rows(items)
    out["today"] = config.REFERENCE_DATE.isoformat()
    return _j(out)


def search_products(query: str) -> str:
    with _conn() as c:
        rows = c.execute(
            """SELECT product_id, name, category, size, color, price, stock_qty, final_sale, care_notes
               FROM products WHERE lower(name) LIKE lower(?) OR lower(color) LIKE lower(?)
               ORDER BY name, size""",
            (f"%{query.strip()}%", f"%{query.strip()}%"),
        ).fetchall()
    return _j(_rows(rows)) if rows else _j({"error": "no products match that query"})


def get_returns(order_id: str) -> str:
    with _conn() as c:
        rows = c.execute(
            """SELECT r.return_id, r.order_id, r.product_id, p.name AS product_name,
                      r.reason, r.status, r.refund_amount, r.initiated_date
               FROM returns r JOIN products p USING (product_id) WHERE r.order_id=?""",
            (order_id.strip().upper(),),
        ).fetchall()
    return _j(_rows(rows)) if rows else _j({"error": "no returns for that order"})


def check_promo(code: str) -> str:
    with _conn() as c:
        row = c.execute("SELECT * FROM promos WHERE upper(code)=upper(?)", (code.strip(),)).fetchone()
    if not row:
        return _j({"error": "no such promo code"})
    out = dict(row)
    out["today"] = config.REFERENCE_DATE.isoformat()
    return _j(out)


# ---------------------------------------------------------------------------
# Write tools (integrity checks only — policy stays with the agent)
# ---------------------------------------------------------------------------

def cancel_order(order_id: str) -> str:
    with _conn() as c:
        row = c.execute("SELECT status FROM orders WHERE order_id=?", (order_id.strip().upper(),)).fetchone()
        if not row:
            return _j({"error": "no order with that ID"})
        if row["status"] not in ("placed", "processing"):
            return _j({"error": f"cannot cancel: order status is '{row['status']}' (already left the warehouse)"})
        c.execute("UPDATE orders SET status='cancelled' WHERE order_id=?", (order_id.strip().upper(),))
    return _j({"ok": True, "order_id": order_id.strip().upper(), "new_status": "cancelled"})


def update_address(order_id: str, new_address: str) -> str:
    with _conn() as c:
        row = c.execute("SELECT status FROM orders WHERE order_id=?", (order_id.strip().upper(),)).fetchone()
        if not row:
            return _j({"error": "no order with that ID"})
        if row["status"] not in ("placed", "processing"):
            return _j({"error": f"cannot change address: order status is '{row['status']}'"})
        c.execute("UPDATE orders SET ship_address=? WHERE order_id=?", (new_address.strip(), order_id.strip().upper()))
    return _j({"ok": True, "order_id": order_id.strip().upper(), "new_address": new_address.strip()})


def initiate_return(order_id: str, product_id: str, reason: str, resolution: str,
                    exchange_product_id: str | None = None) -> str:
    if resolution not in ("refund_original", "store_credit", "exchange"):
        return _j({"error": "resolution must be refund_original, store_credit, or exchange"})
    oid, pid = order_id.strip().upper(), product_id.strip().upper()
    with _conn() as c:
        item = c.execute(
            "SELECT unit_price FROM order_items WHERE order_id=? AND product_id=?", (oid, pid)
        ).fetchone()
        if not item:
            return _j({"error": "that product is not on that order"})
        existing = c.execute(
            "SELECT return_id, status FROM returns WHERE order_id=? AND product_id=?", (oid, pid)
        ).fetchone()
        if existing:
            return _j({"error": f"a return already exists for this item: {existing['return_id']} ({existing['status']})"})
        n = c.execute("SELECT COUNT(*) FROM returns").fetchone()[0]
        rid = f"R{2001 + n}"
        note = reason.strip() + (f" | resolution={resolution}"
                                 + (f" -> {exchange_product_id.strip().upper()}" if exchange_product_id else ""))
        c.execute(
            "INSERT INTO returns VALUES (?,?,?,?,?,?,?)",
            (rid, oid, pid, note, "label_sent", None, config.REFERENCE_DATE.isoformat()),
        )
    return _j({"ok": True, "return_id": rid, "status": "label_sent", "resolution": resolution})


def create_ticket(customer_id: str, vertical: str, summary: str, priority: str = "normal") -> str:
    if priority not in ("normal", "priority"):
        priority = "normal"
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO tickets (customer_id, vertical, summary, priority, created_at) VALUES (?,?,?,?,?)",
            (customer_id.strip().upper() or None, vertical.strip(), summary.strip(), priority,
             config.REFERENCE_DATE.isoformat()),
        )
        tid = cur.lastrowid
    return _j({"ok": True, "ticket_id": tid, "priority": priority,
               "note": "human team responds 9am-6pm ET Mon-Fri; outside hours this is a callback ticket"})


# ---------------------------------------------------------------------------
# Tool schemas (Groq/OpenAI function-calling format) + dispatcher
# ---------------------------------------------------------------------------

def _schema(name: str, desc: str, params: dict[str, str], required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": {k: {"type": "string", "description": v} for k, v in params.items()},
                "required": required,
            },
        },
    }


TOOL_SCHEMAS: list[dict] = [
    _schema("get_customer", "Look up a customer record by email (for identity verification).",
            {"email": "customer email address"}, ["email"]),
    _schema("list_orders", "List all orders for a customer email (use when the customer doesn't know their order ID).",
            {"email": "customer email address"}, ["email"]),
    _schema("get_order", "Full order details incl. items, status, tracking, delivery dates, and customer info.",
            {"order_id": "order ID like O1001"}, ["order_id"]),
    _schema("search_products", "Search the catalog by product name or color substring. Returns all matching size/color SKUs with stock.",
            {"query": "name or color fragment, e.g. 'hoodie' or 'indigo'"}, ["query"]),
    _schema("get_returns", "List returns/refunds attached to an order.",
            {"order_id": "order ID like O1001"}, ["order_id"]),
    _schema("check_promo", "Fetch a promo code's discount, validity dates, minimum order, and active flag. YOU decide validity from these fields.",
            {"code": "promo code, e.g. SUMMER20"}, ["code"]),
    _schema("cancel_order", "Cancel an order. Only succeeds while status is placed/processing.",
            {"order_id": "order ID"}, ["order_id"]),
    _schema("update_address", "Change an order's shipping address. Only succeeds while status is placed/processing. Confirm the address with the customer first.",
            {"order_id": "order ID", "new_address": "full new shipping address"}, ["order_id", "new_address"]),
    _schema("initiate_return", "Create a return/exchange for one item on an order AFTER you have confirmed policy eligibility.",
            {"order_id": "order ID", "product_id": "product ID being returned",
             "reason": "customer's reason", "resolution": "refund_original | store_credit | exchange",
             "exchange_product_id": "target SKU when resolution=exchange (optional)"},
            ["order_id", "product_id", "reason", "resolution"]),
    _schema("create_ticket", "Open a human-support ticket (handoff, investigation, billing dispute, identity recovery...). Include a clear summary of the conversation so far.",
            {"customer_id": "customer ID like C001, or empty string if unverified",
             "vertical": "V1|V2|V3|V4|V5|V6", "summary": "concise handoff summary",
             "priority": "normal | priority"},
            ["customer_id", "vertical", "summary"]),
]

_DISPATCH = {
    "get_customer": get_customer,
    "list_orders": list_orders,
    "get_order": get_order,
    "search_products": search_products,
    "get_returns": get_returns,
    "check_promo": check_promo,
    "cancel_order": cancel_order,
    "update_address": update_address,
    "initiate_return": initiate_return,
    "create_ticket": create_ticket,
}


def execute_tool(name: str, arguments: str | dict) -> str:
    """Dispatch a model tool call. Never raises — errors go back to the model as JSON."""
    fn = _DISPATCH.get(name)
    if fn is None:
        return _j({"error": f"unknown tool '{name}'"})
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
        return fn(**{k: v for k, v in args.items() if v is not None})
    except TypeError as e:
        return _j({"error": f"bad arguments: {e}"})
    except Exception as e:  # noqa: BLE001 - surface to the model, don't crash the run
        return _j({"error": f"{type(e).__name__}: {e}"})
