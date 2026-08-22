import re
from typing import Any, Iterable, Optional

_YEARS_RE = re.compile(r"опыт\s+работы:?\s*(\d+)\s*(?:лет|год|года)", re.IGNORECASE)


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(v).strip() for v in value if v)
    return str(value).strip()


def _join(*parts: Iterable[Optional[Any]]) -> str:
    pieces = [_as_str(p) for p in parts]
    return " ".join(p for p in pieces if p)


def vacancy_text(item: dict) -> str:
    return _join(item.get("title"), item.get("description"), item.get("skills"), item.get("tags"))


def resume_text(item: dict) -> str:
    return _join(
        item.get("title"),
        item.get("specialization"),
        item.get("experience"),
        item.get("skills"),
        item.get("tags"),
    )


def experience_years(item: dict) -> Optional[int]:
    text = _as_str(item.get("experience"))
    m = _YEARS_RE.search(text)
    return int(m.group(1)) if m else None


def parse_raw_text_to_resume(raw_text: str) -> dict:
    experience_text = ""
    match = _YEARS_RE.search(raw_text)
    if match:
        experience_text = match.group(0)

    return {
        "title": "Кандидат",
        "specialization": "",
        "experience": experience_text,
        "skills": [],
        "tags": [],
    }