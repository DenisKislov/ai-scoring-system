from typing import Optional, Sequence

import numpy as np
from scipy.stats import spearmanr


def _discounts(n: int) -> np.ndarray:
    return 1.0 / np.log2(np.arange(2, n + 2))


def ndcg(predicted_relevances: Sequence[float], k: Optional[int] = None) -> float:
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
    top = list(predicted_relevances)[:k]
    if not top:
        return 0.0
    return float(np.mean([r >= threshold for r in top]))


def spearman(predicted_scores: Sequence[float], true_relevances: Sequence[float]) -> float:
    if len(predicted_scores) < 2:
        return 0.0
    rho, _ = spearmanr(predicted_scores, true_relevances)
    return float(rho) if rho == rho else 0.0