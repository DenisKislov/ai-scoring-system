"""Извлечение навыков через словарь API и сопоставление с онтологией скорера.

Критические (must-have) навыки учитываются с повышенным весом.
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Set, Tuple

from .normalize import lemmatize_tokens, tokenize_words
from .skills_dict import RAW_SKILLS_ALL, SKILLS_ALL

CRITICAL_WEIGHT = 2.0


def _raw_pattern(alias: str) -> re.Pattern:
    """Компилирует regex с учётом границ слов для сырого алиаса."""
    return re.compile(rf"(?<![\w.]){re.escape(alias)}(?![\w.])")


def build_skill_index(
    skills: Dict[str, list] = None,
    raw_skills: Dict[str, list] = None,
) -> Tuple[Dict[str, Set[str]], Dict[re.Pattern, str]]:
    """Компилирует онтологию в таблицы поиска."""
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


_lemma_index: Dict[str, Set[str]] | None = None
_raw_index: Dict[re.Pattern, str] | None = None


def _indices() -> Tuple[Dict[str, Set[str]], Dict[re.Pattern, str]]:
    """Возвращает (и при необходимости строит) индексы навыков."""
    global _lemma_index, _raw_index
    if _lemma_index is None:
        _lemma_index, _raw_index = build_skill_index()
    return _lemma_index, _raw_index


def extract_skills(text: str) -> Set[str]:
    """Возвращает множество канонических навыков."""
    if not text or not text.strip():
        return set()

    # Локальный импорт разрывает кольцевую зависимость
    from api.nlp_parser import extract_smart_skills
    raw_found = extract_smart_skills(text)

    # Приводим к каноническому регистру скорера (Python вместо python и т.д.)
    lemma_idx, raw_idx = _indices()
    canonical_map = {}

    for s_set in lemma_idx.values():
        for canon in s_set:
            canonical_map[canon.lower()] = canon

    for canon in raw_idx.values():
        canonical_map[canon.lower()] = canon

    result = set()
    for s in raw_found:
        s_low = s.lower()
        if s_low in canonical_map:
            result.add(canonical_map[s_low])
        else:
            result.add(s)

    return result

def normalize_skill_set(raw_skills_set: Set[str]) -> Set[str]:
    """Приводит любое сырое множество навыков к каноническим ключам из онтологии."""
    if not raw_skills_set:
        return set()

    lemma_index, raw_index = _indices()
    normalized = set()

    for skill in raw_skills_set:
        low_skill = skill.lower()
        found = False

        for pattern, canonical in raw_index.items():
            if pattern.search(low_skill):
                normalized.add(canonical)
                found = True
                break
        if found:
            continue

        lemmas = lemmatize_tokens(tokenize_words(skill))
        if not lemmas:
            continue

        gram = " ".join(lemmas)
        canon = lemma_index.get(gram)
        if canon:
            normalized.update(canon)
        else:
            normalized.add(skill)

    return normalized


def match_skills(
    resume_text: str,
    vacancy_text: str,
    vacancy_skills: Optional[Set[str]] = None,
    critical_skills: Optional[Set[str]] = None,
    resume_skills: Optional[Set[str]] = None,
) -> dict:
    """Сравнивает навыки резюме с навыками, требуемыми вакансией."""
    if vacancy_skills is not None:
        v_skills = normalize_skill_set(vacancy_skills)
    else:
        v_skills = extract_skills(vacancy_text)

    if resume_skills is not None:
        r_skills = normalize_skill_set(resume_skills)
    else:
        r_skills = extract_skills(resume_text)

    matched = v_skills & r_skills
    missing = v_skills - r_skills

    crit = critical_skills or set()
    crit = normalize_skill_set(crit) & v_skills

    matched_critical = matched & crit
    missing_critical = crit - matched

    if crit:
        total_weight = 0.0
        got_weight = 0.0
        for skill in v_skills:
            w = CRITICAL_WEIGHT if skill in crit else 1.0
            total_weight += w
            if skill in matched:
                got_weight += w
        keyword_score = got_weight / total_weight if total_weight > 0 else 0.0
    else:
        keyword_score = len(matched) / len(v_skills) if v_skills else 0.0

    return {
        "matched": matched,
        "missing": missing,
        "matched_critical": matched_critical,
        "missing_critical": missing_critical,
        "keyword_score": keyword_score,
        "vacancy_skills": v_skills,
        "resume_skills": r_skills,
        "critical_skills": crit,
    }
