"""Категории навыков для метрик Precision / Recall / F1.

Онтология скорера (``skills_dict.SKILLS_ALL``) — плоский словарь
«канонический навык -> алиасы». Для оценки качества извлечения навыков этого
недостаточно: чтобы считать Precision/Recall/F1 не только целиком, но и **по
категориям** (языки, базы данных, ML, frontend, backend, DevOps, BI,
процессы), нужна разметка, к какой категории относится каждый навык.

Модуль задаёт таксономию:

* ``CATEGORIES`` — канонический порядок категорий;
* ``SKILL_CATEGORIES`` — явная разметка курируемых навыков из ``skills_dict``
  (``SKILLS`` + ``RAW_SKILLS``) и точечных авто-навыков, которые нельзя
  надёжно отнести по ключевым словам;
* ``_CATEGORY_KEYWORDS`` — упорядоченные правила для остальной (авто-)
  онтологии: категория -> ключевые слова, которые ищутся в каноническом имени
  навыка с учётом границ слов. Классификатор детерминированный и не требует
  внешних моделей.

``category_of`` сначала смотрит явную разметку, затем keyword-правила, затем
возвращает ``CATEGORY_OTHER``. ``categorize`` группирует произвольное множество
навыков в ``{категория: set(навыков)}``.

Правила подобраны под IT-словарь проекта (hh.ru, русские + английские
канонические имена). Это эвристика для оценки качества, а не часть скоринга:
если в онтологию добавляются навыки, которых нет в правилах, они попадают в
``Прочее`` — метрики при этом остаются корректными.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, Set, Tuple

# --- Категории -------------------------------------------------------------

CATEGORY_LANGUAGES = "Языки программирования"
CATEGORY_DATABASES = "Базы данных"
CATEGORY_ML = "ML / Data Science"
CATEGORY_FRONTEND = "Frontend"
CATEGORY_BACKEND = "Backend / API"
CATEGORY_DEVOPS = "DevOps / Инфраструктура"
CATEGORY_BI = "BI / Аналитика"
CATEGORY_PROCESS = "Процессы / Soft skills"
CATEGORY_OTHER = "Прочее"

CATEGORIES: Tuple[str, ...] = (
    CATEGORY_LANGUAGES,
    CATEGORY_DATABASES,
    CATEGORY_ML,
    CATEGORY_FRONTEND,
    CATEGORY_BACKEND,
    CATEGORY_DEVOPS,
    CATEGORY_BI,
    CATEGORY_PROCESS,
    CATEGORY_OTHER,
)

# --- Явная разметка --------------------------------------------------------
# Курируемые навыки (skills_dict.SKILLS + RAW_SKILLS) и точечные авто-навыки,
# для которых keyword-правила дали бы неверный или неоднозначный результат.

SKILL_CATEGORIES: Dict[str, str] = {
    # Языки программирования
    "Python": CATEGORY_LANGUAGES,
    "Java": CATEGORY_LANGUAGES,
    "JavaScript": CATEGORY_LANGUAGES,
    "TypeScript": CATEGORY_LANGUAGES,
    "Go": CATEGORY_LANGUAGES,
    "Kotlin": CATEGORY_LANGUAGES,
    "PHP": CATEGORY_LANGUAGES,
    "Ruby": CATEGORY_LANGUAGES,
    "Scala": CATEGORY_LANGUAGES,
    "Swift": CATEGORY_LANGUAGES,
    "C++": CATEGORY_LANGUAGES,
    "C#": CATEGORY_LANGUAGES,

    # Базы данных
    "SQL": CATEGORY_DATABASES,
    "SQL (advanced)": CATEGORY_DATABASES,
    "PostgreSQL": CATEGORY_DATABASES,
    "MySQL": CATEGORY_DATABASES,
    "MongoDB": CATEGORY_DATABASES,
    "Redis": CATEGORY_DATABASES,
    "ClickHouse": CATEGORY_DATABASES,
    "Elasticsearch": CATEGORY_DATABASES,

    # ML / Data Science
    "Machine Learning": CATEGORY_ML,
    "Deep Learning": CATEGORY_ML,
    "Data Science": CATEGORY_ML,
    "NLP": CATEGORY_ML,
    "Computer Vision": CATEGORY_ML,
    "Artificial Intelligence": CATEGORY_ML,
    "Pandas": CATEGORY_ML,
    "NumPy": CATEGORY_ML,
    "scikit-learn": CATEGORY_ML,
    "TensorFlow": CATEGORY_ML,
    "PyTorch": CATEGORY_ML,
    "Keras": CATEGORY_ML,
    "OpenCV": CATEGORY_ML,
    "TensorRT": CATEGORY_ML,
    "Recommender Systems": CATEGORY_ML,
    "Matplotlib": CATEGORY_ML,
    "OCR": CATEGORY_ML,
    "Speech-to-Text": CATEGORY_ML,
    "Core ML": CATEGORY_ML,
    "Spark": CATEGORY_ML,
    "Hadoop": CATEGORY_ML,
    "ETL": CATEGORY_ML,
    "Аналитика данных": CATEGORY_ML,

    # Frontend
    "React": CATEGORY_FRONTEND,
    "Angular": CATEGORY_FRONTEND,
    "Vue": CATEGORY_FRONTEND,
    "HTML": CATEGORY_FRONTEND,
    "CSS": CATEGORY_FRONTEND,

    # Backend / API
    "REST API": CATEGORY_BACKEND,
    "FastAPI": CATEGORY_BACKEND,
    "Django": CATEGORY_BACKEND,
    "Flask": CATEGORY_BACKEND,
    "Spring": CATEGORY_BACKEND,
    "Node.js": CATEGORY_BACKEND,
    ".NET": CATEGORY_BACKEND,

    # DevOps / Инфраструктура
    "Docker": CATEGORY_DEVOPS,
    "Kubernetes": CATEGORY_DEVOPS,
    "Linux": CATEGORY_DEVOPS,
    "Bash": CATEGORY_DEVOPS,
    "Git": CATEGORY_DEVOPS,
    "Jenkins": CATEGORY_DEVOPS,
    "Ansible": CATEGORY_DEVOPS,
    "Terraform": CATEGORY_DEVOPS,
    "AWS": CATEGORY_DEVOPS,
    "GCP": CATEGORY_DEVOPS,
    "CI/CD": CATEGORY_DEVOPS,

    # BI
    "Tableau": CATEGORY_BI,
    "Power BI": CATEGORY_BI,
    "Excel": CATEGORY_BI,

    # Процессы / методологии
    "Agile": CATEGORY_PROCESS,
    "Scrum": CATEGORY_PROCESS,

    # Точечные авто-навыки: короткие имена, которые нельзя надёжно отнести
    # по keyword-правилам ("ai", "ml" как подстроки дают ложные срабатывания).
    "AI": CATEGORY_ML,
    "AI/ML": CATEGORY_ML,
    "AI-разработка": CATEGORY_ML,
}

# --- Keyword-правила для остальной онтологии -------------------------------
# Порядок категорий важен: проверяется по очереди, первая категория, чьё
# ключевое слово матчится, выигрывает. Поэтому более специфичные/приоритетные
# категории идут раньше (например, ML раньше DevOps — чтобы «Core MLLinux» не
# уехал в DevOps по слову «linux»).

_CATEGORY_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    CATEGORY_LANGUAGES: (
        "dart", "kotlin", "swift", "typescript", "php", "golang", "rust",
        "scala", "ruby", "c++", "c#", "python", "java", "javascript",
        "multithreading", "qt", "qml", "алгоритмы и структуры данных", "ооп",
    ),
    CATEGORY_DATABASES: (
        "sql", "postgresql", "postgres", "mysql", "mongo", "redis",
        "clickhouse", "elasticsearch", "greenplum", "oracle", "nosql",
        "bigquery", "базы данных", "dwh", "ms sql", "sqlalchemy", "hibernate",
        "orm", "patroni", "prisma",
    ),
    CATEGORY_ML: (
        "machine learning", "deep learning", "data science", "data analysis",
        "natural language processing", "computer vision", "tensorflow",
        "pytorch", "pandas", "numpy", "scikit-learn", "catboost", "xgboost",
        "lightgbm", "pyspark", "spark", "hadoop", "llm", "langchain",
        "langgraph", "rag", "cv", "ocr", "speech-to-text", "triton",
        "torchserve", "mlflow", "nltk", "statistics", "статистика",
        "математический анализ", "математическое моделирование",
        "прикладная статистика", "исследовательский анализ данных",
        "mathematics", "scipy", "matplotlib", "big data", "eda",
        "learning to rank", "recommender systems", "core ml", "mllinux",
        "vllm", "airflow", "tensorrt", "claude code", "codex",
    ),
    CATEGORY_FRONTEND: (
        "angular", "vue", "svelte", "nuxt", "next", "webpack", "redux",
        "css", "html", "scss", "sass", "material design", "ui", "ux", "spa",
        "chartjs", "dchart", "3dchart", "figma", "elementplus", "winforms",
        "wpf", "верстка", "кроссбраузерная", "адаптивная",
        "веб-программирование", "торговая площадка", "frontend", "wordpress",
        "drupal", "jquery", "ant", "react", "flutter", "android", "ios",
        "битрикс", "html5", "css3", "es6",
    ),
    CATEGORY_BACKEND: (
        "api", "rest api", "restful api", "graphql", "grpc", "rabbitmq",
        "celery", "spring data", "pydantic", "jwt", "json", "xml", "http",
        "websocket", "backend", "django", "flask", "fast api", "fastapi",
        "kafka", "laravel", "yii", "opencart", "amocrm", "elma",
        "entity framework", "микросервисная архитектура", "1с", "swagger",
        "node",
    ),
    CATEGORY_DEVOPS: (
        "bitbucket", "github", "gitlab", "grafana", "haproxy", "helm",
        "iptables", "istio", "kserve", "keycloak", "nexus", "nginx",
        "prometheus", "teamcity", "ubuntu", "vmware", "zabbix",
        "docker swarm", "ит-инфраструктура", "информационная безопасность",
        "сетевые протоколы", "сетевые технологии", "автоматизация процессов",
        "администрирование серверов linux", "azure", "aws", "gcp", "sentry",
        "elk", "rbac", "web security", "devops", "terraform", "ansible",
        "jenkins", "kubernetes", "k8s", "docker", "linux", "bash", "git",
        "tcp/ip", "gitlab ci", "ci/cd", "ci cd",
    ),
    CATEGORY_BI: (
        "tableau", "power bi", "powerbi", "excel", "superset",
        "apache superset",
    ),
    CATEGORY_PROCESS: (
        "agile", "scrum", "tdd", "pytest", "jest", "solid", "uml", "bpmn",
        "jira", "confluence", "atlassian", "оптимизация кода",
        "рефакторинг кода", "управление командой", "работа в команде",
        "ответственность", "самостоятельность", "аккуратность",
        "навыки декомпозиции", "навыки архитектрного проектирования",
        "аналитическое мышление", "английский", "architecture decision records",
    ),
}

# Порядок, в котором проверяются keyword-правила (== CATEGORIES без OTHER).
_KEYWORD_ORDER: Tuple[str, ...] = (
    CATEGORY_LANGUAGES,
    CATEGORY_DATABASES,
    CATEGORY_ML,
    CATEGORY_FRONTEND,
    CATEGORY_BACKEND,
    CATEGORY_DEVOPS,
    CATEGORY_BI,
    CATEGORY_PROCESS,
)


def _match_keyword(normalized: str, keyword: str) -> bool:
    """Ищет *keyword* в *normalized* с учётом границ «слова».

    Границы по символам, которые не являются буквой/цифрой, чтобы короткие
    ключи не срабатывали внутри других слов: ``sql`` не матчится в ``mysql``,
    ``ml`` не матчится в ``html``, ``git`` — в ``github``.
    """
    pattern = rf"(?<![a-zа-яё0-9]){re.escape(keyword)}(?![a-zа-яё0-9])"
    return re.search(pattern, normalized) is not None


def category_of(skill: str) -> str:
    """Возвращает категорию канонического навыка.

    Порядок: явная разметка ``SKILL_CATEGORIES`` -> keyword-правила ->
    ``CATEGORY_OTHER``.
    """
    if not skill:
        return CATEGORY_OTHER
    if skill in SKILL_CATEGORIES:
        return SKILL_CATEGORIES[skill]
    normalized = skill.strip().lower()
    for category in _KEYWORD_ORDER:
        for keyword in _CATEGORY_KEYWORDS[category]:
            if _match_keyword(normalized, keyword):
                return category
    return CATEGORY_OTHER


def categorize(skills: Iterable[str]) -> Dict[str, Set[str]]:
    """Группирует навыки по категориям: ``{категория: set(навыков)}``.

    Возвращает **все** категории из ``CATEGORIES`` (включая пустые), чтобы
    перебор результата был детерминированным. Каждый навык попадает ровно в
    одну категорию — разбиение корректно для агрегирования микро-метрик.
    """
    grouped: Dict[str, Set[str]] = {category: set() for category in CATEGORIES}
    for skill in skills:
        grouped[category_of(skill)].add(skill)
    return grouped


__all__ = [
    "CATEGORIES",
    "CATEGORY_LANGUAGES",
    "CATEGORY_DATABASES",
    "CATEGORY_ML",
    "CATEGORY_FRONTEND",
    "CATEGORY_BACKEND",
    "CATEGORY_DEVOPS",
    "CATEGORY_BI",
    "CATEGORY_PROCESS",
    "CATEGORY_OTHER",
    "SKILL_CATEGORIES",
    "category_of",
    "categorize",
]
