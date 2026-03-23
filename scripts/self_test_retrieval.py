#!/usr/bin/env python3
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "app"))

from query_utils import apply_light_rerank
from schemas import SearchHit


def main() -> None:
    hits = [
        SearchHit(
            chunk_id=1,
            book="Spec A",
            chapter="8.1.4",
            page_start=10,
            page_end=11,
            chunk_text="Transformer capacity 500 kVA. Rated output and quantity are specified.",
            score=0.2,
        ),
        SearchHit(
            chunk_id=2,
            book="Spec B",
            chapter=None,
            page_start=1,
            page_end=1,
            chunk_text="123 456 789 100 200 300 400 500 600 700",
            score=0.6,
        ),
    ]

    base_top = max(hits, key=lambda h: float(h.score or 0.0)).chunk_id
    reranked, debug = apply_light_rerank("transformer capacity", hits, return_debug=True)
    rerank_top = reranked[0].chunk_id

    assert base_top == 2, "base ordering should favor higher score"
    assert rerank_top == 1, "rerank should boost keyword-rich chunk and penalize noise"
    assert debug, "rerank debug should not be empty"

    print("self-test ok: rerank toggling works as expected")


if __name__ == "__main__":
    main()
