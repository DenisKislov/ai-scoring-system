"""Smoke tests for the scorer.

Runs both under ``pytest`` and standalone (``python tests/test_smoke.py``).

The fixtures are hand-written Russian vacancies/resumes that exercise the key
behaviours the defence cares about:

* a well-matching resume scores high and lists matched skills;
* an unrelated resume scores low (NOT ~100% — the "Показ 3" guard);
* ``rank_candidates`` orders the pool sensibly.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scorer import calculate_score, rank_candidates  # noqa: E402

VACANCY_PY = """
Требуется Python-разработчик в команду Data Science.
Опыт работы: Python, PostgreSQL, Docker, Linux, Git.
Обязанности: разработка и поддержка REST API на FastAPI, проектирование базы
данных (SQL), ревью кода.
Будет плюсом: машинное обучение, pandas, опыт с CI/CD.
"""

RESUME_RELEVANT = """
Python-разработчик, 5 лет опыта.
Стек: Python, PostgreSQL, Docker, Linux, Git.
Разрабатывал REST API на FastAPI, работал с базами данных SQL.
Опыт: pandas, машинное обучение, настройка CI/CD.
"""

RESUME_IRRELEVANT = """
Бухгалтер, 7 лет опыта. Ведение первичной документации, налоговый учёт,
расчёт заработной платы. Знание программы 1С и Excel.
"""

RESUME_PARTIAL = """
Frontend-разработчик: React, JavaScript, TypeScript, HTML, CSS.
Верстка интерфейсов. Опыт работы с Git, Docker.
"""


def test_relevant_scores_high_and_lists_skills():
    res = calculate_score(RESUME_RELEVANT, VACANCY_PY)
    print("RELEVANT:", res)
    assert res["score"] >= 70, f"expected high score, got {res['score']}"
    for skill in ("Python", "PostgreSQL", "Docker", "FastAPI"):
        assert skill in res["matched_skills"], f"missing matched {skill}"
    assert "Python" not in res["missing_skills"]


def test_irrelevant_scores_low():
    res = calculate_score(RESUME_IRRELEVANT, VACANCY_PY)
    print("IRRELEVANT:", res)
    assert res["score"] < 40, f"unrelated resume must not score high, got {res['score']}"
    # "Показ 3" guard: completely different texts never get ~100%.
    assert res["score"] <= 60


def test_empty_inputs_safe():
    assert calculate_score("", VACANCY_PY)["score"] == 0
    assert calculate_score(RESUME_RELEVANT, "")["score"] == 0


def test_rank_orders_pool():
    ranked = rank_candidates(VACANCY_PY, [RESUME_IRRELEVANT, RESUME_PARTIAL, RESUME_RELEVANT])
    print("RANKED:")
    for r in ranked:
        print(" ", r)
    ids = [r["candidate_id"] for r in ranked]
    assert ids[0] == 2, "relevant resume (id=2) must rank first"
    assert ids[-1] == 0, "irrelevant resume (id=0) must rank last"
    top = ranked[0]
    assert top["rank_percentile"] == 100, "top candidate is 100th percentile"


def _run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS  {name}")
    print("\nALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    _run_all()
