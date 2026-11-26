"""Explicit evidence that satisfies a broader vacancy requirement."""
from typing import FrozenSet, Set

# Each row gives equivalent spellings of one requirement and more specific
# skills accepted for that requirement. Specific skills are not interchangeable.
_DIRECTIONS = [
    ({"sql"}, {
        "mysql", "postgresql", "postgres", "sqlite", "ms sql", "mssql", "t-sql",
        "pl/sql", "oracle", "oracle db", "clickhouse", "greenplum", "vertica",
    }),
    ({"machine learning", "ml", "машинное обучение"}, {
        "scikit-learn", "sklearn", "pytorch", "tensorflow", "keras", "xgboost",
        "catboost", "lightgbm", "градиентный бустинг", "random forest", "kmeans",
        "нейронные сети", "нейросети", "deep learning", "глубокое обучение",
    }),
    ({"deep learning", "глубокое обучение"}, {"нейронные сети", "нейросети"}),
    ({"анализ данных", "аналитика данных", "data analysis"}, {
        "ad-hoc аналитика", "a/b тесты", "a/b testing", "статистический анализ",
        "tableau", "power bi", "ms power bi", "matplotlib", "seaborn", "plotly",
    }),
    ({"a/b тесты", "a/b testing"}, set()),
    ({"excel", "ms excel"}, set()),
    ({"power bi", "ms power bi"}, set()),
    ({"дашборды"}, {"tableau", "power bi", "ms power bi"}),
    ({"большие данные", "big data"}, {"spark", "apache spark", "pyspark", "hadoop", "hive", "databricks"}),
    ({"spark", "apache spark"}, {"pyspark"}),
    ({"etl", "etl-пайплайны", "пайплайны данных"}, {
        "airflow", "apache airflow", "nifi", "ssis", "aws glue",
    }),
    ({"airflow", "apache airflow"}, set()),
    ({"javascript", "js"}, {
        "typescript", "react", "react.js", "reactjs", "vue", "vue.js", "angular",
        "angularjs", "node.js", "nodejs", "jquery",
    }),
    ({"react", "react.js", "reactjs"}, set()),
    ({"vue", "vue.js"}, set()),
    ({"node.js", "nodejs"}, set()),
    ({"java"}, {"java ee", "jakarta ee"}),
    ({"spring", "spring framework"}, {"spring boot"}),
    ({"тестирование", "qa"}, {
        "тест-дизайн", "test design", "ручное тестирование", "автоматизированное тестирование",
        "автотесты", "selenium", "pytest", "postman", "soapui", "нагрузочное тестирование",
    }),
    ({"автоматизированное тестирование", "автотесты"}, {"selenium", "pytest"}),
    ({"ооп", "oop", "объектно-ориентированное программирование",
      "объектно ориентированное программирование"}, set()),
    ({"linux"}, {"ubuntu", "debian", "centos", "red hat", "redhat", "astra linux", "alt linux"}),
    ({"1с", "1с 8", "1с: предприятие 8"}, {
        "1с: erp", "1с: бухгалтерия", "1с: ка", "1с: ух", "1с: зарплата и кадры",
        "1с: ут", "1с: упп", "1с программирование",
    }),
    ({"api"}, {"rest api", "rest", "restful", "grpc", "graphql", "soapui"}),
    ({"rest api", "rest", "restful"}, set()),
    ({"документация"}, {"техническая документация"}),
    ({"английский язык", "english"}, set()),
]

_EVIDENCE = {
    general: frozenset(equivalents | specific)
    for equivalents, specific in _DIRECTIONS
    for general in equivalents
}


def family_of(skill: str) -> FrozenSet[str]:
    """Skills accepted as evidence for this requirement."""
    return _EVIDENCE.get(skill.strip().casefold(), frozenset())


def family_satisfied(requirement: str, resume_skills: Set[str]) -> bool:
    evidence = family_of(requirement)
    return any(skill.strip().casefold() in evidence for skill in resume_skills)
