"""TF-IDF + cosine text similarity with a fixed IDF reference.

The vectorizer is fit **once**, at import time, on a stable corpus of normalized
Russian vacancy/resume texts (``reference_corpus.REFERENCE_DOCS``). Fitting once
— rather than per pair or per pool — makes the cosine of a (vacancy, resume)
pair independent of which other candidates happen to be in the pool. Two
consequences the design relies on:

* the score is genuinely **absolute** (the README's claim now holds), and
* ``calculate_score`` and ``rank_candidates`` agree on the cosine of the same
  pair by construction.

Operates on **already-normalized** documents (see ``normalize.normalize``):
lemmatized, stop-words removed. Uni- and bi-grams let phrase-level overlap
("опыт работы", "machine learning") contribute. ``sublinear_tf=True`` dampens
very frequent terms so a candidate who repeats "python" twenty times is not
scored as twenty times more relevant.
"""
from __future__ import annotations

from typing import List

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .reference_corpus import REFERENCE_DOCS

_VECTORIZER = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)
_VECTORIZER.fit(REFERENCE_DOCS)


def cosine(norm_a: str, norm_b: str) -> float:
    """Cosine similarity between two already-normalized documents.

    Returns 0.0 for empty input, or when a document has no in-vocabulary terms
    (a zero TF-IDF vector). ``transform`` silently drops terms unseen during the
    one-time fit, which is intended: it keeps the IDF stable and pool-free.
    """
    if not norm_a or not norm_b:
        return 0.0
    mat = _VECTORIZER.transform([norm_a, norm_b])
    return float(cosine_similarity(mat[0], mat[1])[0, 0])


# Back-compat aliases kept so call sites read naturally.
def pair_cosine(norm_a: str, norm_b: str) -> float:
    """Cosine between two normalized documents (alias of :func:`cosine`)."""
    return cosine(norm_a, norm_b)


def batch_cosine(query: str, docs: List[str]) -> List[float]:
    """Cosine of *query* against each doc, using the fixed reference IDF."""
    return [cosine(query, d) for d in docs]
