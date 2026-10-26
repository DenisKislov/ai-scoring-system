"""Ensure the text benchmark caches predictions without borrowing truth labels."""
from collections import Counter

import pytest

from scripts import benchmark_real_data as benchmark


@pytest.mark.parametrize("mode", ["extracted", "annotated"])
def test_json_benchmark_extracts_once_and_keeps_oracle_inputs_separate(monkeypatch, mode):
    vacancies = [
        {"vacancy": "Vacancy A", "raw_text": "Required Python", "expected_skills": ["TruthA"]},
        {"vacancy": "Vacancy B", "raw_text": "Required SQL", "expected_skills": ["TruthB"]},
    ]
    resumes = [
        {"raw_text": "Used Docker", "expected_skills": ["TruthA"]},
        {"raw_text": "Used Excel", "expected_skills": ["TruthB"]},
    ]
    predicted = {"Required Python": {"Python"}, "Required SQL": {"SQL"},
                 "Used Docker": {"Docker"}, "Used Excel": {"Excel"}}
    extraction_calls = Counter()
    ranking_calls = []

    def extract(text):
        extraction_calls[text] += 1
        return predicted[text].copy()

    def rank(vacancy_text, resume_texts, **kwargs):
        assert resume_texts == ["Used Docker", "Used Excel"]
        ranking_calls.append({"vacancy": set(kwargs["vacancy_skills"]),
                              "resumes": [set(skills) for skills in kwargs["resume_skills_list"]]})
        return [{"candidate_id": 0, "score": 80, "keyword_score": .8},
                {"candidate_id": 1, "score": 20, "keyword_score": .2}]

    monkeypatch.setattr(benchmark, "extract_skills", extract)
    monkeypatch.setattr(benchmark, "rank_candidates", rank)
    monkeypatch.setattr(benchmark, "normalize_skill_set", set)
    monkeypatch.setattr("db.builders.experience_years", lambda item: None)

    report = benchmark.evaluate(vacancies, resumes, ranking_inputs=mode)

    # Covers ranking across two queries AND the extraction report: four calls,
    # one for each original document, independent of the selected ranking mode.
    assert extraction_calls == Counter({text: 1 for text in predicted})
    if mode == "extracted":
        assert [call["vacancy"] for call in ranking_calls] == [{"Python"}, {"SQL"}]
        assert all(call["resumes"] == [{"Docker"}, {"Excel"}] for call in ranking_calls)
    else:
        assert [call["vacancy"] for call in ranking_calls] == [{"TruthA"}, {"TruthB"}]
        assert all(call["resumes"] == [{"TruthA"}, {"TruthB"}] for call in ranking_calls)
    # Even oracle mode must measure extraction using predictions, not truth.
    for kind in ("resumes", "vacancies"):
        assert report["extraction"][kind]["micro"]["tp"] == 0
        assert report["extraction"][kind]["micro"]["fp"] == 2
        assert report["extraction"][kind]["micro"]["fn"] == 2
