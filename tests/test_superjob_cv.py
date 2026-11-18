"""Guard the split boundaries and the scope of cross-validation evidence."""
from copy import deepcopy

import spacy

from training.ner.superjob_cv import (
    evaluate_predictions, inner_split, make_folds, reference_docs,
)


def record(i, text, kind="resumes", truth=None):
    return {"key": f"{kind}/{i:03}", "kind": kind, "index": i,
            "text": text, "original_text": text,
            "truth": ["Python"] if truth is None else truth}


def test_duplicate_documents_stay_in_one_fold_even_with_different_labels():
    rows = [record(i, f"Документ {i}. Навыки: Python, технология {i}.") for i in range(20)]
    rows += [record(20, rows[0]["text"], truth=["Docker"])]
    folds, groups = make_folds(rows)
    assert any({0, 20} <= set(group) for group in groups)
    assert sum(0 in fold and 20 in fold for fold in folds) == 1
    changed = deepcopy(rows)
    changed[0]["truth"] = ["PHP", "SQL", "Java"]
    assert make_folds(changed) == (folds, groups)


def test_outer_test_is_never_used_for_fit_or_early_stopping():
    rows = [record(i, f"Уникальный профиль {i}: навыки Python, инструмент_{i}.") for i in range(30)]
    folds, groups = make_folds(rows)
    predicted = []
    for k, test in enumerate(folds):
        fit, monitor = inner_split(rows, groups, test, 42 + k)
        assert not set(fit) & set(monitor)
        assert not set(test) & (set(fit) | set(monitor))
        assert set(fit) | set(monitor) | set(test) == set(range(len(rows)))
        predicted.extend(test)
    assert sorted(predicted) == list(range(len(rows)))


def test_near_copy_cannot_leak_into_another_fold():
    text = " ".join(f"технология{i}" for i in range(70))
    rows = [record(0, text), record(1, text.replace("технология35", "другаятехнология"))]
    rows += [record(i, f"Профиль {i}: самостоятельная специальность{i}") for i in range(2, 12)]
    folds, groups = make_folds(rows)
    assert any({0, 1} <= set(group) for group in groups)
    assert any({0, 1} <= set(fold) for fold in folds)
    for k, test in enumerate(folds):
        fit, monitor = inner_split(rows, groups, test, 100 + k)
        assert not ({0, 1} & set(test) and {0, 1} & (set(fit) | set(monitor)))


def test_ten_vacancies_are_balanced_across_five_folds():
    rows = [record(i, f"Вакансия {i}: Python, технология_{i}.", "vacancies") for i in range(10)]
    rows += [record(i, f"Резюме {i}: уникальная специализация_{i}.") for i in range(194)]
    folds, _ = make_folds(rows)
    assert [sum(rows[i]["kind"] == "vacancies" for i in fold) for fold in folds] == [2] * 5
    assert max(map(len, folds)) - min(map(len, folds)) <= 1


def test_missing_reference_skill_is_not_inserted_into_training_text():
    nlp = spacy.blank("ru")
    rows = [record(0, "Навыки: Python.", truth=["Python", "PostgreSQL"])]
    original = deepcopy(rows)
    docs, coverage = reference_docs(nlp, rows, [0])
    assert rows == original
    assert [e.text for doc in docs for e in doc.ents] == ["Python"]
    assert coverage["unmatched_skills"] == 1
    assert "PostgreSQL" not in " ".join(doc.text for doc in docs)


def test_no_relevant_candidates_does_not_fabricate_a_recall_value():
    rows = [record(0, "Требуется Python", "vacancies"),
            record(0, "Навыки: Python", truth=[])]
    result = evaluate_predictions(rows, {0: ["Python"], 1: ["Python"]})
    assert result["ranking"]["mean"]["recall_at_10"] is None
    assert result["numeric_thresholds"]["recall_at_10"]["passed"] is False
