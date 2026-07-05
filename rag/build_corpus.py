"""M10: derive Agent C's source document from Agent A's manual (PLAN.md P2.1).

Parity by construction: the corpus is agent_a_system.md VERBATIM except the opening
"You are Lume..." agent-framing paragraph, which becomes a document header. This script
ASSERTS that the remainder is byte-identical, so content parity with A (and hence B,
already audited) can never silently drift.

Run:  .venv/Scripts/python rag/build_corpus.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

SOURCE = config.PROMPTS_DIR / "agent_a_system.md"
CORPUS = config.ROOT / "rag" / "corpus" / "loomora_manual.md"

DOC_HEADER = (
    "This document is the complete and only source of Loomora policy: an online-only "
    "clothing brand's customer-support operations manual covering orders & shipping, "
    "returns & exchanges, products & sizing, payments & promos, account matters, human "
    "handoff, and hard guardrails."
)


def split_intro(text: str) -> tuple[str, str, str]:
    """Return (title_line, intro_paragraph, remainder). Paragraphs are blank-line delimited."""
    lines = text.splitlines(keepends=True)
    assert lines[0].startswith("# "), "manual must start with an h1 title"
    title = lines[0]
    # find the intro paragraph: first non-blank block after the title
    i = 1
    while lines[i].strip() == "":
        i += 1
    j = i
    while j < len(lines) and lines[j].strip() != "":
        j += 1
    return title, "".join(lines[i:j]), "".join(lines[j:])


def main() -> int:
    source_text = SOURCE.read_text(encoding="utf-8")
    title, intro, remainder = split_intro(source_text)

    assert intro.startswith("You are **Lume**"), (
        "agent_a_system.md's intro paragraph changed shape - re-verify the derivation "
        f"(got: {intro[:60]!r})"
    )

    corpus_text = title + "\n" + DOC_HEADER + "\n" + remainder
    CORPUS.parent.mkdir(parents=True, exist_ok=True)
    CORPUS.write_text(corpus_text, encoding="utf-8")

    # the parity assertion: corpus tail == source tail, byte for byte
    _, c_intro, c_remainder = split_intro(corpus_text)
    assert c_remainder == remainder, "corpus remainder diverged from the source manual"
    assert c_intro == DOC_HEADER + "\n", "corpus intro is not exactly the document header"

    n_lines = corpus_text.count("\n")
    print(f"Derived {CORPUS.relative_to(config.ROOT)} from {SOURCE.name}")
    print(f"  diff = intro paragraph only ({len(intro.split())} words -> {len(DOC_HEADER.split())} words)")
    print(f"  remainder: {len(remainder.split())} words across {n_lines} lines - byte-identical (asserted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
