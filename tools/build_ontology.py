"""Derive a scorer skill ontology from the profession corpus.

The hand-curated ``scorer/skills_dict.py`` (RU/EN aliases, ~60 skills) cannot
keep up with the real hh.ru vocabulary — a coverage check showed it recognizes
only ~43% of the tags in ``data/skills_by_profession.json``. This tool turns
that corpus into an **auto ontology** and writes it next to the curated one:

* ``scorer/skills_auto.json``      — letter/space aliases (matched on lemmas)
* ``scorer/skills_auto_raw.json``  — symbol-bearing aliases (matched as substrings)

Rules:

* Tags that are actually comma-joined lists (``"vue2, vue3, vuex"``) are split.
* Surface forms collapse to one canonical skill by a normalized key
  (lower-case, whitespace-collapsed); the nicest-cased form becomes canonical,
  the rest become aliases.
* A small ``MERGE`` map folds the few genuine duplicates the corpus carries in
  two spellings (``Airflow`` / ``Apache Airflow``).
* Anything already covered by the **curated** dictionary (by normalized key of
  canonical + aliases) is skipped, so curated RU/translit aliases always win.
* Digit/symbol-bearing keys go to the RAW table; pure-letter keys to the lemma
  table — exactly how ``scorer/skills.py`` splits the two match strategies.

CLI: ``python -m tools.build_ontology`` (writes the two JSON files, idempotent).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set

_ROOT = Path(__file__).resolve().parent.parent
_CORPUS = _ROOT / "data" / "skills_by_profession.json"
_OUT_SKILLS = _ROOT / "scorer" / "skills_auto.json"
_OUT_RAW = _ROOT / "scorer" / "skills_auto_raw.json"

# Fold these corpus spellings into one canonical skill (genuine duplicates).
MERGE: Dict[str, str] = {
    "airflow": "Apache Airflow",
    "apache airflow": "Apache Airflow",
    "kafka": "Apache Kafka",
    "apache kafka": "Apache Kafka",
}

_LETTER_RE = re.compile(r"^[a-zа-яё][a-zа-яё\s]*$")


def _normkey(tag: str) -> str:
    return re.sub(r"\s+", " ", tag.lower()).strip()


def _split_tag(tag: str) -> List[str]:
    """A tag that contains commas is really a list — split and trim it."""
    if "," in tag:
        return [p.strip() for p in tag.split(",") if p.strip()]
    return [tag.strip()]


def _best_form(forms: List[str]) -> str:
    """Pick the nicest surface form: prefer title-case, then longer."""
    def key(f: str):
        return (f == f.title(), sum(1 for c in f if c.isupper()), len(f))
    return max(forms, key=key)


def _curated_keys() -> Set[str]:
    """Normalized keys already recognized by the hand-curated dictionary."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_sd", _ROOT / "scorer" / "skills_dict.py"
    )
    sd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sd)  # type: ignore[arg-type]
    keys: Set[str] = set()
    for table in (sd.SKILLS, sd.RAW_SKILLS):
        for canon, aliases in table.items():
            keys.add(_normkey(canon))
            keys.update(_normkey(a) for a in aliases)
    return keys


def build() -> Dict[str, Dict[str, List[str]]]:
    corpus = json.loads(_CORPUS.read_text(encoding="utf-8"))
    curated = _curated_keys()

    # Group surface forms by normalized key. MERGE routes duplicate spellings
    # (e.g. "airflow" and "apache airflow") onto one shared group key.
    groups: Dict[str, List[str]] = defaultdict(list)
    merge_values = {_normkey(v) for v in MERGE.values()}
    for info in corpus.values():
        for tag in info.get("skills", []):
            for piece in _split_tag(tag):
                nk = _normkey(piece)
                if len(nk) < 2 or nk in curated:
                    continue
                gkey = _normkey(MERGE[nk]) if nk in MERGE else nk
                groups[gkey].append(piece)

    auto: Dict[str, List[str]] = {}
    for gkey, forms in groups.items():
        canonical = next(v for v in MERGE.values() if _normkey(v) == gkey) \
            if gkey in merge_values else _best_form(forms)
        aliases: List[str] = []
        seen: Set[str] = set()
        for f in [canonical, *forms]:
            nk = _normkey(f)
            if nk and nk not in seen:
                seen.add(nk)
                aliases.append(nk)
        auto[canonical] = aliases

    skills: Dict[str, List[str]] = {}
    raw: Dict[str, List[str]] = {}
    for canon, aliases in auto.items():
        key = _normkey(canon)
        bucket = skills if _LETTER_RE.match(key) else raw
        bucket[canon] = aliases
    return {"skills": skills, "raw": raw}


def main() -> int:
    out = build()
    _OUT_SKILLS.write_text(
        json.dumps(out["skills"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _OUT_RAW.write_text(
        json.dumps(out["raw"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {_OUT_SKILLS}  ({len(out['skills'])} letter skills)")
    print(f"Wrote {_OUT_RAW}   ({len(out['raw'])} symbol skills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
