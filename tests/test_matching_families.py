"""Направленное сопоставление навыков в скорере."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scorer.skills import match_skills, normalize_skill_set  # noqa: E402


def kw(resume_text: str, vacancy_text: str) -> float:
    return match_skills(resume_text, vacancy_text)["keyword_score"]


# --- технические семьи --------------------------------------------------------

def test_sql_satisfied_by_mysql():
    score = kw("Работал с MySQL и PostgreSQL, оптимизация запросов",
               "Требуется: SQL")
    assert score == 1.0


def test_sql_satisfied_by_clickhouse():
    score = kw("Стек: ClickHouse, ETL", "Требуется: SQL, ETL")
    assert score >= 0.5


def test_machine_learning_satisfied_by_libs():
    score = kw("Опыт: scikit-learn, PyTorch, XGBoost",
               "Требуется: Machine Learning, Python")
    assert score >= 0.5


def test_deep_learning_satisfies_ml():
    score = kw("Deep Learning, нейронные сети", "Требуется: Machine Learning")
    assert score == 1.0


def test_bigdata_satisfied_by_spark():
    score = kw("Apache Spark, PySpark, кластеры", "Требуется: большие данные")
    assert score == 1.0


def test_data_analysis_satisfied_by_bi():
    # «Аналитика данных» в вакансии закрывается BI-стеком резюме
    score = kw("Делаю дашборды в Tableau и Power BI, A/B тесты",
               "Требуется: Аналитика данных")
    assert score == 1.0


def test_data_analysis_satisfied_by_adhoc_analytics():
    r = match_skills(
        "", "", vacancy_skills={"Аналитика данных"},
        resume_skills={"ad-hoc аналитика"})
    assert r["matched"] == normalize_skill_set({"Аналитика данных"})


def test_javascript_satisfied_by_react():
    score = kw("Frontend: React, TypeScript", "Требуется: JavaScript")
    assert score == 1.0


def test_testing_satisfied_by_qa_terms():
    # «тестирование» — требование из expected_skills вакансий; в тексте оно
    # слишком частотно для извлечения (эмпирика: 5 TP / 24 FP), поэтому
    # требование передаётся готовым множеством, как в production-потоке.
    r = match_skills(
        resume_text="QA-инженер: selenium, тест-дизайн, автотесты",
        vacancy_text="",
        vacancy_skills={"тестирование"},
        resume_skills={"selenium", "тест-дизайн", "автотесты"})
    assert "тестирование" in r["matched"]


def test_oop_satisfied_by_full_phrase():
    score = kw("Знаю объектно-ориентированное программирование",
               "Требуется: ООП")
    assert score == 1.0


# --- семьи не должны давать ложных срабатываний -------------------------------

def test_unrelated_skills_still_zero():
    score = kw("Бухгалтер: 1С, налоговый учёт, зарплата",
               "Требуется: SQL, Machine Learning")
    assert score == 0.0


def test_family_member_alone_does_not_satisfy_other_requirement():
    # MySQL закрывает SQL, но не Machine Learning
    score = kw("Только MySQL", "Требуется: SQL, Machine Learning")
    assert score == 0.5


def test_missing_reports_family_unmatched():
    r = match_skills("Только MySQL", "Требуется: SQL, Machine Learning")
    missing_lower = {s.lower() for s in r["missing"]}
    matched_lower = {s.lower() for s in r["matched"]}
    assert "machine learning" in missing_lower
    assert "sql" in matched_lower


# --- работа через normalize_skill_set (production-путь) -----------------------

def test_family_works_with_precomputed_skill_sets():
    v = normalize_skill_set({"SQL", "Machine Learning"})
    r = normalize_skill_set({"PostgreSQL", "scikit-learn"})
    out = match_skills(resume_text="", vacancy_text="",
                       vacancy_skills=v, resume_skills=r)
    assert out["keyword_score"] == 1.0


def test_critical_skill_satisfied_by_family():
    v = normalize_skill_set({"SQL", "Docker"})
    r = normalize_skill_set({"MySQL", "Docker"})
    out = match_skills(resume_text="", vacancy_text="",
                       vacancy_skills=v, critical_skills={"SQL"},
                       resume_skills=r)
    assert out["matched_critical"] == {"SQL"}
    assert out["missing_critical"] == set()


@pytest.mark.parametrize('requirement,known', [
    ('PostgreSQL', 'MySQL'), ('PostgreSQL', 'SQL'), ('MySQL', 'PostgreSQL'),
    ('React', 'JavaScript'), ('React', 'Vue'), ('TypeScript', 'JavaScript'),
    ('PyTorch', 'TensorFlow'), ('Deep Learning', 'Machine Learning'),
    ('Power BI', 'Excel'), ('A/B testing', 'Tableau'),
    ('Airflow', 'ETL'), ('Spring', 'Java'), ('Selenium', 'Postman'),
    ('Ubuntu', 'Linux'), ('1С: Бухгалтерия', '1С: ERP'), ('GraphQL', 'REST API'),
])
def test_related_skill_does_not_satisfy_a_specific_critical_requirement(requirement, known):
    result = match_skills('', '', vacancy_skills={requirement},
                          resume_skills={known}, critical_skills={requirement})
    assert result['matched'] == set()
    assert result['missing_critical'] == normalize_skill_set({requirement})
    assert result['keyword_score'] == 0.0
