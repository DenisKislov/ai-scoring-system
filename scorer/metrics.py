"""Метрики качества скорера на размеченных данных.

Две группы функций:

* **Ранжирование** — ``ndcg``, ``precision_at_k``, ``spearman``. Принимают
  релевантности, упорядоченные предсказанием (или пары «предсказание —
  истина»), и оценивают, насколько правильно скорер упорядочил кандидатов.
* **Классификация навыков** — ``precision``, ``recall``, ``f1``,
  ``category_metrics`` и ``classification_report``. Сравнивают множества
  канонических навыков (предсказанные vs истинные) и считают
  Precision/Recall/F1 как целиком, так и **по категориям** (таксономия в
  ``skills_categories.py``).

Соглашения для классификационных метрик:

* метрики принимают множества/итераторы канонических имён навыков;
* при пустом знаменателе Precision/Recall/F1 равны ``0.0`` (безопасно для
  оценочных скриптов);
* по умолчанию категории берутся из ``skills_categories.categorize`` —
  каждый навык попадает ровно в одну категорию, поэтому ``micro``-агрегат
  совпадает с ``overall``.
"""
from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional, Sequence, Set, Tuple

import numpy as np
from scipy.stats import spearmanr

from .skills_categories import categorize


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


# ---------------------------------------------------------------------------
# Классификационные метрики по навыкам (Precision / Recall / F1).
#
# Оперируют множествами канонических навыков:
#   tp = |predicted ∩ true|  fp = |predicted \ true|  fn = |true \ predicted|
# ---------------------------------------------------------------------------


def confusion_counts(
    predicted_skills: Iterable[str], true_skills: Iterable[str]
) -> Dict[str, int]:
    """Считает TP/FP/FN для пары «предсказанные навыки vs истинные навыки»."""
    pred = set(predicted_skills or ())
    true = set(true_skills or ())
    return {
        "tp": len(pred & true),
        "fp": len(pred - true),
        "fn": len(true - pred),
    }


def _prf(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    """Precision / Recall / F1 по счётчикам TP/FP/FN (0.0 при нулевом знаменателе)."""
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def precision(predicted_skills: Iterable[str], true_skills: Iterable[str]) -> float:
    """Precision извлечения навыков: доля предсказанных навыков, которые истинны."""
    counts = confusion_counts(predicted_skills, true_skills)
    return _prf(counts["tp"], counts["fp"], counts["fn"])[0]


def recall(predicted_skills: Iterable[str], true_skills: Iterable[str]) -> float:
    """Recall извлечения навыков: доля истинных навыков, которые предсказаны."""
    counts = confusion_counts(predicted_skills, true_skills)
    return _prf(counts["tp"], counts["fp"], counts["fn"])[1]


def f1(predicted_skills: Iterable[str], true_skills: Iterable[str]) -> float:
    """F1-мера извлечения навыков (гармоническое среднее Precision и Recall)."""
    counts = confusion_counts(predicted_skills, true_skills)
    return _prf(counts["tp"], counts["fp"], counts["fn"])[2]


def category_metrics(
    predicted_skills: Iterable[str],
    true_skills: Iterable[str],
    categories: Optional[Mapping[str, Iterable[str]]] = None,
) -> Dict[str, Dict[str, float]]:
    """Precision / Recall / F1 **по категориям навыков**.

    * ``predicted_skills`` / ``true_skills`` — множества канонических навыков.
    * ``categories`` — опциональное отображение ``{категория: навыки}``. Если
      не передано, категории строятся из ``skills_categories.categorize`` по
      объединению предсказанных и истинных навыков (пустые категории
      отбрасываются).

    Возвращает ``{категория: {"tp", "fp", "fn", "precision", "recall", "f1"}}``.
    """
    pred = set(predicted_skills or ())
    true = set(true_skills or ())

    if categories is None:
        grouped: Mapping[str, Set[str]] = {
            name: skills
            for name, skills in categorize(pred | true).items()
            if skills
        }
    else:
        grouped = {name: set(skills) for name, skills in categories.items()}

    out: Dict[str, Dict[str, float]] = {}
    for name, skills in grouped.items():
        tp = len(skills & pred & true)
        fp = len((skills & pred) - true)
        fn = len((skills & true) - pred)
        p, r, f = _prf(tp, fp, fn)
        out[name] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": p,
            "recall": r,
            "f1": f,
        }
    return out


def micro_average(
    category_results: Mapping[str, Mapping[str, float]]
) -> Dict[str, float]:
    """Micro-агрегат по категориям: суммирует TP/FP/FN, затем считает P/R/F1."""
    tp = int(sum(row["tp"] for row in category_results.values()))
    fp = int(sum(row["fp"] for row in category_results.values()))
    fn = int(sum(row["fn"] for row in category_results.values()))
    p, r, f = _prf(tp, fp, fn)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f}


def macro_average(
    category_results: Mapping[str, Mapping[str, float]]
) -> Dict[str, float]:
    """Macro-агрегат: среднее P/R/F1 по категориям с ненулевой поддержкой."""
    rows = [
        row
        for row in category_results.values()
        if row["tp"] + row["fp"] + row["fn"] > 0
    ]
    if not rows:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    n = len(rows)
    return {
        "precision": sum(r["precision"] for r in rows) / n,
        "recall": sum(r["recall"] for r in rows) / n,
        "f1": sum(r["f1"] for r in rows) / n,
    }


def classification_report(
    predicted_skills: Iterable[str],
    true_skills: Iterable[str],
    categories: Optional[Mapping[str, Iterable[str]]] = None,
) -> Dict:
    """Сводный отчёт по извлечению навыков.

    Возвращает словарь с ключами ``overall`` (P/R/F1 + TP/FP/FN по всему
    множеству), ``per_category`` (``category_metrics``), ``micro`` и ``macro``
    (агрегаты по категориям). При дефолтной таксономии ``micro`` совпадает с
    ``overall``, так как каждый навык попадает ровно в одну категорию.
    """
    pred = set(predicted_skills or ())
    true = set(true_skills or ())
    per_category = category_metrics(pred, true, categories=categories)

    tp = len(pred & true)
    fp = len(pred - true)
    fn = len(true - pred)
    p, r, f = _prf(tp, fp, fn)

    return {
        "overall": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": p,
            "recall": r,
            "f1": f,
        },
        "per_category": per_category,
        "micro": micro_average(per_category),
        "macro": macro_average(per_category),
    }
