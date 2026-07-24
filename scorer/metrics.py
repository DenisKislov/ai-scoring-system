"""Ranking-quality metrics used to evaluate the scorer on labelled data.

All functions take **relevance ordered by the prediction**, so the caller
decides the ordering (typically the scorer's output order). Relevance values
are graded (continuous ``[0, 1]``), so we use linear-gain DCG — the standard
choice when ground truth is a real-valued score rather than binary.

* ``ndcg`` — normalized DCG, the headline metric for Показ 3.
* ``precision_at_k`` — share of relevant items (``rel >= threshold``) in top-k.
* ``spearman`` — rank correlation between predicted scores and true relevance.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

import numpy as np
from scipy.stats import spearmanr


def _discounts(n: int) -> np.ndarray:
    """1 / log2(position + 1), with position starting at 1."""
    return 1.0 / np.log2(np.arange(2, n + 2))


def ndcg(predicted_relevances: Sequence[float], k: Optional[int] = None) -> float:
    """nDCG with linear graded gains.

    ``predicted_relevances`` lists the true relevance of each item **in the
    predicted order**. ``k`` truncates to the top-k (nDCG@k).
    """
    rel = np.asarray(predicted_relevances, dtype=float)
    if rel.size == 0:
        return 0.0
    if k is not None:
        rel = rel[:k]

    dcg = float(np.sum(rel * _discounts(rel.size)))

    ideal = np.sort(np.asarray(predicted_relevances, dtype=float))[::-1]
    if k is not None:
        ideal = ideal[:k]
    idcg = float(np.sum(ideal * _discounts(ideal.size)))

    return dcg / idcg if idcg > 0 else 0.0


def precision_at_k(
    predicted_relevances: Sequence[float], k: int, threshold: float = 0.5
) -> float:
    """Share of top-k items whose true relevance is ``>= threshold``."""
    top = list(predicted_relevances)[:k]
    if not top:
        return 0.0
    return float(np.mean([r >= threshold for r in top]))


def spearman(predicted_scores: Sequence[float], true_relevances: Sequence[float]) -> float:
    """Spearman rank correlation between predicted scores and true relevance.

    Must be called with both arrays in the **same item order** (not sorted).
    """
    if len(predicted_scores) < 2:
        return 0.0
    rho, _ = spearmanr(predicted_scores, true_relevances)
    return float(rho) if rho == rho else 0.0  # guard NaN
