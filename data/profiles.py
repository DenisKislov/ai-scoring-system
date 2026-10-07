"""Coherent role profiles and varied text renderers for synthetic evaluation.

The broad ``skills_by_profession.json`` remains an ontology source. This module
uses compact, plausible stacks from ``synthetic_roles.json`` for generation.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import List, Sequence

_DICT_PATH = Path(__file__).with_name("synthetic_roles.json")
REFERENCE_YEAR = 2026  # fixed so a seed reproduces the same career timeline


def _load() -> dict:
    return json.loads(_DICT_PATH.read_text(encoding="utf-8"))


ROLES = _load()
ROLE_KEYS: List[str] = list(ROLES)

_COMPANIES = [
    "продуктовая команда онлайн-сервиса",
    "региональная ИТ-компания",
    "команда внутренней платформы",
    "разработчик решений для бизнеса",
    "финтех-проект",
    "команда цифровых продуктов",
]
_OUTCOMES = [
    "сокращение времени ручной проверки типовых задач",
    "снижение числа повторных ошибок после релиза",
    "упрощение поддержки для соседних команд",
    "ускорение обработки регулярных запросов",
    "добавление проверок для критичных сценариев",
    "подготовка документации для передачи проекта",
]
_WORK_FORMATS = ["гибридный график", "удалённая работа", "работа в офисе"]
_CITIES = [
    "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург",
    "Казань", "Нижний Новгород", "Самара", "Томск", "Пермь",
    "Красноярск", "Омск", "Воронеж",
]
_SURFACE_FORMS = {
    "Python": "Python 3",
    "PostgreSQL": "Postgres",
    "Kubernetes": "k8s",
    "JavaScript": "JS",
    "TypeScript": "TS",
}
_TEAM_CONTEXT = [
    "В команде есть аналитик, разработчики и специалист по тестированию; задачи проходят обычный цикл планирования и ревью.",
    "Продукт уже используется, поэтому важны аккуратные изменения, понятные проверки и поддержка существующих решений.",
    "Работа включает новые задачи и сопровождение действующей системы; решения обсуждаются с соседними командами.",
]
_RESUME_SUMMARY = [
    "Ищу команду с понятными задачами и возможностью отвечать за результат от идеи до запуска.",
    "Есть опыт работы над действующим продуктом с учётом сроков, качества и обратной связи пользователей.",
    "Предпочитаю разбирать причины проблем и оставлять после изменений понятные проверки и документацию.",
]
_COOPERATION = [
    "В проектах: согласование изменений с командой, проверка результата после выпуска и описание сложных случаев для коллег.",
    "Работа включала обсуждение решений с соседними командами и разбор ошибок после релизов.",
    "Для передачи задач поддерживались короткие инструкции, проверки и история принятых решений.",
]


def _years_word(years: int) -> str:
    return "год" if years == 1 else "года" if years in (2, 3, 4) else "лет"


def _surface(skill: str, rng: random.Random) -> str:
    alias = _SURFACE_FORMS.get(skill)
    return alias if alias and rng.random() < 0.3 else skill


def _skill_line(skills: Sequence[str], rng: random.Random) -> str:
    """Break a stack into short phrases instead of one giant keyword list."""
    items = [_surface(skill, rng) for skill in skills]
    rng.shuffle(items)
    if len(items) <= 3:
        return ", ".join(items)
    cut = max(2, len(items) // 2)
    return f"{', '.join(items[:cut])}; также {', '.join(items[cut:])}"


def render_vacancy(
    profession: str,
    skills: Sequence[str],
    rng: random.Random,
    *,
    optional_skills: Sequence[str] = (),
    critical_skills: Sequence[str] = (),
    required_years: int = 2,
) -> str:
    role = ROLES[profession]
    tasks = rng.sample(role["vacancy_subjects"], k=2)
    context = rng.choice(role["project_contexts"])
    company = rng.choice(_COMPANIES)
    conditions = rng.choice(_WORK_FORMATS)
    stack = _skill_line([skill for skill in skills if skill not in critical_skills], rng)
    must_have = ", ".join(_surface(skill, rng) for skill in critical_skills)
    bonus = (f"Будет плюсом опыт с {', '.join(_surface(skill, rng) for skill in optional_skills)}.\n"
             if optional_skills else "")
    intro = rng.choice([
        f"Мы — {company}. Ищем специалиста в команду продукта.",
        f"{company.capitalize()} расширяет команду и ищет коллегу.",
        "Команда развивает действующий сервис и открыла новую позицию.",
    ])
    return (
        f"Вакансия: {profession}\n"
        f"{intro} {context} {rng.choice(_TEAM_CONTEXT)}\n\n"
        f"Задачи:\n- {tasks[0]};\n- {tasks[1]};\n"
        "- обсуждать решения с разработчиками, аналитиками и владельцем продукта;\n"
        "- оценивать изменения перед релизом и помогать с их сопровождением.\n\n"
        f"Требования:\n- коммерческий опыт от {required_years} "
        f"{'года' if required_years == 1 else 'лет'};\n"
        f"- уверенная работа с {must_have};\n"
        f"- практический опыт: {stack}.\n"
        f"{bonus}\n"
        f"Условия: {conditions}, задачи с понятным владельцем и регулярное код-ревью. "
        "При отклике полезно коротко описать проект, за который отвечали лично."
    )


def render_resume(
    profession: str,
    skills: Sequence[str],
    rng: random.Random,
    faker,
    *,
    years: int = 3,
    familiar_skills: Sequence[str] = (),
) -> str:
    role = ROLES[profession]
    tasks = rng.sample(role["resume_subjects"], k=2)
    context = rng.choice(role["project_contexts"])
    company = rng.choice(_COMPANIES)
    outcome = rng.choice(_OUTCOMES)
    city = rng.choice(_CITIES)
    name = faker.name()
    headline = rng.choice(["Желаемая должность", "Специализация", "Позиция"])
    if years == 0:
        career = (
            "Опыт: учебные и стажировочные проекты.\n"
            f"{REFERENCE_YEAR - 1}–{REFERENCE_YEAR}: стажировка в команде продукта.\n"
            f"- {tasks[0]};\n- {tasks[1]}."
        )
    else:
        current_years = min(years, rng.randint(1, max(1, min(years, 4))))
        start = REFERENCE_YEAR - current_years
        previous = (
            f"\n{REFERENCE_YEAR - years}–{start}: участие в проектах другой команды.\n"
            f"- {tasks[1]}."
            if years > current_years else ""
        )
        career = (
            f"Опыт работы: {years} {_years_word(years)}.\n"
            f"{start}–{REFERENCE_YEAR}: {company}, {profession}.\n"
            f"- {tasks[0]};\n- {outcome}.{previous}"
        )
    listed = [_surface(skill, rng) for skill in skills]
    rng.shuffle(listed)
    if listed:
        split = max(1, len(listed) // 2)
        used = f"Инструменты в рабочих проектах: {', '.join(listed[:split])}.\n"
        skills_block = (f"Ключевые навыки: {', '.join(listed[split:])}.\n"
                        if listed[split:] else "")
    else:
        used = skills_block = ""
    familiar = (
        f"Дополнительно изучены: {', '.join(_surface(skill, rng) for skill in familiar_skills)}; "
        "практического применения пока не было.\n"
        if familiar_skills else ""
    )
    education = rng.choice([
        "Высшее техническое образование.",
        "Высшее образование, профильные курсы.",
        "Профильное образование и самостоятельные проекты.",
    ])
    return (
        f"{name}\n{headline}: {profession}\nГород: {city}\n\n"
        f"О себе: {rng.choice(_RESUME_SUMMARY)}\n\n"
        f"{career}\n"
        f"Один из проектов: {context}\n"
        f"{rng.choice(_COOPERATION)}\n\n"
        f"{used}{skills_block}{familiar}"
        f"Образование: {education}\n"
        f"Формат работы: {rng.choice(_WORK_FORMATS)}. "
        "Готов обсуждать задачи, где можно развивать профильную экспертизу."
    )
