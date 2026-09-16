"""Извлечение и сопоставление навыков по онтологии.

Онтологию (``skills_dict.SKILLS`` + ``RAW_SKILLS``) один раз компилирует
в таблицы поиска, которые отображают *нормализованную* поверхностную форму
на один или несколько канонических навыков. Над каждым текстом работают
два матчера:

* **Lemma-матчер** — для буквенно-пробельных алиасов. И алиас, и текст
  проходят через один и тот же пайплайн нормализации, после чего по тексту
  строятся уни- и биграммы и ищутся в индексе. Это обрабатывает склонения
  («разработке» -> «разработка») и многословные навыки («машинное обучение»,
  «machine learning»).
* **Raw-матчер** — для навыков с символами (``C++``, ``.NET``, ``CI/CD``).
  Ищет их как подстроку исходного текста в нижнем регистре с учётом границ
  слов, потому что ``razdel``/``pymorphy3`` разрушают их пунктуацию.

Дополнительно поддерживает разделение навыков на **критические** (must-have)
и обычные (nice-to-have). При передаче множества критических навыков
``keyword_score`` считается с повышенным весом для must-have.
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Set, Tuple

from .normalize import lemmatize_tokens, tokenize_words
from .skills_dict import RAW_SKILLS_ALL, SKILLS_ALL

# Вес критического навыка относительно обычного при расчёте keyword_score.
# 2.0 означает, что один must-have навык «стоит» как два обычных.
CRITICAL_WEIGHT = 2.0


def _raw_pattern(alias: str) -> re.Pattern:
    """Компилирует regex с учётом границ слов для сырого алиаса."""
    # Границы: не предшествует/не следует буква, цифра или точка, чтобы
    # «.net» не матчился внутри «network», а «c++» — внутри «c++++».
    return re.compile(rf"(?<![\w.]){re.escape(alias)}(?![\w.])")


def build_skill_index(
    skills: Dict[str, list] = None,
    raw_skills: Dict[str, list] = None,
) -> Tuple[Dict[str, Set[str]], Dict[re.Pattern, str]]:
    """Компилирует онтологию в таблицы поиска.

    Возвращает пару ``(lemma_index, raw_index)``:

    * ``lemma_index`` — нормализованная поверхностная форма -> множество
      канонических навыков.
    * ``raw_index`` — скомпилированный regex -> канонический навык
      (для символьных навыков).
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


# Ленивые синглтоны уровня модуля — строятся при первом обращении и
# переиспользуются дальше.
_lemma_index: Dict[str, Set[str]] | None = None
_raw_index: Dict[re.Pattern, str] | None = None


def _indices() -> Tuple[Dict[str, Set[str]], Dict[re.Pattern, str]]:
    """Возвращает (и при необходимости строит) индексы навыков."""
    global _lemma_index, _raw_index
    if _lemma_index is None:
        _lemma_index, _raw_index = build_skill_index()
    return _lemma_index, _raw_index


def extract_skills(text: str) -> Set[str]:
    """Возвращает множество канонических навыков, найденных в *text*."""
    lemma_index, raw_index = _indices()

    lemmas = lemmatize_tokens(tokenize_words(text))
    grams: Set[str] = set(lemmas)
    # Добавляет биграммы для многословных навыков («machine learning» и т.п.).
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


def normalize_skill_set(raw_skills_set: Set[str]) -> Set[str]:
    """Приводит любое сырое множество навыков к каноническим ключам из онтологии."""
    if not raw_skills_set:
        return set()

    lemma_index, raw_index = _indices()
    normalized = set()

    for skill in raw_skills_set:
        low_skill = skill.lower()
        found = False

        # Проверяем символьные навыки (C++, .NET)
        for pattern, canonical in raw_index.items():
            if pattern.search(low_skill):
                normalized.add(canonical)
                found = True
                break
        if found:
            continue

        # Проверяем буквенные навыки через лемматизацию
        lemmas = lemmatize_tokens(tokenize_words(skill))
        if not lemmas:
            continue

        # Ищем точное совпадение
        gram = " ".join(lemmas)
        canon = lemma_index.get(gram)
        if canon:
            normalized.update(canon)
        else:
            # Если навыка нет в словаре, оставляем как есть
            normalized.add(low_skill)

    return normalized


def match_skills(
        resume_text: str,
        vacancy_text: str,
        vacancy_skills: Optional[Set[str]] = None,
        critical_skills: Optional[Set[str]] = None,
        resume_skills: Optional[Set[str]] = None,  # Добавлена поддержка готовых навыков резюме
) -> dict:
    """Сравнивает навыки резюме с навыками, требуемыми вакансией."""
    # ОБЯЗАТЕЛЬНАЯ нормализация для маппинга синонимов
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


