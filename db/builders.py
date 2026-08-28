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
    return _join(
        item.get("title"),
        item.get("specialization"),
        item.get("experience"),
        item.get("skills"),
        item.get("tags"),
    )
_YEARS_RE = re.compile(r"опыт\s+работы:\s*(\d+)\s*(?:лет|год|года)", re.IGNORECASE)


def experience_years(item: dict) -> Optional[int]:
    """Total years of experience parsed from the resume ``experience`` text.

    Returns ``None`` when no figure is found. Used **only as a tie-breaker**
    among equal-score candidates — it never enters the score itself, which stays
    an absolute skill/text measure (see ``scorer.scoring``).
    """
    text = _as_str(item.get("experience"))
    m = _YEARS_RE.search(text)
    return int(m.group(1)) if m else None

def parse_raw_text_to_resume(raw_text: str) -> dict:
    logger.info(f"Начинаем парсинг текста, длина: {len(raw_text)} символов")
    experience_text = ""
    match = _YEARS_RE.search(raw_text)
    if match:
        experience_text = match.group(0)
        logger.info(f"Найден опыт: '{experience_text}'")
    else:
        logger.warning("Опыт работы не найден в тексте")
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
            logger.info(f"Найдена должность: '{title}'")
            break
    else:
        title = ""
        logger.warning("Должность не найдена в тексте")
    
    skills = []
    skills_block_match = re.search(
        r"Ключевые навыки:\s*([^\n]+)",
        raw_text,
        re.IGNORECASE
    )
    
    if skills_block_match:
        skills_raw = skills_block_match.group(1)
        
        if ',' in skills_raw:
            skills = [s.strip() for s in skills_raw.split(',') if s.strip()]
        else:
            words = skills_raw.split()
            stop_words = {'опыт', 'работы', 'ключевые', 'навыки', 'технологии', 'стек'}
            for word in words:
                cleaned = word.strip('.,!?;:')
                if len(cleaned) > 2 and cleaned.lower() not in stop_words:
                    skills.append(cleaned)
        
        logger.info(f"Найдено навыков: {len(skills)}")
        if len(skills) > 0:
            preview = ', '.join(skills[:5])
            if len(skills) > 5:
                preview += f'... (всего {len(skills)})'
            logger.info(f" Навыки: {preview}")
    else:
        logger.warning("Блок 'Ключевые навыки' не найден")
    logger.info(
        f"Распаршено резюме: должность='{title}', "
        f"навыков={len(skills)}, "
        f"опыт='{experience_text}'"
    )
    
    return {
        "title": title if title else "Кандидат",
        "specialization": "",
        "experience": experience_text,
        "skills": skills,
        "tags": skills,
    }
