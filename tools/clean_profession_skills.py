"""Normalize and clean ``data/skills_by_profession.json`` in place.

Two problems with the hand-assembled corpus:

1. It was saved as a **Python dict literal** (single quotes) instead of valid
   JSON, so ``data.profiles`` (which does ``json.load``) crashed on import and
   took the whole synthetic/seed/eval pipeline down with it.
2. The profession skill lists were scraped from hh.ru and contain **exact
   duplicates** (case/whitespace variants of the same tag) and a few clearly
   **wrong-profession tags** (e.g. visual-design tools inside Data Scientist)
   that pollute both realism and the ``true_relevance`` denominator.

This tool is **idempotent**: it accepts either a valid JSON file or a Python
literal, applies the same cleaning, and writes back canonical UTF-8 JSON. Safe
to re-run.

CLI: ``python -m tools.clean_profession_skills``
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Dict, List

_PATH = Path(__file__).resolve().parent.parent / "data" / "skills_by_profession.json"

# Tags that are unambiguously *visual / UI design* and therefore wrong inside
# a Data Scientist skill set (the only profession list we curate manually —
# the rest are left intact to avoid subjective pruning).
_DS_DESIGN_NOISE = {
    "Figma", "Tilda", "Web-дизайн", "Usability", "Дизайн-ревью",
    "Adobe Illustrator", "Прототипирование", "Создание дизайн-системы",
}


def _load(path: Path) -> Dict[str, dict]:
    """Load the corpus whether it is valid JSON or a Python literal."""
    src = path.read_text(encoding="utf-8")
    try:
        return json.loads(src)
    except json.JSONDecodeError:
        # Legacy single-quoted form -> evaluate as a Python literal.
        return ast.literal_eval(src)


def _dedup(skills: List[str]) -> List[str]:
    """Drop exact duplicates, keeping the first (nicest-cased) occurrence.

    Comparison key is lower-cased with collapsed whitespace, so ``AirFlow`` and
    ``Airflow`` collapse to one entry while genuinely different tags survive.
    """
    seen: set[str] = set()
    out: List[str] = []
    for s in skills:
        key = " ".join(s.lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(" ".join(s.split()))  # normalize internal whitespace
    return out


def clean(data: Dict[str, dict]) -> Dict[str, dict]:
    for profession, info in data.items():
        skills: List[str] = list(info.get("skills", []))
        if profession == "Data Scientist":
            skills = [s for s in skills if s not in _DS_DESIGN_NOISE]
        info["skills"] = _dedup(skills)
    return data


def main() -> int:
    data = _load(_PATH)
    before = {p: len(i.get("skills", [])) for p, i in data.items()}
    data = clean(data)
    after = {p: len(i.get("skills", [])) for p, i in data.items()}

    _PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {_PATH}")
    for p in data:
        removed = before[p] - after[p]
        print(f"  {p:<24} {before[p]:>3} -> {after[p]:>3}  ({removed} dropped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
