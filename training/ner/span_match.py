"""Каскадный поиск спанов навыков для авторазметки NER-датасета.

Уровни матчинга (все найденные упоминания накапливаются; уровни различаются
шероховатостью, а не приоритетом — пересечения кандидатов разных навыков
разрешаются позже, глобально, правилом «длинный побеждает»):

1. verbatim — дословно, границы слов;
2. normalized — ё→е, «\\»→«/», гибкие пробелы между словами;
3. morph — русские слова >=5 букв по стему (как в прод-экстракторе
   ``scorer/skill_extractor.py``): «параллельным программированием»
   закрывает метку «параллельное программирование»;
4. alias — написания-синонимы из словаря проекта (``skills_dict``).

Пересечения кандидатов разрешаются правилом «длинный побеждает».
Навыки, не нашедшиеся вовсе, считаются шумом разметки (метки без
упоминания в тексте) и в обучение не попадают — дописывать текст нельзя.
"""
from __future__ import annotations

import random
import re
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

LABEL = "Skill"
_BOUND_L = r"(?<![\w])"
_BOUND_R = r"(?![\w])"


def _regex(pattern: str) -> re.Pattern:
    return re.compile(_BOUND_L + pattern + _BOUND_R, re.IGNORECASE)


def _flexible(skill: str) -> str:
    """Пробелы между словами — любые вертикальные/горизонтальные."""
    return r"\s+".join(re.escape(w) for w in skill.split())


def _normalize_text_like(skill: str) -> str:
    return skill.replace("ё", "е").replace("Ё", "Е").replace("\\", "/")


def _morph_pattern(skill: str) -> str | None:
    """Стем-паттерн: у кириллических слов >=5 букв отрезаем окончание."""
    parts = []
    for w in _normalize_text_like(skill).split():
        if re.match(r"^[а-яеА-ЯЕ\-]+$", w) and len(w) >= 5:
            stem = w[:-2] if len(w) >= 6 else w[:-1]
            parts.append(rf"{re.escape(stem)}[а-яе]{{0,3}}")
        else:
            parts.append(re.escape(w))
    return r"\s+".join(parts) if parts else None


def find_skill_spans(text: str, skill: str,
                     alias_map: Dict[str, Sequence[str]]) -> List[Tuple[int, int]]:
    """Все спаны *skill* в *text* (по всем уровням, позиция-отсортированы).

    Замены при нормализации односимвольные (ё→е, «\\»→«/»), поэтому смещения
    валидны и для исходного текста.
    """
    if not text or not skill:
        return []
    skill_norm = _normalize_text_like(skill)
    text_norm = text.replace("ё", "е").replace("Ё", "Е").replace("\\", "/")
    found: set = set()

    # 1. verbatim
    for m in _regex(re.escape(skill_norm)).finditer(text):
        found.add((m.start(), m.end()))

    # 2. normalized: ё/е, слэши, гибкие пробелы
    for m in _regex(_flexible(skill_norm)).finditer(text_norm):
        found.add((m.start(), m.end()))

    # 3. морфология
    morph = _morph_pattern(skill)
    if morph:
        for m in _regex(morph).finditer(text_norm):
            found.add((m.start(), m.end()))

    # 4. алиасы — все написания-синонимы канонической метки
    for alias in alias_map.get(skill_norm.lower(), ()):
        alias_norm = _normalize_text_like(alias)
        for m in _regex(re.escape(alias_norm)).finditer(text_norm):
            found.add((m.start(), m.end()))

    return sorted(found)


def build_entities(nlp, text: str, skills: Sequence[str],
                   alias_map: Dict[str, Sequence[str]] | None = None) -> Tuple[list, dict]:
    """Спаны навыков в *text*, выровненные на токены *nlp*.

    Возвращает ([(start, end, LABEL), ...] по возрастанию start, stats).
    Пересекающиеся кандидаты отбрасываются в пользу более длинного;
    спаны, не легшие на границы токенов, пропускаются и считаются.
    """
    alias_map = default_alias_map() if alias_map is None else alias_map
    candidates: List[Tuple[int, int]] = []
    matched = unmatched = 0
    for skill in skills:
        spans = find_skill_spans(text, skill, alias_map)
        if spans:
            matched += 1
            candidates.extend(spans)
        else:
            unmatched += 1

    # длинный побеждает; при равной длине — раньше по тексту
    candidates.sort(key=lambda se: (-(se[1] - se[0]), se[0]))
    accepted: List[Tuple[int, int]] = []
    rejected = 0
    for start, end in candidates:
        if any(start < e and s < end for s, e in accepted):
            rejected += 1
            continue
        accepted.append((start, end))
    accepted.sort()

    doc = nlp.make_doc(text)
    entities: List[Tuple[int, int, str]] = []
    skipped = 0
    for start, end in accepted:
        if doc.char_span(start, end, label=LABEL) is not None:
            entities.append((start, end, LABEL))
        else:
            skipped += 1

    stats = {"matched_skills": matched, "unmatched_skills": unmatched,
             "candidates_rejected": rejected, "skipped_misaligned": skipped}
    return entities, stats


def split_ids(ids: Sequence[str], seed: int = 42):
    """Детерминированный сплит 80/10/10 (train/dev/test); от n>=3 — по
    минимум одному документу в dev и test."""
    ids = sorted(ids)
    random.Random(seed).shuffle(ids)
    n = len(ids)
    if n >= 3:
        n_test = max(1, round(n * 0.1))
        n_dev = max(1, round(n * 0.1))
        n_train = n - n_dev - n_test
    else:
        n_train, n_dev, n_test = n, 0, 0
    train = ids[:n_train]
    dev = ids[n_train:n_train + n_dev]
    test = ids[n_train + n_dev:]
    return train, dev, test


_DEFAULT_ALIAS_MAP: Dict[str, List[str]] | None = None


def default_alias_map() -> Dict[str, List[str]]:
    """canonical.lower() -> список написаний-синонимов из словаря проекта."""
    global _DEFAULT_ALIAS_MAP
    if _DEFAULT_ALIAS_MAP is None:
        from scorer.skills_dict import RAW_SKILLS_ALL, SKILLS_ALL
        amap: Dict[str, List[str]] = {}
        for canonical, aliases in SKILLS_ALL.items():
            amap.setdefault(canonical.lower(), []).extend(aliases)
        for canonical, aliases in RAW_SKILLS_ALL.items():
            amap.setdefault(canonical.lower(), []).extend(aliases)
        _DEFAULT_ALIAS_MAP = amap
    return _DEFAULT_ALIAS_MAP
