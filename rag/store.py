"""M10: ChromaDB vector store for the chunked manual (PLAN.md P2.1).

Embedding: Chroma's built-in ONNX all-MiniLM-L6-v2 (local, CPU, deterministic) -
no torch dependency, no API cost. Retrieval cost is therefore ~0 LLM tokens; the
wall-clock of embed+search is returned per query and charged to Agent C's latency.

Build (idempotent - drops and re-adds):  .venv/Scripts/python rag/store.py
Query API:  RagStore().query("where is my order", k=3) -> list of hits + elapsed ms
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

CHUNKS = config.ROOT / "rag" / "chunks.jsonl"
CHROMA_DIR = config.ROOT / "rag" / "chroma"
COLLECTION = "loomora_manual"
DEFAULT_K = 3


@dataclass
class Hit:
    id: str
    anchor: str
    title: str
    text: str
    distance: float


class RagStore:
    def __init__(self):
        import chromadb  # deferred: heavy import

        self._client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self._col = self._client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"}
        )

    def build(self) -> int:
        chunks = [json.loads(x) for x in CHUNKS.read_text(encoding="utf-8").splitlines() if x.strip()]
        try:
            self._client.delete_collection(COLLECTION)
        except Exception:  # noqa: BLE001 - didn't exist yet
            pass
        self._col = self._client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
        self._col.add(
            ids=[c["id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[{"anchor": c["anchor"], "title": c["title"]} for c in chunks],
        )
        return len(chunks)

    def query(self, text: str, k: int = DEFAULT_K) -> tuple[list[Hit], float]:
        t0 = time.perf_counter()
        r = self._col.query(query_texts=[text], n_results=k)
        ms = (time.perf_counter() - t0) * 1000
        hits = [
            Hit(id=i, anchor=m["anchor"], title=m["title"], text=d, distance=dist)
            for i, m, d, dist in zip(r["ids"][0], r["metadatas"][0], r["documents"][0], r["distances"][0])
        ]
        return hits, ms

    def anchors(self) -> set[str]:
        got = self._col.get(include=["metadatas"])
        return {m["anchor"] for m in got["metadatas"]}


def main() -> int:
    store = RagStore()
    n = store.build()
    print(f"Built Chroma collection '{COLLECTION}' at {CHROMA_DIR.relative_to(config.ROOT)}: {n} chunks")

    for q in ["Where is my order?", "I want to return a dress I bought a month ago",
              "my promo code isn't working"]:
        hits, ms = store.query(q)
        print(f"  {q!r} -> {[h.anchor for h in hits]}  ({ms:.0f} ms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
