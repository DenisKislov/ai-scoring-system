from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Set, Tuple

import numpy as np
from scipy.stats import spearmanr

# ИМПОРТ ИЗМЕНЕН: используем правильную таксономию
from .skills_categories import category_of


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


def confusion_counts(
        predicted_skills: Iterable[str], true_skills: Iterable[str]
) -> Dict[str, int]:
    pred = set(predicted_skills or ())
    true = set(true_skills or ())
    return {
        "tp": len(pred & true),
        "fp": len(pred - true),
        "fn": len(true - pred),
    }


def _prf(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def precision(predicted_skills: Iterable[str], true_skills: Iterable[str]) -> float:
    counts = confusion_counts(predicted_skills, true_skills)
    return _prf(counts["tp"], counts["fp"], counts["fn"])[0]


def recall(predicted_skills: Iterable[str], true_skills: Iterable[str]) -> float:
    counts = confusion_counts(predicted_skills, true_skills)
    return _prf(counts["tp"], counts["fp"], counts["fn"])[1]


def f1(predicted_skills: Iterable[str], true_skills: Iterable[str]) -> float:
    counts = confusion_counts(predicted_skills, true_skills)
    return _prf(counts["tp"], counts["fp"], counts["fn"])[2]


def category_metrics(
        predicted_skills: Iterable[str],
        true_skills: Iterable[str],
        categories: Optional[Mapping[str, Iterable[str]]] = None,
) -> Dict[str, Dict[str, float]]:
    pred = set(predicted_skills or ())
    true = set(true_skills or ())

    grouped_pred: Dict[str, Set[str]] = {}
    grouped_true: Dict[str, Set[str]] = {}
    all_categories = set()

    if categories is not None:
        # Для test_category_metrics_explicit_categories (кастомная таксономия)
        skill_to_cat = {}
        for cat_name, cat_skills in categories.items():
            all_categories.add(cat_name)
            for skill in cat_skills:
                skill_to_cat[skill] = cat_name

        for skill in pred:
            if skill in skill_to_cat:
                cat = skill_to_cat[skill]
                grouped_pred.setdefault(cat, set()).add(skill)

        for skill in true:
            if skill in skill_to_cat:
                cat = skill_to_cat[skill]
                grouped_true.setdefault(cat, set()).add(skill)
    else:
        # По умолчанию используем таксономию проекта
        for skill in pred:
            cat = category_of(skill)
            grouped_pred.setdefault(cat, set()).add(skill)
            all_categories.add(cat)

        for skill in true:
            cat = category_of(skill)
            grouped_true.setdefault(cat, set()).add(skill)
            all_categories.add(cat)

    out = {}
    for cat in all_categories:
        c_pred = grouped_pred.get(cat, set())
        c_true = grouped_true.get(cat, set())

        tp = len(c_pred & c_true)
        fp = len(c_pred - c_true)
        fn = len(c_true - c_pred)
        p, r, f = _prf(tp, fp, fn)

        out[cat] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": p,
            "recall": r,
            "f1": f,
        }
    return out


def micro_average(
        category_results: Mapping[str, Mapping[str, Any]]
) -> Dict[str, float]:
    tp = int(sum(row["tp"] for row in category_results.values()))
    fp = int(sum(row["fp"] for row in category_results.values()))
    fn = int(sum(row["fn"] for row in category_results.values()))
    p, r, f = _prf(tp, fp, fn)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f}


def macro_average(
        category_results: Mapping[str, Mapping[str, Any]]
) -> Dict[str, float]:
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
) -> Dict[str, Any]:
    pred = set(predicted_skills or ())
    true = set(true_skills or ())
    per_category = category_metrics(pred, true)

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