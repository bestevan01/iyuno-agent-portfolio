"""인덱스 빌드 CLI.

    python -m agent.build_index              # 기본(e5)
    python -m agent.build_index --embedder tfidf --out /tmp/idx
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from .config import get_settings
from .ingest import load_chunks
from .retriever import VectorIndex, make_embedder


def main() -> None:
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("--embedder", default=s.embedder, choices=["e5", "tfidf"])
    ap.add_argument("--out", type=Path, default=s.index_dir)
    a = ap.parse_args()

    t0 = time.perf_counter()
    chunks = load_chunks(s.raw_dir, s.sources_file, s.chunk_size, s.chunk_overlap)
    index = VectorIndex.build(chunks, make_embedder(a.embedder, s.e5_model))
    index.save(a.out)
    docs = len({c.doc_id for c in chunks})
    print(f"indexed {len(chunks)} chunks from {docs} docs with {a.embedder} "
          f"in {time.perf_counter() - t0:.1f}s -> {a.out}")


if __name__ == "__main__":
    main()
