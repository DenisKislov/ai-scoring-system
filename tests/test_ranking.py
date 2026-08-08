"""QA-тесты ядра скоринга (scorer.scoring).

Кейс «AI-система для скоринга кандидатов», роль: QA/Tools Support.
Требования из ТЗ:
* Показ 3  — система не даёт 100% совпадение совершенно разным текстам;
* Спринт 5 — пустые файлы не ломают систему;
* MVP      — список кандидатов отсортирован по степени соответствия.
"""
from scorer import calculate_score, rank_candidates

VACANCY = "Требуется Python-разработчик: Python, Django, PostgreSQL, Git."
STRONG = "Python-разработчик, 3 года опыта: Django, PostgreSQL, Git, REST API."
MEDIUM = "QA-инженер: тестирование, немного SQL и Python."
WEAK = "Работал поваром: борщ, компоты, выпечка."


# --- calculate_score --------------------------------------------------------

def test_score_range():
    """Балл всегда в диапазоне 0–100."""
    for resume in (STRONG, MEDIUM, WEAK):
        res = calculate_score(resume, VACANCY)
        assert 0 <= res["score"] <= 100


def test_unrelated_texts_not_100():
    """Показ 3: совершенно разные тексты не получают 100%."""
    assert calculate_score(WEAK, VACANCY)["score"] < 100


def test_strong_beats_weak():
    """Релевантное резюме получает балл выше нерелевантного."""
    assert calculate_score(STRONG, VACANCY)["score"] > calculate_score(WEAK, VACANCY)["score"]


def test_empty_inputs_do_not_break():
    """Спринт 5: пустые тексты не ломают систему."""
    assert calculate_score("", VACANCY)["score"] == 0
    assert calculate_score(STRONG, "")["score"] == 0
    assert calculate_score("   ", "   ")["score"] == 0


def test_matched_skills_found():
    """Для релевантного резюме находятся ключевые навыки."""
    res = calculate_score(STRONG, VACANCY)
    assert len(res["matched_skills"]) > 0


# --- rank_candidates ---------------------------------------------------------

def test_empty_pool():
    """Пустой список кандидатов возвращает пустой список."""
    assert rank_candidates(VACANCY, []) == []


def test_results_sorted_desc():
    """MVP: кандидаты отсортированы по убыванию балла."""
    results = rank_candidates(VACANCY, [WEAK, STRONG, MEDIUM])
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_candidate_ids_preserved():
    """ID кандидатов не теряются при ранжировании."""
    results = rank_candidates(VACANCY, [WEAK, STRONG], candidate_ids=["a", "b"])
    assert {r["candidate_id"] for r in results} == {"a", "b"}


def test_percentile_top_and_bottom():
    """Лучший кандидат получает percentile 100, худший — 0."""
    results = rank_candidates(VACANCY, [WEAK, MEDIUM, STRONG])
    assert results[0]["rank_percentile"] == 100
    assert results[-1]["rank_percentile"] == 0