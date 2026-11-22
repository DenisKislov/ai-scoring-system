from typing import Dict, List, Optional, Set

from .normalize import normalize
from .similarity import batch_cosine, pair_cosine
from .skills import match_skill_sets, prepare_skill_input
from .metrics import category_metrics
from .config import load_config, validate_weights
from .privacy import professional_text

DEFAULT_WEIGHTS: Dict[str, float] = load_config()["weights"]


def calculate_score(
        resume_text: str,
        vacancy_text: str,
        weights: Optional[Dict[str, float]] = None,
        min_score: Optional[float] = None,
        critical_skills: Optional[Set[str]] = None,
) -> Dict:
    w = validate_weights({**load_config()["weights"], **(weights or {})})
    resume_text, r_skills, denied = prepare_skill_input(professional_text(resume_text))
    vacancy_text, v_skills, _ = prepare_skill_input(professional_text(vacancy_text))
    match = match_skill_sets(v_skills, r_skills, critical_skills, denied)
    keyword_score = match["keyword_score"]
    cosine_sim = pair_cosine(normalize(vacancy_text), normalize(resume_text))

    raw = w["keyword"] * keyword_score + w["cosine"] * cosine_sim

    if len(match["matched"]) == 0:
        raw = 0.0

    score = round(raw * 100)

    result = {
        "score": score,
        "raw_score": round(raw, 3),
        "keyword_score": round(keyword_score, 3),
        "cosine_sim": round(cosine_sim, 3),
        "keyword_contribution": round(w["keyword"] * keyword_score, 3) if raw else 0.0,
        "cosine_contribution": round(w["cosine"] * cosine_sim, 3) if raw else 0.0,
        "matched_skills": sorted(match["matched"]),
        "missing_skills": sorted(match["missing"]),
        "matched_critical": sorted(match["matched_critical"]),
        "missing_critical": sorted(match["missing_critical"]),
        "vacancy_skills": sorted(match["vacancy_skills"]),
        "critical_skills": sorted(match["critical_skills"]),
    }

    if min_score is not None:
        result["passed_threshold"] = score >= min_score

    return result


def rank_candidates(
        vacancy_text: str,
        candidate_texts: List[str],
        candidate_ids: Optional[List] = None,
        weights: Optional[Dict[str, float]] = None,
        min_score: Optional[float] = None,
        critical_skills: Optional[Set[str]] = None,
        vacancy_skills: Optional[Set[str]] = None,
        resume_skills_list: Optional[List[Set[str]]] = None,
) -> List[Dict]:
    w = validate_weights({**load_config()["weights"], **(weights or {})})
    if not candidate_texts:
        return []
    if candidate_ids is None:
        candidate_ids = list(range(len(candidate_texts)))
    elif len(candidate_ids) != len(candidate_texts):
        raise ValueError("candidate_ids must align with candidate_texts")

    if resume_skills_list is not None and len(resume_skills_list) != len(candidate_texts):
        raise ValueError("resume_skills_list must align with candidate_texts")
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("candidate_ids must be unique")
    vacancy_text, v_skills, v_denied = prepare_skill_input(professional_text(vacancy_text), vacancy_skills)
    prepared = [prepare_skill_input(professional_text(text), skills)
                for text, skills in zip(candidate_texts, resume_skills_list or [None] * len(candidate_texts))]
    cosines = batch_cosine(normalize(vacancy_text), [normalize(text) for text, _, _ in prepared])

    results: List[Dict] = []
    metric_requirements = (vacancy_skills if vacancy_skills is not None and not v_denied
                           else v_skills)
    for cid, (rtext, r_skills, denied), cos in zip(candidate_ids, prepared, cosines):
        match = match_skill_sets(v_skills, r_skills, critical_skills, denied)
        kw = match["keyword_score"]
        raw = w["keyword"] * kw + w["cosine"] * cos
        if not rtext.strip() or not vacancy_text.strip() or not match["matched"]:
            raw = 0.0
        score = round(raw * 100)

        cat_metrics = category_metrics(predicted_skills=r_skills, true_skills=metric_requirements)

        item = {
            "candidate_id": cid,
            "score": score,
            "raw_score": round(raw, 3),
            "keyword_score": round(kw, 3),
            "cosine_sim": round(cos, 3),
            "keyword_contribution": round(w["keyword"] * kw, 3) if raw else 0.0,
            "cosine_contribution": round(w["cosine"] * cos, 3) if raw else 0.0,
            "matched_skills": sorted(match["matched"]),
            "missing_skills": sorted(match["missing"]),
            "matched_critical": sorted(match["matched_critical"]),
            "missing_critical": sorted(match["missing_critical"]),
            "critical_skills": sorted(match["critical_skills"]),
            "vacancy_skills": sorted(match["vacancy_skills"]),
            "metrics_by_category": cat_metrics,
            "_raw": raw,
        }

        if min_score is not None:
            item["passed_threshold"] = score >= min_score

        results.append(item)

    _add_percentile_rank(results)
    results.sort(key=lambda r: r["score"], reverse=True)

    for r in results:
        del r["_raw"]
    return results


def _add_percentile_rank(results: List[Dict]) -> None:
    raws = [r["_raw"] for r in results]
    n = len(raws)
    if n <= 1:
        for r in results:
            r["rank_percentile"] = 100
        return
    for r in results:
        below = sum(1 for x in raws if x < r["_raw"])
        r["rank_percentile"] = round(100 * below / (n - 1))
