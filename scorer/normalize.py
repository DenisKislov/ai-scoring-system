"""Нормализация текста для пайплайна скоринга.

Пайплайн:
  1. Лёгкая очистка (HTML-теги, лишние пробелы, управляющие символы).
  2. Раскрытие распространённых IT-сокращений и сленга.
  3. Токенизация через razdel (с учётом правил русского языка).
  4. Оставляем только «словоподобные» токены (буквы + цифры + символы,
     которые легитимно встречаются внутри идентификаторов: python3,
     c++, node.js).
  5. Лемматизация через pymorphy3 (только русский; английские токены
     проходят в нижнем регистре без изменений).
  6. Удаление однобуквенных токенов и русских стоп-слов (до и после
     лемматизации).

Лемматизатор кэшируется (lru_cache), потому что в реальных корпусах
резюме одни и те же леммы навыков/слов повторяются тысячи раз — кэш
превращает ~1 мс на токен в поиск по хеш-таблице.

Английские токены намеренно **не** лемматизируются: pymorphy3 работает
только с русским и иначе выдавал бы мусор.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable

import pymorphy3
from razdel import tokenize

from .stopwords_ru import STOPWORDS_RU


# Модульный MorphAnalyzer — создаётся ровно один раз (загружает словарь
# размером в несколько мегабайт)

_MORPH = pymorphy3.MorphAnalyzer()

# «Словоподобный» токен: начинается с буквы, далее буквы/цифры/символы,
# которые легитимно встречаются внутри идентификаторов
# (python3, c++, node.js, ci/cd, .net)
_WORD_RE = re.compile(
    r"^[a-zа-яё][a-zа-яё0-9+./#\-]*$",
    re.IGNORECASE,
)

# Грубая очистка HTML-тегов (в резюме иногда остаётся разметка)
_HTML_RE = re.compile(r"<[^>]+>", re.IGNORECASE)

# Схлопывание любой последовательности пробельных символов в один пробел
_WS_RE = re.compile(r"\s+")


# Распространённые IT-сокращения / сленг -> каноническая форма
# Применяются к сырому токену в нижнем регистре до лемматизации, чтобы
# и «k8s», и «kubernetes» попадали в одну и ту же поверхностную форму
# для матчера навыков и для TF-IDF
# Словарь специально маленький и консервативный — чрезмерное раскрытие

_ABBREVIATIONS: dict[str, str] = {
    # контейнеры / оркестрация
    "k8s": "kubernetes",
    "kube": "kubernetes",
    # языки / рантаймы
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "golang": "go",
    # базы данных
    "pg": "postgresql",
    "postgres": "postgresql",
    "mongo": "mongodb",
    # devops / инструменты
    "ci": "ci/cd",
    "cd": "ci/cd",
    "gh": "github",
    "gl": "gitlab",
    # ml
    "ml": "machine learning",
    "dl": "deep learning",
    "nlp": "natural language processing",
    "cv": "computer vision",
    # прочее
    "os": "operating system",
}


def _expand_abbreviation(token: str) -> str:
    """Возвращает каноническую форму известного сокращения, иначе сам токен."""
    return _ABBREVIATIONS.get(token, token)


@lru_cache(maxsize=200_000)
def _lemma(token: str) -> str:
    """Нормальная форма токена.

    Неизвестные (например, чисто английские) токены проходят без изменений.
    Кэш критически важен: одни и те же леммы встречаются десятки тысяч раз
    по типичному корпусу резюме
    """
    try:
        parses = _MORPH.parse(token)
    except Exception:
        return token
    if not parses:
        return token
    nf = parses[0].normal_form
    return nf or token


def clean_text(text: str) -> str:
    """Лёгкая предобработка перед токенизацией

    - убирает HTML-теги
    - нормализует пробелы
    - удаляет большинство управляющих символов
    - возвращает пустую строку для None / нестрокового ввода
    """
    if not text or not isinstance(text, str):
        return ""
    # Удаляем HTML-теги, которые иногда просачиваются из парсеров hh.ru.
    text = _HTML_RE.sub(" ", text)
    # Отбрасываем управляющие символы, кроме обычных пробельных.
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or (ord(ch) >= 32))
    # Схлопываем последовательности пробелов.
    text = _WS_RE.sub(" ", text)
    return text.strip()


def tokenize_words(text: str) -> list[str]:
    """Токены в нижнем регистре с удалённой пунктуацией.

    Оставляются только токены, подходящие под _WORD_RE. Это отфильтровывает
    чистую пунктуацию, одиночные числа и большую часть шума, сохраняя при этом
    идентификаторы вида c++, node.js, python3
    """
    cleaned = clean_text(text)
    out: list[str] = []
    for tok in tokenize(cleaned):
        w = tok.text.strip().lower()
        if w and _WORD_RE.match(w):
            # Раскрываем известные сокращения до дальнейшей обработки.
            w = _expand_abbreviation(w)
            out.append(w)
    return out


def lemmatize_tokens(tokens: Iterable[str]) -> list[str]:
    """Лемматизирует токены, отбрасывая однобуквенные и стоп-слова (до и после)

    Стоп-слова проверяются и по поверхностной форме, и по лемме, чтобы
    надёжно убирать «быть», «есть», «являюсь» и тп
    """
    lemmas: list[str] = []
    for w in tokens:
        if len(w) <= 1 or w in STOPWORDS_RU:
            continue
        lemma = _lemma(w)
        if lemma in STOPWORDS_RU or len(lemma) <= 1:
            continue
        lemmas.append(lemma)
    return lemmas


def normalize(text: str) -> str:
    """Строка лемм через пробел — документ, который подаётся в TF-IDF

    Пустой / отсутствующий ввод даёт пустую строку (ниже по пайплайну
    косинус корректно вернёт 0.0)
    """
    if not text:
        return ""
    tokens = tokenize_words(text)
    lemmas = lemmatize_tokens(tokens)
    return " ".join(lemmas)