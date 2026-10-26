"""TF-IDF и косинусная близость нормализованных текстов.

Словарь и IDF обучаются один раз на фиксированном ``REFERENCE_DOCS``.
Одна пара получает одинаковую близость независимо от состава и размера
пула резюме. Вход — уже нормализованные строки (пробельные леммы).
Тексты без известных слов имеют нулевой вектор и близость 0.
"""
from __future__ import annotations

from typing import List

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .reference_corpus import REFERENCE_DOCS


# Токены уже подготовлены normalize(): повторная токенизация регулярным
# выражением разделила бы названия технологий со спецсимволами.
_VECTORIZER = TfidfVectorizer(
    tokenizer=str.split,
    token_pattern=None,
    lowercase=False,
    sublinear_tf=True,
    norm="l2",
)
_VECTORIZER.fit(REFERENCE_DOCS)


def pair_cosine(norm_a: str, norm_b: str) -> float:
    """Косинусная близость двух нормализованных текстов в [0, 1]."""
    return batch_cosine(norm_a, [norm_b])[0]


def batch_cosine(query: str, docs: List[str]) -> List[float]:
    """Близость запроса к каждому документу с фиксированным словарём и IDF."""
    if not docs:
        return []
    if not query or not query.strip():
        return [0.0] * len(docs)

    query_vector = _VECTORIZER.transform([query])
    doc_vectors = _VECTORIZER.transform([doc or "" for doc in docs])
    scores = cosine_similarity(query_vector, doc_vectors)[0]
    # Устраняем лишь погрешность float около 1, без калибровки баллов.
    return scores.clip(0.0, 1.0).tolist()


# --- Обратная совместимость -------------------------------------------------
cosine = pair_cosine
