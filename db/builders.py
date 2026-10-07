"""Build scorer input text from hh.ru-shaped items."""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Optional

# Вызываем парсер куратора из api.nlp_parser
from api.nlp_parser import extract_smart_skills

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
    """Total years of experience parsed from the resume experience text."""
    text = _as_str(item.get("experience"))
    m = _YEARS_RE.search(text)
    return int(m.group(1)) if m else None


def parse_raw_text_to_resume(raw_text: str):
    if not raw_text or len(raw_text.strip()) == 0:
        logger.warning("WARN: Получен пустой текст для парсинга (вероятно пустой файл)")
        return {
            "title": "Кандидат",
            "specialization": "",
            "experience": "",
            "skills": [],
            "tags": [],
        }

    logger.info(f"INFO: Начинаем парсинг текста, длина: {len(raw_text)} символов")

    experience_text = ""
    match = _YEARS_RE.search(raw_text)
    if match:
        experience_text = match.group(0)
    else:
        logger.warning("WARN: Опыт работы не найден в тексте")

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
    # ИСПОЛЬЗУЕМ СЛОВАРНЫЙ ПАРСЕР КУРАТОРА
    # -----------------------------------------------------------------------
    logger.info("INFO: [VocabExtractor] Запуск извлечения навыков")
    skills = extract_smart_skills(raw_text)

    if skills:
        logger.info(f"INFO: Извлечено навыков ({len(skills)} шт.): {', '.join(skills)}")
    else:
        logger.warning("WARN: Парсер не нашел ни одного навыка в тексте")

    logger.info(
        f"INFO: Распаршено резюме: должность='{title}', опыт='{experience_text}'"
    )

    return {
        "title": title if title else "Кандидат",
        "specialization": "",
        "experience": experience_text,
        "skills": skills,
        "tags": skills,
    }