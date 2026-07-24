"""Skill extraction and matching against the ontology.

The ontology (``skills_dict.SKILLS`` + ``RAW_SKILLS``) is compiled once into a
lookup table that maps a *normalized* surface form to one or more canonical
skills. Two matchers run over each text:

* **Lemma matcher** — for letter/space aliases. Both alias and text are run
  through the same normalization pipeline, then uni- and bi-grams of the text
  are looked up. This handles inflection ("разработке"->"разработка") and
  multi-word skills ("машинное обучение", "machine learning").
* **Raw matcher** — for symbol-bearing skills (``C++``, ``.NET``). Matched as
  word-boundary-aware substrings of the lower-cased original text, because
  ``razdel``/``pymorphy3`` destroy their punctuation.
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Set, Tuple

from .normalize import lemmatize_tokens, tokenize_words
from .skills_dict import RAW_SKILLS_ALL, SKILLS_ALL


def _raw_pattern(alias: str) -> re.Pattern:
    """Compile a word-boundary-aware regex for a raw alias."""
    # Boundaries: not preceded/followed by a word char or a dot, so ".net" does
    # not match inside "network" and "c++" does not match inside "c++++".
    return re.compile(rf"(?<![\w.]){re.escape(alias)}(?![\w.])")


def build_skill_index(
    skills: Dict[str, list] = None, raw_skills: Dict[str, list] = None
) -> Tuple[Dict[str, Set[str]], Dict[str, re.Pattern]]:
    """Compile the ontology into lookup tables.

    Returns ``(lemma_index, raw_index)``:

    * ``lemma_index`` — normalized surface form -> set of canonical skills.
    * ``raw_index``  — compiled regex -> canonical skill (for symbol skills).
    """
    skills = SKILLS_ALL if skills is None else skills
    raw_skills = RAW_SKILLS_ALL if raw_skills is None else raw_skills

    lemma_index: Dict[str, Set[str]] = {}
    for canonical, aliases in skills.items():
        for alias in aliases:
            norm = " ".join(lemmatize_tokens(tokenize_words(alias)))
            if not norm:
                continue
            lemma_index.setdefault(norm, set()).add(canonical)

    raw_index: Dict[re.Pattern, str] = {}
    for canonical, aliases in raw_skills.items():
        for alias in aliases:
            raw_index[_raw_pattern(alias.lower())] = canonical
    return lemma_index, raw_index


# Lazy module-level singletons — built on first use, reused afterwards.
_lemma_index: Dict[str, Set[str]] | None = None
_raw_index: Dict[re.Pattern, str] | None = None


def _indices():
    global _lemma_index, _raw_index
    if _lemma_index is None:
        _lemma_index, _raw_index = build_skill_index()
    return _lemma_index, _raw_index


def extract_skills(text: str) -> Set[str]:
    """Return the set of canonical skills found in *text*."""
    lemma_index, raw_index = _indices()

    lemmas = lemmatize_tokens(tokenize_words(text))
    grams = set(lemmas)
    grams.update(" ".join(pair) for pair in zip(lemmas, lemmas[1:]))

    found: Set[str] = set()
    for gram in grams:
        canon = lemma_index.get(gram)
        if canon:
            found.update(canon)

    low = (text or "").lower()
    for pattern, canonical in raw_index.items():
        if pattern.search(low):
            found.add(canonical)
    return found


def match_skills(
    resume_text: str,
    vacancy_text: str,
    vacancy_skills: Optional[Set[str]] = None,
) -> dict:
    """Compare skills extracted from a resume against those required by a vacancy.

    Returns a dict with ``matched``, ``missing``, ``keyword_score``
    (share of required skills present, in ``[0, 1]``), plus the raw sets.

    *vacancy_skills* lets a caller that scores many resumes against one vacancy
    pass the vacancy's skill set in once (see ``rank_candidates``) instead of
    re-extracting it on every call.
    """
    v_skills = vacancy_skills if vacancy_skills is not None else extract_skills(vacancy_text)
    r_skills = extract_skills(resume_text)
    matched = v_skills & r_skills
    missing = v_skills - r_skills
    keyword_score = len(matched) / len(v_skills) if v_skills else 0.0
    return {
        "matched": matched,
        "missing": missing,
        "keyword_score": keyword_score,
        "vacancy_skills": v_skills,
        "resume_skills": r_skills,
    }
