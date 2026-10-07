"""
api/nlp_parser.py — словарный экстрактор навыков.

Заменяет spaCy-подход: вместо NER/POS использует точный матч по словарю
навыков (JSON-файл). Один словарь — один файл данных, никаких ML-моделей.

Публичный API:
    extract_smart_skills(text: str) -> list[str]
        — основная функция, которую вызывает db/builders.py.

Конфигурация через переменные окружения:
    SKILLS_VOCAB_PATH   путь к JSON-словарю
                        (по умолчанию "data/skills_vocab.json")

Формат словаря (см. scripts/build_skills_vocab.py):
    {
      "version": "1.0",
      "config": {"lemmatized": false, ...},
      "skills": {
        "python":     ["python"],
        "postgresql": ["postgresql", "postgres", "psql"],
        ...
      }
    }
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Опциональная лемматизация.
#
# Работает только с кириллицей. Латиница и токены с цифрами не трогаются —
# иначе pymorphy3 ломает 'oracle' -> 'оракл', 'ios' -> 'иос' и т.п.
# По умолчанию лемматизация выключена: на вакансиях она вредит
# (см. экспериментальные прогоны).
# ---------------------------------------------------------------------------
try:
    import pymorphy3
    _MORPH = pymorphy3.MorphAnalyzer()
except ImportError:
    _MORPH = None


_TOKEN_RE = re.compile(r"[А-Яа-яЁёA-Za-z]+")


def _lemma_ru_only(text: str) -> str:
    """Лемматизируем только слова, содержащие кириллицу. Остальное — lower()."""
    if _MORPH is None:
        return text

    def _repl(m: re.Match) -> str:
        w = m.group(0)
        if not re.search(r"[А-Яа-яЁё]", w):
            return w.lower()
        if len(w) < 2 or any(c.isdigit() for c in w):
            return w.lower()
        return _MORPH.parse(w.lower())[0].normal_form

    return _TOKEN_RE.sub(_repl, text)


# ---------------------------------------------------------------------------
# Очистка текста перед матчингом.
#
# Убирает типичный шум PDF-выгрузок (SuperJob-футер, URL, даты, e-mail)
# и склеивает переносы строк, чтобы многословные навыки вроде
# "анализ\nданных" находились.
# ---------------------------------------------------------------------------
def _clean_text(text: str, lemmatize: bool = False) -> str:
    if not text:
        return ""
    t = text.replace("\u00ad", "")          # soft hyphen
    t = t.replace("ё", "е").replace("Ё", "Е")
    t = t.lower()

    # мусор из PDF
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"www\.\S+", " ", t)
    t = re.sub(r"\S+@\S+", " ", t)
    t = re.sub(r"\b\d{2}\.\d{2}\.\d{4},?\s*\d{1,2}:\d{2}\b", " ", t)
    t = re.sub(r"\bsuper\s*job\b", " ", t)
    t = re.sub(r"russia\.superjob\.ru", " ", t)
    t = re.sub(r"force\s*printing\s*=\s*1", " ", t)
    t = re.sub(r"vacancy-\d+\.html", " ", t)

    # перенос строки перед строчной буквой — признак разрыва слова/фразы
    t = re.sub(r"\n(?=[а-яa-z])", " ", t)
    t = re.sub(r"\s*\n\s*", " ", t)
    t = re.sub(r"[ \t\u00a0]+", " ", t)

    if lemmatize:
        t = _lemma_ru_only(t)
    return t


# ---------------------------------------------------------------------------
# Singleton словаря.
#
# Грузится один раз при первом вызове extract_smart_skills.
# Все паттерны компилируются один раз, дальше — только search().
# ---------------------------------------------------------------------------
class _SkillVocabulary:
    _instance: Optional["_SkillVocabulary"] = None

    def __init__(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)

        # Поддерживаем оба формата:
        #   A) {"config": {...}, "skills": {...}}          — наш build_skills_vocab.py
        #   B) {"config": {...}, "resumes": {...},
        #                       "vacancies": {...}}        — старый build_vocab.py
        if "skills" in doc:
            self.lemmatized: bool = bool(doc.get("config", {}).get("lemmatized", False))
            raw: Dict[str, List[str]] = doc["skills"]
        elif "resumes" in doc and "vacancies" in doc:
            self.lemmatized = bool(doc.get("config", {}).get("lemmatized", False))
            merged: Dict[str, List[str]] = {}
            for split in ("resumes", "vacancies"):
                for canonical, pats in doc[split].items():
                    bucket = merged.setdefault(canonical, [])
                    for p in pats:
                        if p and p not in bucket:
                            bucket.append(p)
            raw = merged
        else:
            raise ValueError(
                f"Непонятный формат словаря {path}: ожидаю ключ "
                f"'skills' или пару 'resumes'+'vacancies'"
            )

        # Компиляция regex: длинные паттерны идут первыми,
        # чтобы более специфичные совпадения не перекрывались короткими.
        self.patterns: List[Tuple[str, re.Pattern]] = []
        for canonical, pats in raw.items():
            for p in pats:
                if not p or len(p) < 2:
                    continue
                rx = re.compile(
                    rf"(?<![a-zа-я0-9_]){re.escape(p)}(?![a-zа-я_])",
                    re.IGNORECASE,
                )
                self.patterns.append((canonical, rx))
        self.patterns.sort(key=lambda t: -len(t[1].pattern))

    # ---- singleton access ----
    @classmethod
    def get(cls, path: Optional[str] = None) -> "_SkillVocabulary":
        if cls._instance is None:
            resolved = path or os.environ.get(
                "SKILLS_VOCAB_PATH", "data/skills_vocab.json"
            )
            if not os.path.exists(resolved):
                raise FileNotFoundError(
                    f"Словарь навыков не найден: {resolved}. "
                    f"Собери его: python scripts/build_skills_vocab.py "
                    f"--from-list data/skills_source.txt --no-lemmatize"
                )
            cls._instance = cls(resolved)
        return cls._instance

    # ---- извлечение ----
    def extract(self, text: str) -> List[str]:
        norm = _clean_text(text, lemmatize=self.lemmatized)
        hits: List[str] = []
        seen: Set[str] = set()
        for canonical, rx in self.patterns:
            if canonical in seen:
                continue
            if rx.search(norm):
                seen.add(canonical)
                hits.append(canonical)
        return sorted(hits)


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------

def extract_smart_skills(text: str) -> List[str]:
    """
    Основная точка входа. Возвращает отсортированный список навыков
    (канонические имена из словаря).

    Если словарь не собран — падаем с понятной ошибкой, а не молча
    возвращаем пустой список. Это лучше: сразу видно, что нужно
    запустить build_skills_vocab.py.
    """
    return _SkillVocabulary.get().extract(text)
