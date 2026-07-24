"""Resume-scoring package — hybrid keyword + TF-IDF/cosine matcher for Russian
resumes and vacancies (hh.ru domain).

Quick start::

    from scorer import calculate_score, rank_candidates

    score = calculate_score(resume_text, vacancy_text)
    ranked = rank_candidates(vacancy_text, [resume1, resume2, resume3])
"""
from .normalize import normalize
from .scoring import DEFAULT_WEIGHTS, calculate_score, rank_candidates
from .skills import extract_skills, match_skills

__all__ = [
    "calculate_score",
    "rank_candidates",
    "extract_skills",
    "match_skills",
    "normalize",
    "DEFAULT_WEIGHTS",
]
