from __future__ import annotations

import pytest
from collections import defaultdict
from importlib import import_module

from api.nlp_parser import extract_smart_skills
from data.synthetic import ADJACENT_ROLES, generate_dataset
from scripts.benchmark_synthetic import ranking_metrics


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(n_vacancies=6, n_resumes=20, seed=42)


def test_profiles_are_varied_and_reproducible(dataset):
    assert dataset == generate_dataset(n_vacancies=6, n_resumes=20, seed=42)
    assert len({entry["vacancy"]["role"] for entry in dataset}) >= 5
    assert len({candidate["text"] for entry in dataset
                for candidate in entry["candidates"]}) == 120
    for entry in dataset:
        vacancy = entry["vacancy"]
        required = set(vacancy["skills"])
        assert 6 <= len(required) <= 9
        assert set(vacancy["critical_skills"]) <= required
        assert not required & set(vacancy["optional_skills"])
        assert 0 < sum(candidate["true_relevance"] >= 0.65
                       for candidate in entry["candidates"]) < 20


def test_relevance_is_based_on_hidden_profile(dataset):
    hidden_skills_exist = False
    course_only_mentions_exist = False
    for entry in dataset:
        vacancy = entry["vacancy"]
        required = set(vacancy["skills"])
        critical = set(vacancy["critical_skills"])
        for candidate in entry["candidates"]:
            latent = set(candidate["skills"])
            course_only = set(candidate["familiar_only_skills"])
            mentioned = set(candidate["text_skills"])
            assert course_only <= mentioned
            assert not course_only & latent
            assert mentioned - course_only <= latent
            hidden_skills_exist |= bool(latent - mentioned)
            course_only_mentions_exist |= bool(course_only)

            role_fit = (1.0 if candidate["role"] == vacancy["role"] else
                        0.6 if candidate["role"] in ADJACENT_ROLES[vacancy["role"]]
                        else 0.2)
            expected = round(
                0.55 * len(latent & required) / len(required)
                + 0.20 * len(latent & critical) / len(critical)
                + 0.15 * role_fit
                + 0.10 * min(candidate["experience_years"] /
                             vacancy["required_years"], 1.0),
                3,
            )
            assert candidate["true_relevance"] == expected
    assert hidden_skills_exist
    assert course_only_mentions_exist


def test_binary_ranking_metric_definitions():
    ranked = [
        {"candidate_id": 2, "score": 90},
        {"candidate_id": 0, "score": 80},
        {"candidate_id": 3, "score": 70},
        {"candidate_id": 1, "score": 60},
    ]
    result = ranking_metrics(ranked, [1.0, 0.8, 0.0, 0.9], k=2, threshold=0.65)
    assert result["precision_at_k"] == 0.5
    assert result["recall_at_k"] == pytest.approx(1 / 3)
    assert result["average_precision"] == pytest.approx((1 / 2 + 2 / 3 + 3 / 4) / 3)
    assert result["reciprocal_rank"] == 0.5
    assert 0 < result["ndcg_at_k"] < 1


def test_db_seed_does_not_expose_hidden_skills(monkeypatch, dataset):
    seed_module = import_module("db.seed")

    class FakeCollection(list):
        def insert_one(self, document):
            self.append(document)

    collections = defaultdict(FakeCollection)
    monkeypatch.setattr(seed_module.mongo, "get_db", lambda: collections)
    monkeypatch.setattr(seed_module, "generate_dataset", lambda *args: dataset[:1])
    seed_module.seed(n_vacancies=1, n_resumes=20, seed=42)

    stored = collections[seed_module.mongo.COLL_RESUMES]
    assert len(stored) == 20
    assert all(item["skills"] == extract_smart_skills(candidate["text"])
               for item, candidate in zip(stored, dataset[0]["candidates"]))
    assert any(set(item["skills"]) != set(candidate["skills"])
               for item, candidate in zip(stored, dataset[0]["candidates"]))
