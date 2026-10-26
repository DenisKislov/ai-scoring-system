"""Извлечение и сопоставление навыков по онтологии.

Онтологию (``skills_dict.SKILLS`` + ``RAW_SKILLS`` + внешние CSV/JSON разметки)
компилирует в единый список для ``SkillExtractor``.

Поддерживает разделение навыков на критические (must-have) и обычные (nice-to-have).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
import re
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

import pandas as pd

from .normalize import lemmatize_tokens, tokenize_words
from .skill_extractor import SkillExtractor, collapse_case
from .skill_families import family_satisfied
from .skills_dict import RAW_SKILLS_ALL, SKILLS_ALL
from . import dictionary
from .config import load_config
from .privacy import professional_text

CRITICAL_WEIGHT = load_config()["critical_weight"]

# Навыки, которые экстрактор обязан распознавать, даже если они в BLACKLIST.
# Список эмпирический (data/superjob_dataset.json + data/dataset_resume.json,
# 201 документ): для каждого залайкленного терминами BLACKLIST ярлыка ground
# truth посчитано, сколько TP даёт его распознавание против сколько FP оно
# приносит в документах, где разметка его не содержит. Чистый плюс только у
# этих трёх; «тестирование» (5 TP / 24 FP), «api» (18/37), «разработка»
# (1/113) и пр. оставлены в чёрном списке — их распознавание портит точность.
PROTECTED_SKILLS = {"ООП", "КОМПАС", "Стратегия"}


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


def _get_project_root() -> Path:
    current = Path(__file__).resolve().parent
    for parent in [current, current.parent, current.parent.parent]:
        if (parent / "data").exists() or (parent / "scripts").exists():
            return parent
    return current.parent


def _load_unified_taxonomy() -> List[str]:
    """Собирает единый словарь навыков из всех источников проекта."""
    skills: Set[str] = set()

    # 1. Базовые навыки скорера
    lemma_idx, raw_idx = _indices()
    for v in lemma_idx.values():
        skills.update(v)
    for v in raw_idx.values():
        skills.add(v)

    # Evaluation annotations are never a source of production vocabulary.
    skills.update(dictionary.entries())

    # 4. Базовый профиль навыков для продаж и недвижимости (fallback)
    extra_sales_skills = {
        "Поиск и привлечение клиентов", "Телефонные переговоры",
        "Навыки переговоров", "B2B Продажи", "B2B продажи", "В2В Продажи",
        "Прямые продажи", "Консультирование клиентов",
        "Клиентоориентированность", "Деловая переписка",
        "Холодные звонки", "Заключение договоров", "Работа с возражениями"
    }
    skills.update(extra_sales_skills)

    return sorted(list(skills))


_EXTRACTOR_INSTANCE: SkillExtractor | None = None
_EXTRACTOR_SIGNATURE = None


def _get_extractor() -> SkillExtractor:
    global _EXTRACTOR_INSTANCE, _EXTRACTOR_SIGNATURE
    signature = dictionary.signature()
    if _EXTRACTOR_INSTANCE is None or signature != _EXTRACTOR_SIGNATURE:
        taxonomy = _load_unified_taxonomy()
        _EXTRACTOR_INSTANCE = SkillExtractor(
            taxonomy=taxonomy, protected=PROTECTED_SKILLS | set(dictionary.entries()),
            aliases=dictionary.entries())
        _EXTRACTOR_SIGNATURE = signature
        _normalized_skill.cache_clear()
    return _EXTRACTOR_INSTANCE


def extract_skills(text: str) -> Set[str]:
    """Возвращает множество канонических навыков, найденных в *text*."""
    if not text or not text.strip():
        return set()

    extractor = _get_extractor()
    return normalize_skill_set(extractor.extract(professional_text(text)))


@lru_cache(maxsize=200_000)
def _normalized_skill(skill: str, dictionary_signature: tuple) -> FrozenSet[str]:
    """Канонические имена одного навыка.

    Кэшируется: матчинг вызывает нормализацию одних и тех же навыков тысячи
    раз (по разу на каждую пару вакансия×кандидат) — без кэша это ~1800
    regex-проверок на навык и минуты на пул из 100 резюме.
    """
    lemma_index, raw_index = _indices()

    canonical = dictionary.canonical(skill)
    if canonical != skill or canonical in dictionary.entries():
        return frozenset({canonical})
    low_skill = skill.lower()
    for pattern, canonical in raw_index.items():
        if pattern.search(low_skill):
            return frozenset({canonical})

    lemmas = lemmatize_tokens(tokenize_words(skill))
    if not lemmas:
        return frozenset()

    gram = " ".join(lemmas)
    canon = lemma_index.get(gram)
    if canon:
        # онтология даёт 2-3 написания одного навыка — оставляем одно,
        # детерминированно (иначе имена «пляшут» от хэш-сида процесса)
        return frozenset(collapse_case(canon))
    return frozenset({skill})


def normalize_skill_set(raw_skills_set: Set[str]) -> Set[str]:
    """Приводит любое сырое множество навыков к каноническим ключам из онтологии."""
    if not raw_skills_set:
        return set()

    normalized: Set[str] = set()
    signature = dictionary.signature()
    for skill in raw_skills_set:
        normalized.update(_normalized_skill(skill, signature))
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

    # Направленное сопоставление: требование «SQL» закрывается резюме с MySQL,
    # «Machine Learning» — scikit-learn/PyTorch, и т.д. (см. skill_families).
    for v_skill in v_skills - matched:
        if family_satisfied(v_skill, r_skills):
            matched.add(v_skill)

    missing = v_skills - matched

    crit = critical_skills or set()
    crit = normalize_skill_set(crit) & v_skills

    matched_critical = matched & crit
    missing_critical = crit - matched

    if crit:
        critical_weight = load_config()["critical_weight"]
        total_weight = 0.0
        got_weight = 0.0
        for skill in v_skills:
            w = critical_weight if skill in crit else 1.0
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
