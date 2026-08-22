from typing import List
from rank_bm25 import BM25Okapi


def normalize_bm25_score(score: float, max_expected: float = 10.0) -> float:
    return min(max(score / max_expected, 0.0), 1.0)


def cosine(norm_a: str, norm_b: str) -> float:
    if not norm_a or not norm_b:
        return 0.0

    tokenized_query = norm_a.split()
    tokenized_doc = norm_b.split()

    bm25 = BM25Okapi([tokenized_doc])
    raw_score = bm25.get_scores(tokenized_query)[0]

    return normalize_bm25_score(raw_score)


def pair_cosine(norm_a: str, norm_b: str) -> float:
    return cosine(norm_a, norm_b)


def batch_cosine(query: str, docs: List[str]) -> List[float]:
    if not query or not docs:
        return [0.0] * len(docs)

    tokenized_query = query.split()
    tokenized_docs = [doc.split() for doc in docs]

    bm25 = BM25Okapi(tokenized_docs)
    raw_scores = bm25.get_scores(tokenized_query)

    return [normalize_bm25_score(score) for score in raw_scores]