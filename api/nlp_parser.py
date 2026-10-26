"""
api/nlp_parser.py — словарный экстрактор навыков и парсер опыта работы.

Заменяет spaCy-подход: вместо NER/POS использует точный матч по словарю
навыков (JSON-файл). Один словарь — один файл данных, никаких ML-моделей.

Публичный API:
    extract_smart_skills(text: str) -> list[str]
        — словарная функция для скриптов оценки.
    extract_experience_years(text: str) -> float | None
        — парсер опыта, используемый db/builders.py.

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
from datetime import date
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


# =============================================================================
# Парсинг опыта работы
# =============================================================================
#
# Реальные резюме (SuperJob, PDF) пишут опыт десятком способов:
#   «Опыт работы: 5 лет», «Опыт работы — 3 года», «2 года и 1 месяц» (значение
#   поля experience без префикса), «Общий стаж: 22 года и 8 месяцев»,
#   «полгода», «менее года», «более 3 лет», «5 лет опыта», периоды вида
#   «апрель 2021 — настоящее время» / «июнь 2010 — июнь 2013».
# Прежний регэксп ``опыт\s+работы:\s*(\d+)\s*лет`` не совпадал ни с одним из
# этих форматов — опыт не находился вообще ни у одного реального резюме.

_MONTH_NAME = (
    r"(?:январ\w*|феврал\w*|март\w*|апрел\w*|ма[йя]\w*|июн[ья]\w*|июл[ья]\w*"
    r"|август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)"
)

_MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "май": 5, "мая": 5,
    "июн": 6, "июл": 7, "август": 8, "сентябр": 9, "октябр": 10,
    "ноябр": 11, "декабр": 12,
}

_OPEN_END = r"(?:настоящ\w*\s+врем\w*|текущ\w*\s+момент\w*|сейчас|по\s+наст\w*|н\s*\.\s*в\s*\.)"

_YEARS_WORD = r"(?:лет|год[а-яё]{0,2})\b"

# Явные формулировки «N лет (и M месяцев)» — в порядке приоритета.
_EXPLICIT_PATTERNS = [
    # «опыт работы: 5 лет», «стаж 10 лет», «общий стаж: 22 года и 8 месяцев»
    re.compile(
        r"(?:опыт(?:\s+работы)?|стаж(?:\s+работы)?|общий\s+стаж)\s*[:—–-]?\s*"
        r"(\d{1,2})\s*" + _YEARS_WORD +
        r"(?:\s*и?\s*(\d{1,2})\s*мес[а-яё]*)?"),
    # «5 лет опыта», «3 года работы»
    re.compile(r"(\d{1,2})\s*" + _YEARS_WORD + r"\s+(?:опыта|работы)"),
    # «более 3 лет», «свыше 2 лет», «от 5 лет»
    re.compile(r"(?:более|свыше|от)\s+(\d{1,2})\s*" + _YEARS_WORD),
    # «5-летний опыт», «10-летний стаж»
    re.compile(r"(\d{1,2})\s*[-\s]?\s*летн\w+\s+(?:опыт\w*|стаж\w*)"),
    # Голое значение поля SuperJob: «2 года и 1 месяц». Часть «и N месяц*»
    # обязательна — возраст («мне 30 лет») месяцев не содержит.
    re.compile(r"(\d{1,2})\s*" + _YEARS_WORD + r"\s*и\s*(\d{1,2})\s*мес[а-яё]*"),
]

# Месяцы с контекстом опыта: «опыт работы: 6 месяцев», «стаж 10 месяцев».
_MONTHS_CONTEXT = re.compile(
    r"(?:опыт|стаж)[^.\n]{0,40}?(\d{1,2})\s*мес(?:яц[а-яё]*)?\b")

# Дробные и оценочные формулировки.
_FRACTIONAL = [
    (re.compile(r"полтора\s*" + _YEARS_WORD), 1.5),
    (re.compile(r"пол\s*года|полгода"), 0.5),
    (re.compile(r"(?:менее|до|почти)\s+(?:одного\s+)?года"), 0.5),
    (re.compile(r"около\s+года"), 1.0),
]

_NO_EXPERIENCE = re.compile(r"(?:без\s+опыта|нет\s+опыта|не\s+имею\s+опыта)")

# Периоды работы: «июнь 2010 — июнь 2013», «2018 — 2021»,
# «апрель 2021 — настоящее время». Строка-контекст не должна быть про учебу.
_PERIOD = re.compile(
    rf"({_MONTH_NAME})?\s*(\d{{4}})\s*(?:[—–-]+|\bпо\b)\s*"
    rf"(?:(?:({_MONTH_NAME})?\s*(\d{{4}}))|({_OPEN_END}))",
    re.IGNORECASE,
)

_EDUCATION_LINE = re.compile(
    r"(?:образовани|университет|институт|академи|колледж|школ|курсы|бакалавр|магистр|специалитет)",
    re.IGNORECASE,
)

_MAX_YEARS = 60


def _experience_text(text: str) -> str:
    """Exclude education sections, including dates on their following lines."""
    lines = []
    in_education = False
    for line in text.splitlines():
        if re.match(r'^\s*(?:опыт(?:\s+работы)?|трудовая деятельность|стаж|без опыта)\b', line, re.I):
            in_education = False
        elif re.match(r'^\s*(?:образование|курсы|повышение квалификации)\b', line, re.I):
            in_education = True
        if not in_education:
            lines.append(line)
    return '\n'.join(lines)


def _month_number(word: str) -> Optional[int]:
    """«апрель»/«апреля» -> 4; возвращает None для пустой строки."""
    if not word:
        return None
    stem = word.lower()[:6].rstrip()
    for prefix, num in _MONTHS.items():
        if word.lower().startswith(prefix):
            return num
    return None


def _parse_periods(text: str, now: date) -> float:
    """Суммирует (с объединением пересечений) длительности периодов работы."""
    intervals = []
    for line in text.splitlines():
        if _EDUCATION_LINE.search(line):
            continue
        for m in _PERIOD.finditer(line):
            start_m = _month_number(m.group(1) or "")
            start_y = int(m.group(2))
            if m.group(5):  # открытое «настоящее время»
                end_m, end_y = now.month, now.year
            else:
                end_m = _month_number(m.group(3) or "")
                end_y = int(m.group(4))
            start_idx = start_y * 12 + (start_m - 1 if start_m else 0)
            end_idx = end_y * 12 + (end_m - 1 if end_m else 0)
            if 1990 <= start_y <= now.year and start_idx < end_idx <= now.year * 12 + now.month - 1:
                intervals.append((start_idx, end_idx))
    if not intervals:
        return 0.0

    intervals.sort()
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        ls, le = merged[-1]
        if s <= le:
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    total_months = sum(e - s for s, e in merged)
    return total_months / 12


def extract_experience_years(text: str, *, now: Optional[date] = None) -> Optional[float]:
    """Вытаскивает годы опыта из текста резюме.

    Приоритет источников: явная формулировка («Опыт работы: 5 лет») →
    дробные формулировки («полгода») → сумма периодов работы → маркер
    «без опыта» (0.0). Возвращает ``None``, когда текст об опыте молчит.

    ``now`` — точка отсчёта для открытых периодов («настоящее время»);
    параметр нужен для детерминированных тестов.
    """
    if not text or not text.strip():
        return None
    now = now or date.today()
    low = _experience_text(text.lower())

    for pattern in _EXPLICIT_PATTERNS:
        m = pattern.search(low)
        if m:
            years = int(m.group(1))
            months = int(m.group(2)) if (m.lastindex or 0) >= 2 and m.group(2) else 0
            if 0 <= years <= _MAX_YEARS:
                return round(min(years + months / 12, _MAX_YEARS), 2)

    m = _MONTHS_CONTEXT.search(low)
    if m and int(m.group(1)) <= 36:
        return round(int(m.group(1)) / 12, 2)

    for pattern, value in _FRACTIONAL:
        if pattern.search(low):
            return value

    from_periods = _parse_periods(low, now)
    if from_periods > 0:
        return round(min(from_periods, _MAX_YEARS), 2)

    if _NO_EXPERIENCE.search(low):
        return 0.0

    return None


def format_experience(years: float) -> str:
    """Человекочитаемая строка опыта: 5.0 -> «5 лет», 2.08 -> «2 года 1 мес.»"""
    if years is None:
        return ""
    whole = int(years)
    months = int(round((years - whole) * 12))
    if months == 12:
        whole, months = whole + 1, 0
    if whole == 0 and months == 0:
        return "Без опыта"
    year_word = "год" if whole % 10 == 1 and whole % 100 != 11 else (
        "года" if whole % 10 in (2, 3, 4) and whole % 100 not in (12, 13, 14) else "лет")
    parts = []
    if whole:
        parts.append(f"{whole} {year_word}")
    if months:
        parts.append(f"{months} мес.")
    return " ".join(parts)
