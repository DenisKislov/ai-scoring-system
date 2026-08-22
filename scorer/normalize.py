import re
from functools import lru_cache
from typing import Iterable

import pymorphy3
from razdel import tokenize

from .stopwords_ru import STOPWORDS_RU

_MORPH = pymorphy3.MorphAnalyzer()

_WORD_RE = re.compile(r"^[a-zа-яё][a-zа-яё0-9+./#\-]*$", re.IGNORECASE)
_HTML_RE = re.compile(r"<[^>]+>", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")

_ABBREVIATIONS: dict[str, str] = {
    "k8s": "kubernetes",
    "kube": "kubernetes",
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "golang": "go",
    "pg": "postgresql",
    "postgres": "postgresql",
    "mongo": "mongodb",
    "ci": "ci/cd",
    "cd": "ci/cd",
    "gh": "github",
    "gl": "gitlab",
    "ml": "machine learning",
    "dl": "deep learning",
    "nlp": "natural language processing",
    "cv": "computer vision",
    "os": "operating system",
}


def _expand_abbreviation(token: str) -> str:
    return _ABBREVIATIONS.get(token, token)


@lru_cache(maxsize=200_000)
def _lemma(token: str) -> str:
    try:
        parses = _MORPH.parse(token)
    except Exception:
        return token
    if not parses:
        return token
    nf = parses[0].normal_form
    return nf or token


def clean_text(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    text = _HTML_RE.sub(" ", text)
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or (ord(ch) >= 32))
    text = _WS_RE.sub(" ", text)
    return text.strip()


def tokenize_words(text: str) -> list[str]:
    cleaned = clean_text(text)
    out: list[str] = []
    for tok in tokenize(cleaned):
        w = tok.text.strip().lower()
        if w and _WORD_RE.match(w):
            w = _expand_abbreviation(w)
            out.append(w)
    return out


def lemmatize_tokens(tokens: Iterable[str]) -> list[str]:
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
    if not text:
        return ""
    tokens = tokenize_words(text)
    lemmas = lemmatize_tokens(tokens)
    return " ".join(lemmas)