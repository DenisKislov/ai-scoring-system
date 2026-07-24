"""Role profiles, loaded from ``skills_by_profession.json``.

The JSON is the single source of truth for which skills belong to each
profession (extend it freely). Each profession carries:

* ``skills`` — canonical skills a practitioner of this profession realistically
  has (all are aliases the scorer ontology recognizes);
* ``vacancy_subjects`` / ``resume_subjects`` — domain phrases used to render
  realistic Russian vacancy/resume text.

The profession key (e.g. "Computer Vision Engineer") doubles as the human
title shown in the UI table.
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

_BONUS_PHRASES = [
    "опыт работы с микросервисами",
    "понимание принципов ООП",
    "навыки командной работы",
    "опыт менторства",
    "знание алгоритмов и структур данных",
]


def render_vacancy(profession: str, skills: List[str], rng: random.Random) -> str:
    """Render a vacancy text for *profession* listing *skills* as requirements."""
    role = ROLES[profession]
    subject = rng.choice(role["vacancy_subjects"])
    years = rng.randint(1, 5)
    bonus = rng.choice(_BONUS_PHRASES)
    return (
        f"Вакансия: {profession}.\n"
        f"Требуемый опыт работы: от {years} лет.\n"
        f"Мы ищем специалиста для задач: {subject}.\n"
        f"Обязанности:\n- {subject};\n- участие в проектировании архитектуры, ревью кода.\n"
        f"Требования к кандидату:\n- уверенное владение технологиями: {', '.join(skills)}.\n"
        f"Будет плюсом: {bonus}."
    )


def render_resume(profession: str, skills: List[str], rng: random.Random, faker) -> str:
    """Render a resume text for *profession* listing *skills* as the stack."""
    role = ROLES[profession]
    subject = rng.choice(role["resume_subjects"])
    return (
        f"{faker.name()}, позиция: {profession}.\n"
        f"Опыт работы: {rng.randint(1, 10)} лет. Город: {faker.city()}.\n"
        f"Сфера деятельности: {subject}.\n"
        f"Технологии и навыки: {', '.join(skills)}.\n"
        f"Обязанности на последнем месте работы: {subject}, работа в команде.\n"
        f"Образование: высшее."
    )
