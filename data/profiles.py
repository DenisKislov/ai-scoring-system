"""Role profiles, loaded from ``skills_by_profession.json``.

The JSON is the single source of truth for which skills belong to each
profession (extend it freely). Each profession carries:

* ``skills`` — canonical skills a practitioner of this profession realistically
  has (all are aliases the scorer ontology recognizes);
* ``vacancy_subjects`` / ``resume_subjects`` — domain phrases used to render
  realistic Russian vacancy/resume text.
"""
from __future__ import annotations

import json
import os
import random
from typing import List

_DICT_PATH = os.path.join(os.path.dirname(__file__), "skills_by_profession.json")


def _load() -> dict:
    with open(_DICT_PATH, encoding="utf-8") as handle:
        return json.load(handle)


# profession -> {skills, vacancy_subjects, resume_subjects}
ROLES = _load()
ROLE_KEYS: List[str] = list(ROLES.keys())

# Расширенный список бонусных фраз для реалистичности
_BONUS_PHRASES = [
    "опыт работы с микросервисами",
    "понимание принципов ООП",
    "навыки командной работы",
    "опыт менторства",
    "знание алгоритмов и структур данных",
    "опыт работы в Agile/Scrum командах",
    "навыки оптимизации производительности",
    "опыт написания технической документации",
    "знание принципов CI/CD",
    "опыт работы с облачными сервисами (AWS, GCP, Azure)",
]

# Варианты уровней английского
_ENGLISH_LEVELS = ["A2 (Pre-Intermediate)", "B1 (Intermediate)", "B2 (Upper-Intermediate)", "C1 (Advanced)"]

# Университеты для реалистичности
_UNIVERSITIES = ["НГУ", "СПбГУ", "МГУ им. М.В. Ломоносова", "ИТМО", "ВШЭ", "МФТИ", "УрФУ"]


def render_vacancy(profession: str, skills: List[str], rng: random.Random) -> str:
    """Render a vacancy text for *profession* listing *skills* as requirements."""
    role = ROLES[profession]
    subject = rng.choice(role["vacancy_subjects"])
    years = rng.randint(1, 5)
    bonus = rng.choice(_BONUS_PHRASES)
    
    return (
        f"Вакансия: {profession}.\n"
        f"Требуемый опыт работы: от {years} лет.\n"
        f"Мы ищем специалиста для решения задач: {subject}.\n\n"
        f"Обязанности:\n"
        f"- {subject};\n"
        f"- участие в проектировании архитектуры и ревью кода;\n"
        f"- взаимодействие с продуктовой командой.\n\n"
        f"Требования к кандидату:\n"
        f"- уверенное владение технологиями: {', '.join(skills)}.\n"
        f"- {bonus.capitalize()}."
    )


def render_resume(profession: str, skills: List[str], rng: random.Random, faker) -> str:
    """Render a detailed, realistic resume text for *profession*."""
    role = ROLES[profession]
    subject = rng.choice(role["resume_subjects"])
    years = rng.randint(1, 10)
    
    # Генерация реалистичных деталей
    company = rng.choice(["ООО 'ТехноСофт'", "АО 'ИнфоСистемы'", "Яндекс", "Сбер", "Тинькофф", "Ozon"])
    university = rng.choice(_UNIVERSITIES)
    grad_year = rng.randint(2015, 2022)
    english = rng.choice(_ENGLISH_LEVELS)
    salary = rng.choice([100, 150, 200, 250, 300, 350])
    
    # Конкретные достижения в зависимости от профессии
    achievements = [
        "разработка и поддержка высоконагруженных сервисов",
        "оптимизация SQL-запросов и ускорение работы приложений",
        "внедрение автоматизированного тестирования (покрытие выросло до 80%)",
        "участие в миграции монолита на микросервисную архитектуру",
        "настройка CI/CD пайплайнов и автоматизация деплоя"
    ]
    achievement = rng.choice(achievements)

    return (
        f"{faker.name()}, позиция: {profession}.\n"
        f"Город: {faker.city()}.\n"
        f"Зарплатные ожидания: от {salary} 000 руб. на руки.\n\n"
        f"Опыт работы: {years} лет.\n"
        f"2022 — настоящее время ({rng.randint(1, 4)} года)\n"
        f"{company}\n"
        f"{profession}\n"
        f"Обязанности и достижения:\n"
        f"— {subject};\n"
        f"— {achievement};\n"
        f"— работа в команде, code review, менторство.\n\n"
        f"Ключевые навыки: {', '.join(skills)}\n\n"
        f"Образование:\n"
        f"{grad_year} г., {university}, высшее образование.\n\n"
        f"Дополнительная информация:\n"
        f"— Уровень английского: {english}\n"
        f"— Готовность к удалённой работе или релокации."
    )