"""Text normalization for the scoring pipeline.

Pipeline: ``razdel`` tokenization -> drop punctuation/short tokens ->
``pymorphy3`` lemmatization (Russian) -> drop stop-words. English tokens pass
through lower-cased and un-lemmatized, because ``pymorphy3`` is Russian-only.

The lemmatizer is cached (``lru_cache``) because real resume corpora repeat the
same skill/word lemmas thousands of times — caching turns ~1 ms/token into a
hash-table lookup.
"""
from __future__ import annotations

import re
from functools import lru_cache

import pymorphy3
from razdel import tokenize

from .stopwords_ru import STOPWORDS_RU

# Module-level analyzer — instantiating MorphAnalyzer loads a ~few-MB dict,
# so we create it exactly once.
_MORPH = pymorphy3.MorphAnalyzer()

# A "word" token: starts with a letter, then letters/digits/some symbols that
# legitimately appear inside identifiers (``python3``, ``c++``, ``node.js``).
_WORD_RE = re.compile(r"^[a-zа-яё][a-zа-яё0-9+./#-]*$", re.IGNORECASE)


@lru_cache(maxsize=200_000)
def _lemma(token: str) -> str:
    """Normal form of a token. Unknown (e.g. English) tokens pass through."""
    try:
        parses = _MORPH.parse(token)
    except Exception:
        return token
    if not parses:
        return token
    nf = parses[0].normal_form
    return nf or token


def tokenize_words(text: str) -> list[str]:
    """Lower-cased word tokens with punctuation removed."""
    out: list[str] = []
    for tok in tokenize(text or ""):
        w = tok.text.strip().lower()
        if w and _WORD_RE.match(w):
            out.append(w)
    return out


def lemmatize_tokens(tokens: list[str]) -> list[str]:
    """Lemmatize tokens, dropping one-char tokens and stop-words (pre & post)."""
    lemmas: list[str] = []
    for w in tokens:
        if len(w) <= 1 or w in STOPWORDS_RU:
            continue
        lemma = _lemma(w)
        if lemma in STOPWORDS_RU:
            continue
        lemmas.append(lemma)
    return lemmas


def normalize(text: str) -> str:
    """Space-joined content lemmas — the document string fed to TF-IDF."""
    return " ".join(lemmatize_tokens(tokenize_words(text)))
