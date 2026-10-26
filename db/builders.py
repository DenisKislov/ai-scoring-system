"""Build scorer input text from hh.ru-shaped items.

The Scrapy spider (and the synthetic seeder) store documents in the hh.ru item
shape. These helpers flatten a document into a single text string suitable for
``calculate_score`` / ``rank_candidates``:

* vacancy  -> title + description + required skills
* resume   -> title + specialization + experience + skills + tags

Resume ``skills`` are often empty without an employer login on hh.ru, so the
resume text leans on ``experience`` and ``specialization`` — the free-text
fields that are always present. Field values may be ``str``, ``list``, or
``None``; everything is normalized defensively.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional
import logging

# Единый фасад извлечения навыков через SkillExtractor
from scorer import extract_skills

# Робастный парсер опыта: покрывает форматы реальных резюме SuperJob/PDF
# («2 года и 1 месяц», «Стаж 10 лет», периоды «апрель 2021 — настоящее
# время»), которые старый регэксп «опыт работы: N лет» не замечал.
from api.nlp_parser import extract_experience_years, format_experience

logger = logging.getLogger("db.builders")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)


def _as_str(value: Any) -> str:
    """Flatten a str / list-of-str / None into a single trimmed string."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(v).strip() for v in value if v)
    return str(value).strip()


def _join(*parts: Iterable[Optional[Any]]) -> str:
    pieces = [_as_str(p) for p in parts]
    return " ".join(p for p in pieces if p)


def vacancy_text(item: dict) -> str:
    """Text representation of a vacancy item for the scorer."""
    return _join(item.get("title"), item.get("description"), item.get("skills"), item.get("tags"))


def resume_text(item: dict) -> str:
    """Text representation of a resume item for the scorer."""
    if item.get("_raw_text") is not None:
        return item["_raw_text"]
    return _join(
        item.get("title"),
        item.get("specialization"),
        item.get("experience"),
        item.get("skills"),
        item.get("tags"),
    )


def experience_years(item: dict) -> Optional[float]:
    """Годы опыта из резюме; ``None``, когда текст об опыте молчит.

    Сначала берётся готовое числовое поле ``experience_years`` (его кладёт
    парсер при загрузке), затем поле ``experience``, затем полный текст
    ``_raw_text`` (периоды работы в нём видны даже когда поле опыта пусто).

    Используется **только как тай-брейк** при равном Score — в сам скор
    опыт не входит (см. ``scorer.scoring``).
    """
    pre = item.get("experience_years")
    if pre is not None:
        try:
            return float(pre)
        except (TypeError, ValueError):
            pass

    for key in ("experience", "_raw_text"):
        years = extract_experience_years(_as_str(item.get(key)))
        if years is not None:
            return years
    return None


def parse_raw_text_to_resume(raw_text: str):
    if not raw_text or len(raw_text.strip()) == 0:
        logger.warning("WARN: Получен пустой текст для парсинга (вероятно пустой файл)")
        return {
            "title": "Кандидат",
            "specialization": "",
            "experience": "",
            "experience_years": None,
            "skills": [],
            "tags": [],
        }

    logger.info(f"INFO: Начинаем парсинг текста, длина: {len(raw_text)} символов")

    years = extract_experience_years(raw_text)
    if years is None:
        experience_text = ""
        logger.warning("WARN: Опыт работы не найден в тексте")
    else:
        experience_text = ("Без опыта" if years == 0
                           else f"Опыт работы: {format_experience(years)}")

    title = ""
    title_patterns = [
        r"Должность:\s*([^,;.\n]+)",
        r"Профессия:\s*([^,;.\n]+)",
        r"Специализация:\s*([^,;.\n]+)",
    ]
    for pattern in title_patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            title = match.group(1).strip()
            break
    else:
        title = ""
        logger.warning("WARN: Должность не найдена в тексте")

    # -----------------------------------------------------------------------
    # ИСПОЛЬЗУЕМ ОБНОВЛЕННЫЙ SKILL EXTRACTOR
    # -----------------------------------------------------------------------
    logger.info("INFO: [SkillExtractor] Запуск извлечения навыков")
    skills = sorted(list(extract_skills(raw_text)))

    if skills:
        logger.info(f"INFO: Извлечено навыков ({len(skills)} шт.): {', '.join(skills)}")
    else:
        logger.warning("WARN: Парсер не нашел ни одного навыка в тексте")

    logger.info(
        f"INFO: Распаршено резюме: должность='{title}', "
        f"опыт='{experience_text}' ({years} лет)"
    )

    return {
        "title": title if title else "Кандидат",
        "specialization": "",
        "experience": experience_text,
        "experience_years": years,
        "skills": skills,
        "tags": skills,
    }