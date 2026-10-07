"""Assert the ranking quality criterion on the seeded synthetic benchmark.

The calculation lives in ``scripts.benchmark_synthetic`` so the regression
check and the user-facing report use the same labels and metric definitions.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.benchmark_synthetic import evaluate as run_benchmark, markdown  # noqa: E402

QUALITY_BAR = 0.80


def evaluate() -> float:
    report = run_benchmark()
    print(markdown(report))
    score = report["mean"]["ndcg_at_k"]
    assert score >= QUALITY_BAR, f"NDCG@10 {score:.3f} below {QUALITY_BAR:.2f}"
    return score


if __name__ == "__main__":
    evaluate()
