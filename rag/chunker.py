"""M10: section-aware chunker for the Loomora manual (PLAN.md P2.1).

Chunks on the manual's own structure - one chunk per `##` or `###` heading block,
never splitting mid-policy. Each `###` chunk carries its parent `#` section as a
context prefix and is tagged with its ANCHOR (e.g. "V2.window", "Guard.privacy") -
the same anchors Checklist.md's A-column uses, which is what lets the parity audit
verify chunk coverage mechanically.

Target 150-350 tokens/chunk (node-packet granularity); hard-fails above MAX_TOKENS.

Retrieval hints: each chunk's EMBEDDED text is prefixed with the corresponding graph
node's `router_hint` (the same authored hint Agent B's router reads — mechanism-side
parity, identical words). The STORED/injected text stays the untouched manual text, so
the corpus byte-parity guarantee is unaffected.

Run:  .venv/Scripts/python rag/chunker.py   (writes rag/chunks.jsonl, prints stats)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

CORPUS = config.ROOT / "rag" / "corpus" / "loomora_manual.md"
CHUNKS = config.ROOT / "rag" / "chunks.jsonl"
MAX_TOKENS = 600  # hard ceiling; chunks should sit in 150-350

ANCHOR_RE = re.compile(r"^### ([A-Za-z0-9.]+)")  # "### V1.status — ..." -> V1.status

# anchor -> graph node whose router_hint doubles as this chunk's retrieval hint
ANCHOR_TO_NODE = {
    "V1.status": "ord_status", "V1.delayed": "ord_delayed", "V1.cancel": "ord_cancel",
    "V1.address": "ord_address_change", "V1.lost": "ord_lost", "V1.elicit": "elicit_order",
    "V2.window": "ret_window_check", "V2.finalsale": "ret_final_sale",
    "V2.damaged": "ret_damaged", "V2.exchange": "ret_exchange", "V2.status": "ret_status",
    "V2.refund": "ret_refund_timeline", "V2.elicit": "elicit_order",
    "V3.stock": "prod_stock", "V3.restock": "prod_restock", "V3.sizing": "prod_sizing",
    "V3.care": "prod_care", "V3.clarify": "prod_clarify", "V3.bounds": "prod_reco_bounds",
    "V4.duplicate": "pay_duplicate_charge", "V4.promo": "pay_promo_check",
    "V4.failed": "pay_failed", "V4.giftcard": "pay_giftcard",
    "V4.priceadjust": "pay_price_adjust", "V4.chargeback": "pay_chargeback",
    "V5.update": "acct_update", "V5.password": "acct_password",
    "V5.complaint": "acct_complaint", "V5.feedback": "acct_feedback",
    "V5.lockout": "acct_lockout",
    "V6.request": "handoff_human", "V6.twostrikes": "handoff_human",
    "V6.legal": "guardrail_legal", "V6.exception": "ret_out_of_window",
    "Guard.injection": "guardrail_injection", "Guard.privacy": "guardrail_privacy",
    "Guard.abuse": "guardrail_abuse", "Guard.offtopic": "guardrail_offtopic",
    "Guard.promptleak": "guardrail_prompt_leak", "Guard.fraud": "guardrail_fraud",
}


def load_hints() -> dict[str, str]:
    graph = json.loads(config.GRAPH_PATH.read_text(encoding="utf-8"))
    hints_by_node = {n["id"]: n["router_hint"] for n in graph["nodes"]}
    return {anchor: hints_by_node[node] for anchor, node in ANCHOR_TO_NODE.items()}


def est_tokens(text: str) -> int:
    return int(len(text.split()) * 1.4)


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def chunk_corpus(text: str) -> list[dict]:
    chunks: list[dict] = []
    current_h1 = ""
    block_title, block_anchor, block_lines = "", "", []

    def flush() -> None:
        if not block_lines or not block_title:
            return
        body = "\n".join(block_lines).strip()
        if not body:
            return
        prefix = f"[{current_h1}]\n" if current_h1 and block_anchor.count(".") else ""
        chunks.append({
            "id": block_anchor,
            "anchor": block_anchor,
            "title": block_title,
            "text": f"{prefix}{block_title}\n{body}",
            "tokens_est": 0,  # filled below
        })

    for line in text.splitlines():
        if line.startswith("# ") and not line.startswith("## "):
            flush()
            block_title, block_anchor, block_lines = "", "", []
            current_h1 = line.lstrip("# ").strip()
            continue
        if line.startswith("### ") or line.startswith("## "):
            flush()
            title = line.lstrip("#").strip()
            m = ANCHOR_RE.match(line)
            block_anchor = m.group(1) if m else slug(title.split("—")[0].split("(")[0])
            block_title = title
            block_lines = []
            continue
        block_lines.append(line)
    flush()

    for c in chunks:
        c["tokens_est"] = est_tokens(c["text"])
    return chunks


def main() -> int:
    chunks = chunk_corpus(CORPUS.read_text(encoding="utf-8"))
    hints = load_hints()
    for c in chunks:
        hint = hints.get(c["anchor"], "")
        c["embed_text"] = (f"When: {hint}\n{c['text']}" if hint else c["text"])

    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids)), f"duplicate chunk ids: {[i for i in ids if ids.count(i) > 1]}"
    oversize = [c["id"] for c in chunks if c["tokens_est"] > MAX_TOKENS]
    assert not oversize, f"chunks over {MAX_TOKENS} tokens (split the section): {oversize}"

    CHUNKS.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in chunks), encoding="utf-8")

    sizes = sorted(c["tokens_est"] for c in chunks)
    n_hinted = sum(1 for c in chunks if c["embed_text"] != c["text"])
    print(f"{len(chunks)} chunks -> {CHUNKS.relative_to(config.ROOT)} ({n_hinted} with retrieval hints)")
    print(f"  tokens/chunk: min {sizes[0]}, median {sizes[len(sizes)//2]}, max {sizes[-1]}")
    in_band = sum(1 for s in sizes if 150 <= s <= 350)
    print(f"  in 150-350 target band: {in_band}/{len(chunks)}")
    print("  anchors:", ", ".join(c["anchor"] for c in chunks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
