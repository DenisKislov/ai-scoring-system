"""Public scoring API: ``calculate_score`` and ``rank_candidates``.

Both implement the *hybrid* score agreed in the design:

    raw = w_keyword * keyword_score + w_cosine * cosine_similarity
    Score(%) = round(raw * 100)

* ``keyword_score`` — share of the vacancy's required skills (from the
  ontology) present in the resume. Produces the "Найденные навыки" column.
* ``cosine_similarity`` — TF-IDF cosine between the vacancy description and the
  resume (experience + description).

``Score`` is an **absolute** measure in ``[0, 100]``: a fully matching resume
scores high, an unrelated one scores low — even as the lone candidate in a
pool. This satisfies the "Показ 3" requirement (no 100% for unrelated texts).
``rank_candidates`` additionally reports ``rank_percentile`` — the candidate's
position within the submitted pool — so the UI can badge "top-10%" without
distorting the absolute score.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .normalize import normalize
from .similarity import batch_cosine, pair_cosine
from .skills import extract_skills, match_skills

DEFAULT_WEIGHTS: Dict[str, float] = {"keyword": 0.6, "cosine": 0.4}


def calculate_score(
    resume_text: str,
    vacancy_text: str,
    weights: Optional[Dict[str, float]] = None,
) -> Dict:
    """Score a single resume against a single vacancy.

    Returns a JSON-friendly dict: ``score`` (0-100), ``keyword_score``,
    ``cosine_sim``, ``raw_score``, ``matched_skills``, ``missing_skills``.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    if not (resume_text and resume_text.strip()) or not (
        vacancy_text and vacancy_text.strip()
    ):
        return _empty_result()

    match = match_skills(resume_text, vacancy_text)
    keyword_score = match["keyword_score"]
    cosine_sim = pair_cosine(normalize(vacancy_text), normalize(resume_text))

    raw = w["keyword"] * keyword_score + w["cosine"] * cosine_sim
    return {
        "score": round(raw * 100),
        "raw_score": round(raw, 3),
        "keyword_score": round(keyword_score, 3),
        "cosine_sim": round(cosine_sim, 3),
        "matched_skills": sorted(match["matched"]),
        "missing_skills": sorted(match["missing"]),
        "vacancy_skills": sorted(match["vacancy_skills"]),
    }


def rank_candidates(
    vacancy_text: str,
    candidate_texts: List[str],
    candidate_ids: Optional[List] = None,
    weights: Optional[Dict[str, float]] = None,
) -> List[Dict]:
    """Score and rank a batch of resumes against one vacancy.

    TF-IDF is fitted once over ``[vacancy] + candidates`` so IDF reflects the
    whole pool (rare skills score higher) instead of per-pair noise. Results
    are sorted by ``score`` descending and enriched with ``rank_percentile``.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    if not candidate_texts:
        return []
    if candidate_ids is None:
        candidate_ids = list(range(len(candidate_texts)))
    elif len(candidate_ids) != len(candidate_texts):
        raise ValueError("candidate_ids must align with candidate_texts")

    norm_v = normalize(vacancy_text)
    norm_resumes = [normalize(r) for r in candidate_texts]
    cosines = batch_cosine(norm_v, norm_resumes)

    # Extract the vacancy's skills once, not once per resume.
    v_skills = extract_skills(vacancy_text)

    results: List[Dict] = []
    for cid, rtext, cos in zip(candidate_ids, candidate_texts, cosines):
        match = match_skills(rtext, vacancy_text, vacancy_skills=v_skills)
        kw = match["keyword_score"]
        raw = w["keyword"] * kw + w["cosine"] * cos
        results.append(
            {
                "candidate_id": cid,
                "score": round(raw * 100),
                "raw_score": round(raw, 3),
                "keyword_score": round(kw, 3),
                "cosine_sim": round(cos, 3),
                "matched_skills": sorted(match["matched"]),
                "missing_skills": sorted(match["missing"]),
                "_raw": raw,
            }
        )

    _add_percentile_rank(results)
    results.sort(key=lambda r: r["score"], reverse=True)
    for r in results:
        del r["_raw"]
    return results


def _add_percentile_rank(results: List[Dict]) -> None:
    """Attach ``rank_percentile`` = share of pool scoring strictly lower."""
    raws = [r["_raw"] for r in results]
    n = len(raws)
    if n <= 1:
        for r in results:
            r["rank_percentile"] = 100
        return
    for r in results:
        below = sum(1 for x in raws if x < r["_raw"])
        r["rank_percentile"] = round(100 * below / (n - 1))


def _empty_result() -> Dict:
    return {
        "score": 0,
        "raw_score": 0.0,
        "keyword_score": 0.0,
        "cosine_sim": 0.0,
        "matched_skills": [],
        "missing_skills": [],
        "vacancy_skills": [],
    }
