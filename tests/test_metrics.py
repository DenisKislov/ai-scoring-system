"""Unit tests for skill classification metrics (Precision / Recall / F1).

Covers both standalone execution (``python tests/test_metrics.py``) and
``pytest``. The fixtures are small sets of canonical skill names so the
expected TP/FP/FN values are exact.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scorer.metrics import (  # noqa: E402
    category_metrics,
    classification_report,
    confusion_counts,
    f1,
    macro_average,
    micro_average,
    precision,
    recall,
)
from scorer.skills_categories import (  # noqa: E402
    CATEGORY_DATABASES,
    CATEGORY_DEVOPS,
    CATEGORY_LANGUAGES,
    CATEGORY_ML,
    CATEGORY_OTHER,
    category_of,
    categorize,
)


def test_confusion_counts():
    got = confusion_counts(["Python", "Docker"], ["Python", "SQL"])
    assert got == {"tp": 1, "fp": 1, "fn": 1}


def test_precision_recall_f1_exact():
    pred = {"Python", "Docker", "React"}
    true = {"Python", "SQL", "React", "Flask"}
    assert precision(pred, true) == 2 / 3
    assert recall(pred, true) == 0.5
    expected_f1 = 2 * (2 / 3 * 0.5) / (2 / 3 + 0.5)
    assert abs(f1(pred, true) - expected_f1) < 1e-12


def test_empty_sets_safe():
    assert precision([], []) == 0.0
    assert recall([], []) == 0.0
    assert f1([], []) == 0.0
    assert precision(["Python"], []) == 0.0
    assert recall([], ["Python"]) == 0.0
    assert f1(["Python"], ["Python"]) == 1.0


def test_category_of_curated():
    assert category_of("Python") == CATEGORY_LANGUAGES
    assert category_of("PostgreSQL") == CATEGORY_DATABASES
    assert category_of("PyTorch") == CATEGORY_ML
    assert category_of("Docker") == CATEGORY_DEVOPS


def test_category_of_auto_and_unknown():
    # Авто-навыки классифицируются keyword-правилами.
    assert category_of("XGBoost") == CATEGORY_ML
    assert category_of("Vue.js") == "Frontend"
    # Неизвестный навык попадает в «Прочее».
    assert category_of("Совершенно неизвестный навык") == CATEGORY_OTHER


def test_categorize_partitions_skills():
    grouped = categorize(["Python", "Docker", "NumPy"])
    assert grouped[CATEGORY_LANGUAGES] == {"Python"}
    assert grouped[CATEGORY_DEVOPS] == {"Docker"}
    assert grouped[CATEGORY_ML] == {"NumPy"}
    # Каждый навык ровно в одной категории.
    total = sum(len(v) for v in grouped.values())
    assert total == 3


def test_category_metrics_default_taxonomy():
    pred = {"Python", "Docker", "NumPy"}
    true = {"Python", "PostgreSQL", "PyTorch"}
    per = category_metrics(pred, true)

    lang = per[CATEGORY_LANGUAGES]
    assert (lang["tp"], lang["fp"], lang["fn"]) == (1, 0, 0)

    db = per[CATEGORY_DATABASES]
    assert (db["tp"], db["fp"], db["fn"]) == (0, 0, 1)

    ml = per[CATEGORY_ML]
    assert (ml["tp"], ml["fp"], ml["fn"]) == (0, 1, 1)

    devops = per[CATEGORY_DEVOPS]
    assert (devops["tp"], devops["fp"], devops["fn"]) == (0, 1, 0)

    # Пустые категории по умолчанию не попадают в отчёт.
    assert "BI / Аналитика" not in per


def test_category_metrics_explicit_categories():
    cats = {
        "lvl1": {"Python", "Java"},
        "lvl2": {"Docker", "Linux"},
    }
    pred = {"Python", "Docker", "Git"}
    true = {"Python", "Java", "Linux"}
    per = category_metrics(pred, true, categories=cats)

    assert (per["lvl1"]["tp"], per["lvl1"]["fp"], per["lvl1"]["fn"]) == (1, 0, 1)
    assert (per["lvl2"]["tp"], per["lvl2"]["fp"], per["lvl2"]["fn"]) == (0, 1, 1)
    # «Git» не входит в явные категории и потому не учитывается.
    assert per["lvl1"]["precision"] == 1.0


def test_classification_report_micro_equals_overall():
    pred = {"Python", "Docker", "NumPy", "React"}
    true = {"Python", "PostgreSQL", "PyTorch", "React"}
    report = classification_report(pred, true)
    overall = report["overall"]
    micro = report["micro"]
    for key in ("precision", "recall", "f1"):
        assert abs(overall[key] - micro[key]) < 1e-12


def test_micro_average_sums_counts():
    per = {
        "a": {"tp": 1, "fp": 1, "fn": 0, "precision": 0.5, "recall": 1.0, "f1": 2 / 3},
        "b": {"tp": 1, "fp": 0, "fn": 1, "precision": 1.0, "recall": 0.5, "f1": 2 / 3},
    }
    micro = micro_average(per)
    assert (micro["tp"], micro["fp"], micro["fn"]) == (2, 1, 1)
    assert abs(micro["precision"] - 2 / 3) < 1e-12
    assert abs(micro["recall"] - 2 / 3) < 1e-12


def test_macro_average_skips_empty_categories():
    per = {
        "a": {"tp": 1, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0},
        "b": {"tp": 0, "fp": 1, "fn": 1, "precision": 0.0, "recall": 0.0, "f1": 0.0},
        "empty": {"tp": 0, "fp": 0, "fn": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0},
    }
    macro = macro_average(per)
    assert abs(macro["precision"] - 0.5) < 1e-12
    assert abs(macro["recall"] - 0.5) < 1e-12
    assert abs(macro["f1"] - 0.5) < 1e-12


def _run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS  {name}")
    print("\nALL METRIC TESTS PASSED")


if __name__ == "__main__":
    _run_all()
