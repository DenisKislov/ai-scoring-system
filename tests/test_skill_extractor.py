import pytest
from scorer.skill_extractor import SkillExtractor

TAXONOMY = [
    "Python", "PostgreSQL", "C++", "C#", ".NET", "1С", "1С: ERP",
    "JavaScript", "TypeScript", "FastAPI", "Docker", "Java",
    "сетевое оборудование", "английский язык", "HTML", "CSS"
]

@pytest.fixture(scope="module")
def extractor():
    return SkillExtractor(taxonomy=TAXONOMY)


# --- Тесты спецсимволов и границ слов ---

def test_special_characters_cpp_csharp_dotnet(extractor):
    text = "Требуется опыт разработки на C++, C# и платформе .NET Core."
    skills = extractor.extract(text)
    assert "C++" in skills
    assert "C#" in skills
    assert ".NET" in skills
    # Одиночная 'C' не должна определяться
    assert "C" not in skills


def test_1c_and_configurations(extractor):
    text = "Знание платформы 1С: ERP и опыт доработки типовой конфигурации 1С."
    skills = extractor.extract(text)
    assert "1С: ERP" in skills
    assert "1С" in skills


# --- Тесты CamelCase и защиты подстрок ---

def test_camelcase_preservation(extractor):
    text = "Стек: FastAPI, PostgreSQL, TypeScript."
    skills = extractor.extract(text)
    assert "FastAPI" in skills
    assert "PostgreSQL" in skills
    assert "TypeScript" in skills


def test_java_not_triggered_by_javascript(extractor):
    text = "Разработка клиентской части на JavaScript."
    skills = extractor.extract(text)
    assert "JavaScript" in skills
    assert "Java" not in skills, "Java не должна срабатывать как подстрока JavaScript"


# --- Тесты морфологии (падежи) ---

def test_russian_inflection_matching(extractor):
    text = "Опыт настройки и эксплуатации сетевого оборудования в офисе."
    skills = extractor.extract(text)
    assert "сетевое оборудование" in skills


# --- Тесты фильтрации шума ---

def test_language_section_is_ignored(extractor):
    text = """
    Опыт работы: Python, Docker.
    Иностранные языки:
    Английский язык — B2 (средне-продвинутый).
    """
    skills = extractor.extract(text)
    assert "Python" in skills
    assert "Docker" in skills
    assert "английский язык" not in skills, "Блок языков должен отсекаться"


def test_benefits_and_conditions_ignored(extractor):
    text = """
    Требования: Python, Docker.
    Условия работы:
    Обучение за счет компании, разработка корпоративных стандартов, ДМС.
    """
    skills = extractor.extract(text)
    assert "Python" in skills
    assert "Docker" in skills
    assert "разработка" not in skills
    assert "обучение" not in skills


# --- Тесты граничных условий ввода ---

def test_empty_and_whitespace_input(extractor):
    assert extractor.extract("") == set()
    assert extractor.extract("   \n\t  ") == set()
