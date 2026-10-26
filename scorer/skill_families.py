"""Семьи родственных навыков для матчинга резюме ↔ вакансия.

Проблема на реальных данных (data/superjob_dataset.json): требования вакансий
записаны «широкими» навыками (``SQL``, ``Machine Learning``, ``Аналитика
данных``), а резюме — конкретными технологиями (``MySQL``, ``scikit-learn``,
``Tableau``). Формальное пересечение множеств давало keyword_score ~0.38 даже
для идеальных кандидатов: ``MySQL`` не считался владением ``SQL``.

Семья — группа имён (в нижнем регистре, в нотации после
``skills.normalize_skill_set``), любое из которых закрывает требование,
выраженное любым другим именем группы. Состав семей собран из реального
словаря датасета: добавляйте технологии сюда, а не в caller-код.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Set

# Каждая группа — взаимозаменяемые на уровне требования навыки.
SKILL_FAMILY_GROUPS = [
    # SQL и конкретные SQL-СУБД
    {"sql", "mysql", "postgresql", "postgres", "sqlite", "ms sql", "mssql",
     "t-sql", "pl/sql", "oracle", "oracle db", "clickhouse", "greenplum",
     "vertica"},
    # ML и библиотеки/методы
    {"machine learning", "ml", "машинное обучение", "scikit-learn", "sklearn",
     "pytorch", "tensorflow", "keras", "xgboost", "catboost", "lightgbm",
     "градиентный бустинг", "random forest", "kmeans", "нейронные сети",
     "нейросети", "deep learning", "глубокое обучение"},
    # Анализ данных / BI / отчётность
    {"анализ данных", "аналитика данных", "data analysis", "ad-hoc аналитика",
     "статистика", "статистический анализ", "a/b тесты", "a/b testing",
     "дашборды", "tableau", "power bi", "ms power bi", "excel", "ms excel",
     "matplotlib", "seaborn", "plotly"},
    # Big Data
    {"большие данные", "big data", "spark", "apache spark", "pyspark",
     "hadoop", "hive", "databricks"},
    # ETL / оркестрация данных
    {"etl", "etl-пайплайны", "пайплайны данных", "airflow", "apache airflow",
     "nifi", "ssis", "aws glue"},
    # JavaScript-стек
    {"javascript", "js", "typescript", "react", "react.js", "reactjs", "vue",
     "vue.js", "angular", "angularjs", "node.js", "nodejs", "jquery"},
    # Java-стек
    {"java", "spring", "spring boot", "spring framework", "java ee",
     "jakarta ee"},
    # Тестирование
    {"тестирование", "qa", "тест-дизайн", "test design",
     "ручное тестирование", "автоматизированное тестирование", "автотесты",
     "selenium", "pytest", "postman", "soapui", "нагрузочное тестирование"},
    # ООП
    {"ооп", "oop", "объектно-ориентированное программирование",
     "объектно ориентированное программирование"},
    # Linux-дистрибутивы
    {"linux", "ubuntu", "debian", "centos", "red hat", "redhat",
     "astra linux", "alt linux"},
    # 1С-конфигурации закрывают требование «1С»
    {"1с", "1с 8", "1с: предприятие 8", "1с: erp", "1с: бухгалтерия",
     "1с: ка", "1с: ух", "1с: зарплата и кадры", "1с: управление персоналом",
     "1с программирование", "1с упп", "1с ут"},
    # API-интерфейсы
    {"api", "rest api", "rest", "restful", "grpc", "graphql", "swagger",
     "openapi"},
    # Документация
    {"техническая документация", "документация", "confluence",
     "atlassian confluence"},
    # Английский
    {"английский язык", "english"},
]

# skill (lowercase) -> множество имён его семьи (без самого навыка)
_FAMILY_INDEX: Dict[str, FrozenSet[str]] = {}
for _group in SKILL_FAMILY_GROUPS:
    _frozen = frozenset(_group)
    for _name in _group:
        # Группы могут пересекаться (ml входит и в ML, и в экосистемы) —
        # объединяем всех родичей из всех групп.
        _FAMILY_INDEX[_name] = _FAMILY_INDEX.get(_name, frozenset()) | _frozen


def family_of(skill: str) -> FrozenSet[str]:
    """Имена-родственники навыка (включая его самого) или пустое множество."""
    return _FAMILY_INDEX.get(skill.strip().lower(), frozenset())


def family_satisfied(requirement: str, resume_skills: Set[str]) -> bool:
    """Закрывает ли какое-либо имя из ``resume_skills`` требование
    ``requirement`` через семейную эквивалентность."""
    family = _FAMILY_INDEX.get(requirement.strip().lower())
    if not family:
        return False
    return any(s.strip().lower() in family for s in resume_skills)
