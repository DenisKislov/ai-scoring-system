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


# "Опыт работы: N лет|год|года" — the phrasing the synthetic renderer and the
# hh.ru free-text both use. Generalizes Parser/extract_years_of_experience.py
# so the live (MongoDB) pipeline can derive the same figure.
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
