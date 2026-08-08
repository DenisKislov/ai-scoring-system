"""Извлечение и сопоставление навыков по онтологии.

Онтологию (``skills_dict.SKILLS`` + ``RAW_SKILLS``) один раз компилирует
в таблицы поиска, которые отображают *нормализованную* поверхностную форму
на один или несколько канонических навыков. Над каждым текстом работают
два матчера:

* **Lemma-матчер** — для буквенно-пробельных алиасов. И алиас, и текст
  проходят через один и тот же пайплайн нормализации, после чего по тексту
  строятся уни- и биграммы и ищутся в индексе. Это обрабатывает склонения
  («разработке» → «разработка») и многословные навыки («машинное обучение»,
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

    * ``lemma_index`` — нормализованная поверхностная форма → множество
      канонических навыков.
    * ``raw_index`` — скомпилированный regex → канонический навык
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


def match_skills(
    resume_text: str,
    vacancy_text: str,
    vacancy_skills: Optional[Set[str]] = None,
    critical_skills: Optional[Set[str]] = None,
) -> dict:
    """Сравнивает навыки резюме с навыками, требуемыми вакансией.

    Возвращает словарь:

    * ``matched`` / ``missing`` — полное пересечение и разница;
    * ``matched_critical`` / ``missing_critical`` — то же только по must-have;
    * ``keyword_score`` — доля покрытия с учётом повышенного веса критических
      навыков (если ``critical_skills`` передан);
    * ``vacancy_skills`` / ``resume_skills`` — сырые множества.

    *vacancy_skills* позволяет вызывающему коду передать навыки вакансии
    один раз (см. ``rank_candidates``).
    *critical_skills* — необязательное множество канонических must-have
    навыков. Если не передано, все навыки считаются равнозначными
    (обратная совместимость).
    """
    v_skills = vacancy_skills if vacancy_skills is not None else extract_skills(vacancy_text)
    r_skills = extract_skills(resume_text)

    matched = v_skills & r_skills
    missing = v_skills - r_skills

    # Критические навыки (must-have).
    crit = critical_skills or set()
    # Оставляем только те критические, которые реально требуются вакансией.
    crit = crit & v_skills

    matched_critical = matched & crit
    missing_critical = crit - matched

    # Расчёт keyword_score с учётом весов.
    if crit:
        # Каждый критический навык весит CRITICAL_WEIGHT, обычный — 1.0.
        total_weight = 0.0
        got_weight = 0.0
        for skill in v_skills:
            w = CRITICAL_WEIGHT if skill in crit else 1.0
            total_weight += w
            if skill in matched:
                got_weight += w
        keyword_score = got_weight / total_weight if total_weight > 0 else 0.0
    else:
        # Старое поведение — просто доля покрытия.
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