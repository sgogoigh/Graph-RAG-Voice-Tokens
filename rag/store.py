"""M10/M11: hybrid retrieval store for the chunked manual (PLAN.md P2.1-P2.2).

Two signals, fused with Reciprocal Rank Fusion (RRF, K=60 - the standard constant):
  - vector: Chroma + ONNX all-MiniLM-L6-v2 (local, CPU, deterministic)
  - lexical: hand-rolled BM25 over the same hint-enriched chunk texts
Hybrid vector+lexical is canonical production RAG; it also makes Agent C a STRONGER
baseline, which makes any Agent B advantage more credible. Retrieval costs ~0 LLM
tokens; the embed+search wall-clock is returned per query and charged to C's latency.

Build (idempotent - drops and re-adds):  .venv/Scripts/python rag/store.py
Query API:  RagStore().query_fused(user_msg, last_agent_msg, k=3) -> hits + elapsed ms
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

CHUNKS = config.ROOT / "rag" / "chunks.jsonl"
CHROMA_DIR = config.ROOT / "rag" / "chroma"
COLLECTION = "loomora_manual"
DEFAULT_K = 3
BM25_WEIGHT = 0.5  # RRF weight for the lexical lists (vector lists weigh 1.0)


@dataclass
class Hit:
    id: str
    anchor: str
    title: str
    text: str
    distance: float


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


class _BM25:
    """Minimal BM25 (k1=1.5, b=0.75) over the hint-enriched chunk texts."""

    def __init__(self, docs: dict[str, str]):
        self.ids = list(docs)
        self.toks = {i: _tokens(t) for i, t in docs.items()}
        self.avg_len = sum(len(t) for t in self.toks.values()) / max(1, len(self.toks))
        n = len(self.ids)
        df = Counter(tok for toks in self.toks.values() for tok in set(toks))
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def rank(self, query: str) -> list[str]:
        q = _tokens(query)
        scores: dict[str, float] = {}
        for cid in self.ids:
            tf = Counter(self.toks[cid])
            dl = len(self.toks[cid])
            s = 0.0
            for t in q:
                if t not in tf:
                    continue
                f = tf[t]
                s += self.idf.get(t, 0.0) * (f * 2.5) / (f + 1.5 * (0.25 + 0.75 * dl / self.avg_len))
            if s > 0:
                scores[cid] = s
        return [cid for cid, _ in sorted(scores.items(), key=lambda kv: -kv[1])]


class RagStore:
    def __init__(self):
        import chromadb  # deferred: heavy import
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        self._ef = DefaultEmbeddingFunction()  # ONNX all-MiniLM-L6-v2, local
        self._client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self._col = self._client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"}, embedding_function=self._ef
        )

    def build(self) -> int:
        chunks = [json.loads(x) for x in CHUNKS.read_text(encoding="utf-8").splitlines() if x.strip()]
        try:
            self._client.delete_collection(COLLECTION)
        except Exception:  # noqa: BLE001 - didn't exist yet
            pass
        self._col = self._client.create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"}, embedding_function=self._ef
        )
        # Embed the hint-enriched text; STORE the untouched manual text (parity: the
        # injected content is byte-identical to the corpus, hints only steer search).
        self._col.add(
            ids=[c["id"] for c in chunks],
            embeddings=self._ef([c.get("embed_text", c["text"]) for c in chunks]),
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

    def _bm25(self) -> _BM25:
        if not hasattr(self, "_bm25_index"):
            chunks = [json.loads(x) for x in CHUNKS.read_text(encoding="utf-8").splitlines() if x.strip()]
            self._bm25_index = _BM25({c["id"]: c.get("embed_text", c["text"]) for c in chunks})
            self._by_id = {c["id"]: c for c in chunks}
        return self._bm25_index

    def query_fused(self, user_msg: str, last_agent_msg: str | None, k: int = DEFAULT_K
                    ) -> tuple[list[Hit], float]:
        """Agent C's retrieval: hybrid RRF over four rank lists —
        vector(user-only), vector(context+user), BM25(user-only), BM25(context+user).
        User-only queries keep topic pivots from drowning in conversation context;
        context queries keep terse continuations ('store credit please') grounded;
        BM25 rescues exact-phrase matches embeddings miss ('ignore your instructions')."""
        t0 = time.perf_counter()
        bm25 = self._bm25()
        queries = [f"Customer: {user_msg}"]
        if last_agent_msg:
            queries.append(f"Agent: {last_agent_msg[-300:]}\nCustomer: {user_msg}")

        # (rank_list, weight): vector is the primary signal, BM25 a phrase-match booster
        rank_lists: list[tuple[list[str], float]] = []
        hits_by_id: dict[str, Hit] = {}
        for q in queries:
            vhits, _ = self.query(q, k=max(k, 5))
            rank_lists.append(([h.id for h in vhits], 1.0))
            hits_by_id.update({h.id: h for h in vhits})
            rank_lists.append((bm25.rank(q)[: max(k, 5)], BM25_WEIGHT))

        K = 60  # standard RRF constant
        scores: dict[str, float] = {}
        for lst, w in rank_lists:
            for rank, cid in enumerate(lst):
                scores[cid] = scores.get(cid, 0.0) + w / (K + rank)

        top = sorted(scores, key=lambda c: -scores[c])[:k]
        fused = []
        for cid in top:
            if cid in hits_by_id:
                fused.append(hits_by_id[cid])
            else:  # BM25-only hit: materialize from chunks.jsonl
                c = self._by_id[cid]
                fused.append(Hit(id=cid, anchor=c["anchor"], title=c["title"],
                                 text=c["text"], distance=1.0))
        return fused, (time.perf_counter() - t0) * 1000

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
