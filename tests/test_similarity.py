"""Косинусная близость TF-IDF над фиксированным референс-корпусом.

Проверяем свойства близости и стабильность итогового Score при изменении
пула. Одиночный и пакетный API должны использовать одинаковые веса IDF.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scorer.similarity import batch_cosine, pair_cosine  # noqa: E402
from scorer import rank_candidates  # noqa: E402


A = "python разработка docker postgresql"
B = "python разработка docker postgresql sql"
C = "бухгалтерия налоговый учёт зарплата"


def test_identical_texts_score_one():
    assert abs(pair_cosine(A, A) - 1.0) < 1e-9


def test_disjoint_texts_score_zero():
    assert pair_cosine(A, C) == 0.0


def test_partial_overlap_in_unit_interval():
    s = pair_cosine(A, B)
    assert 0.0 < s < 1.0


def test_symmetry():
    assert abs(pair_cosine(A, B) - pair_cosine(B, A)) < 1e-9


def test_empty_inputs():
    assert pair_cosine("", A) == 0.0
    assert pair_cosine(A, "") == 0.0


def test_batch_consistent_with_pair():
    scores = batch_cosine(A, [A, B, C])
    assert len(scores) == 3
    assert scores[0] >= scores[1] > scores[2]
    assert scores[2] == 0.0
    assert scores == pytest.approx([pair_cosine(A, doc) for doc in [A, B, C]])


def test_batch_empty_docs():
    assert batch_cosine(A, []) == []


def test_batch_orders_by_relevance():
    scores = batch_cosine(A, [C, A, B])
    assert scores[1] >= scores[2] >= scores[0]


def test_similarity_is_independent_of_pool_size_and_content():
    query = "python sql разработка"
    candidate = "python docker"
    pool10 = [candidate] + ["docker sql"] * 9
    pool200 = pool10 + ["python разработка"] * 190

    expected = pair_cosine(query, candidate)
    assert batch_cosine(query, pool10)[0] == pytest.approx(expected, abs=1e-12)
    assert batch_cosine(query, pool200)[0] == pytest.approx(expected, abs=1e-12)


def test_candidate_score_is_identical_in_pools_of_10_and_200():
    vacancy = "Требуется Python, SQL, Docker для разработки сервисов."
    candidate = "Python и Docker, разработка сервисов."
    pool10 = [candidate] + ["SQL Docker"] * 9
    pool200 = pool10 + ["Python разработка"] * 190

    def first_candidate(pool):
        results = rank_candidates(
            vacancy,
            pool,
            vacancy_skills={"Python", "SQL", "Docker"},
            resume_skills_list=[{"Python", "Docker"}] * len(pool),
        )
        return next(result for result in results if result["candidate_id"] == 0)

    small = first_candidate(pool10)
    large = first_candidate(pool200)
    assert small["score"] == large["score"]
    assert small["raw_score"] == large["raw_score"]
    assert small["cosine_sim"] == large["cosine_sim"]


def test_scores_are_bounded_with_repeated_tokens_and_empty_documents():
    docs = [A, B, C, "", "python " * 100, "docker sql " * 50]
    scores = batch_cosine(A, docs)
    assert all(0.0 <= score <= 1.0 for score in scores)
    assert scores[3] == 0.0


def test_unknown_terms_have_zero_vectors():
    unknown = "unknown_unique_token_563"
    assert pair_cosine(unknown, unknown) == 0.0
    assert batch_cosine(A, [unknown]) == [0.0]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS  {name}")
    print("\nALL SIMILARITY TESTS PASSED")
