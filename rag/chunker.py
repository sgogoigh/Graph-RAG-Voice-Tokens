"""M10: section-aware chunker for the Loomora manual (PLAN.md P2.1).

Chunks on the manual's own structure - one chunk per `##` or `###` heading block,
never splitting mid-policy. Each `###` chunk carries its parent `#` section as a
context prefix and is tagged with its ANCHOR (e.g. "V2.window", "Guard.privacy") -
the same anchors Checklist.md's A-column uses, which is what lets the parity audit
verify chunk coverage mechanically.

Target 150-350 tokens/chunk (node-packet granularity); hard-fails above MAX_TOKENS.

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

    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids)), f"duplicate chunk ids: {[i for i in ids if ids.count(i) > 1]}"
    oversize = [c["id"] for c in chunks if c["tokens_est"] > MAX_TOKENS]
    assert not oversize, f"chunks over {MAX_TOKENS} tokens (split the section): {oversize}"

    CHUNKS.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in chunks), encoding="utf-8")

    sizes = sorted(c["tokens_est"] for c in chunks)
    print(f"{len(chunks)} chunks -> {CHUNKS.relative_to(config.ROOT)}")
    print(f"  tokens/chunk: min {sizes[0]}, median {sizes[len(sizes)//2]}, max {sizes[-1]}")
    in_band = sum(1 for s in sizes if 150 <= s <= 350)
    print(f"  in 150-350 target band: {in_band}/{len(chunks)}")
    print("  anchors:", ", ".join(c["anchor"] for c in chunks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
