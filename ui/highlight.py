"""Highlight matched skills inside resume text for Streamlit rendering.

Given a resume's raw text and the list of *canonical* matched skills, wrap every
occurrence of any of their surface aliases (from the ontology) in ``<mark>``.
Output is safe HTML: the text is HTML-escaped first, only matched spans get the
``<mark>`` tag, and newlines become ``<br>``.
"""
from __future__ import annotations

import html
import re
from typing import Iterable, List

from scorer.skills_dict import RAW_SKILLS_ALL, SKILLS_ALL


def _build_alias_map() -> dict:
    """canonical skill -> lower-cased surface forms (canonical + aliases)."""
    idx = {}
    for canon, aliases in SKILLS_ALL.items():
        idx[canon] = [canon.lower()] + [a.lower() for a in aliases]
    for canon, aliases in RAW_SKILLS_ALL.items():
        idx[canon] = [canon.lower()] + [a.lower() for a in aliases]
    return idx


_ALIASES = _build_alias_map()


def highlight_skills(text: str, skills: Iterable[str]) -> str:
    """Return safe HTML of *text* with skill aliases highlighted."""
    if not text:
        return ""

    forms = []
    for s in skills:
        forms.extend(_ALIASES.get(s, [s.lower()]))
    forms = sorted({f for f in forms if f}, key=len, reverse=True)

    if not forms:
        return html.escape(text).replace("\n", "<br>")

    pattern = re.compile("(" + "|".join(re.escape(f) for f in forms) + ")", re.IGNORECASE)

    out: List[str] = []
    last = 0
    for m in pattern.finditer(text):
        out.append(html.escape(text[last:m.start()]))
        out.append(f'<mark style="background:#fff3a0">{html.escape(m.group(0))}</mark>')
        last = m.end()
    out.append(html.escape(text[last:]))
    return "".join(out).replace("\n", "<br>")
