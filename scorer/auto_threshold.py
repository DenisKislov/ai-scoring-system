"""Calibrate the display filter with the production extraction and matching code.

The lower decile of top-score candidates' coverage is robust to isolated weak
queries. The UI caps this target at the top candidate's coverage for each
actual pool, so the leading result is always visible.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Tuple

from .corpus import vacancy_text_of, resume_text_of
from .scoring import rank_candidates
from .skills import extract_skills

METHOD = 'extracted_top1_lower_decile_pool_cap_v1'


def compute_dataset_threshold(vacancies_path: str | Path, resumes_path: str | Path,
                              *, floor_to: int = 3) -> Tuple[float, int, int]:
    vacancies = json.loads(Path(vacancies_path).read_text(encoding='utf-8'))
    resumes = json.loads(Path(resumes_path).read_text(encoding='utf-8'))
    if not vacancies or not resumes:
        return 0.0, len(vacancies), len(resumes)
    texts = [resume_text_of(item) for item in resumes]
    skills = [extract_skills(text) for text in texts]
    coverages = []
    for vacancy in vacancies:
        text = vacancy_text_of(vacancy)
        required = extract_skills(text)
        if not required:
            continue
        ranked = rank_candidates(text, texts, vacancy_skills=required,
                                 resume_skills_list=skills)
        coverages.append(len(ranked[0]['matched_skills']) / len(required))
    target = sorted(coverages)[(len(coverages) - 1) // 10] if coverages else 0.0
    factor = 10 ** floor_to
    return math.floor(target * factor) / factor, len(vacancies), len(resumes)
