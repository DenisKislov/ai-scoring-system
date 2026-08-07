"""Публичный API скоринга: calculate_score и rank_candidates.

Обе функции реализуют согласованный гибридный скор:

    raw = w_keyword * keyword_score + w_cosine * cosine_similarity
    Score(%) = round(raw * 100)

* keyword_score — долю требуемых навыков вакансии (из онтологии),
  найденных в резюме. Формирует столбец «Найденные навыки».
* cosine_similarity — TF-IDF-косинус между описанием вакансии и
  резюме (опыт + описание).

Score является **абсолютной** мерой в диапазоне [0, 100]: полностью
совпадающее резюме получает высокий балл, нерелевантное — низкий, даже если
оно единственное в пуле. Это удовлетворяет требованию «Показ 3» (не ставить
100 % нерелевантным текстам).
rank_candidates дополнительно возвращает rank_percentile — позицию
кандидата внутри поданного пула, чтобы UI мог показывать бейдж «топ-10 %»
без искажения абсолютного скора.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .normalize import normalize
from .similarity import batch_cosine, pair_cosine
from .skills import extract_skills, match_skills

# Веса по умолчанию: 60 % — пересечение навыков, 40 % — текстовое сходство.
DEFAULT_WEIGHTS: Dict[str, float] = {"keyword": 0.6, "cosine": 0.4}


def calculate_score(
    resume_text: str,
    vacancy_text: str,
    weights: Optional[Dict[str, float]] = None,
    min_score: Optional[float] = None,
) -> Dict:
    """Считает скор одного резюме относительно одной вакансии.

    Возвращает JSON-совместимый словарь: score (0–100), keyword_score,
    cosine_sim, raw_score, matched_skills, missing_skills,
    а также вклад каждого компонента и (опционально) флаг прохождения порога.
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
    score = round(raw * 100)

    result = {
        "score": score,
        "raw_score": round(raw, 3),
        "keyword_score": round(keyword_score, 3),
        "cosine_sim": round(cosine_sim, 3),
        "keyword_contribution": round(w["keyword"] * keyword_score, 3),
        "cosine_contribution": round(w["cosine"] * cosine_sim, 3),
        "matched_skills": sorted(match["matched"]),
        "missing_skills": sorted(match["missing"]),
        "vacancy_skills": sorted(match["vacancy_skills"]),
    }

    # Добавляет флаг прохождения минимального порога, если порог задан.
    if min_score is not None:
        result["passed_threshold"] = score >= min_score

    return result


def rank_candidates(
    vacancy_text: str,
    candidate_texts: List[str],
    candidate_ids: Optional[List] = None,
    weights: Optional[Dict[str, float]] = None,
    min_score: Optional[float] = None,
) -> List[Dict]:
    """Считает скоры и ранжирует пачку резюме относительно одной вакансии.

    TF-IDF обучается один раз на фиксированном референс-корпусе, поэтому
    косинус пары не зависит от состава пула, а Score остаётся абсолютной
    мерой. Результаты сортируются по score по убыванию и обогащаются
    полем rank_percentile.
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

    # Извлекает навыки вакансии один раз, а не для каждого резюме.
    v_skills = extract_skills(vacancy_text)

    results: List[Dict] = []
    for cid, rtext, cos in zip(candidate_ids, candidate_texts, cosines):
        match = match_skills(rtext, vacancy_text, vacancy_skills=v_skills)
        kw = match["keyword_score"]
        raw = w["keyword"] * kw + w["cosine"] * cos
        score = round(raw * 100)

        item = {
            "candidate_id": cid,
            "score": score,
            "raw_score": round(raw, 3),
            "keyword_score": round(kw, 3),
            "cosine_sim": round(cos, 3),
            "keyword_contribution": round(w["keyword"] * kw, 3),
            "cosine_contribution": round(w["cosine"] * cos, 3),
            "matched_skills": sorted(match["matched"]),
            "missing_skills": sorted(match["missing"]),
            "_raw": raw,
        }

        # Добавляет флаг прохождения минимального порога, если порог задан.
        if min_score is not None:
            item["passed_threshold"] = score >= min_score

        results.append(item)

    _add_percentile_rank(results)
    results.sort(key=lambda r: r["score"], reverse=True)

    # Удаляет служебное поле после сортировки.
    for r in results:
        del r["_raw"]
    return results


def _add_percentile_rank(results: List[Dict]) -> None:
    """Прикрепляет rank_percentile — долю пула, набравшую строго меньший скор."""
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
    """Возвращает пустой результат при отсутствии текста резюме или вакансии."""
    return {
        "score": 0,
        "raw_score": 0.0,
        "keyword_score": 0.0,
        "cosine_sim": 0.0,
        "keyword_contribution": 0.0,
        "cosine_contribution": 0.0,
        "matched_skills": [],
        "missing_skills": [],
        "vacancy_skills": [],
    }