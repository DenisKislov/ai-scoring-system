"""Тесты парсинга опыта работы из русскоязычных резюме.

Проверяют ``api.nlp_parser.extract_experience_years`` — единый парсер опыта,
которым пользуется и загрузка PDF-резюме (``db.builders``), и импорт SuperJob.

Форматы реальных данных (data/dataset_resume.json, PDF-резюме):
* «Опыт работы: 5 лет» / «Опыт работы — 3 года» / «Опыт работы 2 года»
* «2 года и 1 месяц» (значение поля experience без префикса)
* «Общий стаж: 22 года и 8 месяцев» / «Стаж 10 лет»
* «полгода», «6 месяцев», «менее года», «более 3 лет»
* периоды: «апрель 2021 — настоящее время», «июнь 2010 — июнь 2013»
* «Без опыта»
"""
from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.nlp_parser import extract_experience_years  # noqa: E402


NOW = date(2026, 10, 7)  # фиксированная «сегодняшняя» дата для воспроизводимости


def approx(actual, expected, tol=0.15):
    assert actual is not None, f"expected ~{expected}, got None"
    assert abs(actual - expected) <= tol, f"expected ~{expected}, got {actual}"


# --- явные формулировки ------------------------------------------------------

def test_explicit_years_with_colon():
    assert extract_experience_years("Опыт работы: 5 лет", now=NOW) == 5.0


def test_explicit_years_with_dash():
    assert extract_experience_years("Опыт работы — 3 года", now=NOW) == 3.0


def test_explicit_years_no_punctuation():
    assert extract_experience_years("Опыт работы 2 года", now=NOW) == 2.0


def test_years_and_months_value_without_prefix():
    # значение поля experience из SuperJob: «2 года и 1 месяц»
    approx(extract_experience_years("2 года и 1 месяц", now=NOW), 2.08, tol=0.01)


def test_years_and_months_long_form():
    approx(extract_experience_years(
        "Общий стаж: 22 года и 8 месяцев", now=NOW), 22.67, tol=0.01)


def test_stazh_keyword():
    assert extract_experience_years("Стаж 10 лет", now=NOW) == 10.0


def test_years_of_experience_phrase():
    assert extract_experience_years("5 лет опыта в разработке", now=NOW) == 5.0


def test_more_than_n_years():
    assert extract_experience_years("опыт более 3 лет", now=NOW) == 3.0


def test_less_than_year():
    assert extract_experience_years("опыт менее года", now=NOW) == 0.5


def test_half_year():
    assert extract_experience_years("Опыт работы: полгода", now=NOW) == 0.5


def test_months_only():
    approx(extract_experience_years("Опыт работы: 6 месяцев", now=NOW), 0.5, tol=0.01)


def test_no_experience():
    assert extract_experience_years("Без опыта работы", now=NOW) == 0.0


def test_no_match_returns_none():
    assert extract_experience_years("Образование: высшее, МГУ", now=NOW) is None


def test_not_fooled_by_years_range():
    # «2019–2022» — это годы учёбы, не опыт
    assert extract_experience_years(
        "Образование: 2019–2022, МГУ", now=NOW) is None


# --- периоды работы ----------------------------------------------------------

def test_period_range_closed():
    approx(extract_experience_years(
        "Опыт работы: июнь 2010 — июнь 2013", now=NOW), 3.0)


def test_period_range_open_ended():
    approx(extract_experience_years(
        "апрель 2021 — настоящее время", now=NOW), 5.5)


def test_period_years_only():
    approx(extract_experience_years("2018 — 2021", now=NOW), 3.0)


def test_multiple_periods_summed():
    text = (
        "Опыт работы:\n"
        "- Инженер (январь 2008 — июнь 2010): ...\n"
        "- Ведущий инженер (июнь 2010 — июнь 2013): ..."
    )
    approx(extract_experience_years(text, now=NOW), 5.5)


def test_explicit_statement_preferred_over_periods():
    text = "Опыт работы: 7 лет\n- Инженер (2010 — 2015)"
    assert extract_experience_years(text, now=NOW) == 7.0


# --- интеграция с db.builders -------------------------------------------------

def test_builders_experience_years_from_superjob_value():
    from db.builders import experience_years
    doc = {"experience": "Опыт работы: 2 года и 1 месяц"}
    approx(experience_years(doc), 2.08, tol=0.01)


def test_builders_experience_years_falls_back_to_raw_text():
    from db.builders import experience_years
    doc = {
        "experience": "",
        "_raw_text": "Опыт работы:\n- Слесарь (март 2015 — март 2020): ремонт",
    }
    approx(experience_years(doc), 5.0)


def test_builders_parse_raw_text_resume_experience():
    from db.builders import parse_raw_text_to_resume
    parsed = parse_raw_text_to_resume(
        "Должность: Data Scientist\nОпыт работы — 4 года 6 месяцев\nPython, SQL")
    assert parsed["experience_years"] == 4.5
    assert parsed["title"] == "Data Scientist"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS  {name}")
    print("\nALL EXPERIENCE TESTS PASSED")
