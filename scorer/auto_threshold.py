"""Автоматический подбор порога отбора кандидатов по датасету.

Используется при старте API (см. ``api.threshold_service``): считаем один
раз по SuperJob-датасетам и кладём результат в MongoDB, чтобы фронт читал
готовое значение через ``GET /threshold``.

Логика совпадает с ``scripts/benchmark_real_data.py``:

    overlap(vacancy, resume) = |v_skills ∩ r_skills| / |v_skills|

    T = min по вакансиям от (max overlap у этой вакансии по всем резюме)

T — максимальное значение, при котором у КАЖДОЙ вакансии есть хотя бы один
кандидат с overlap >= T.

Скоррер не запускается: overlap считается по ``expected_skills`` из JSON,
которые совпадают с нормализованными ``skills`` документов в MongoDB после
импорта SuperJob.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Tuple

from scorer.skills import normalize_skill_set


def _gt_skills(item: dict) -> set:
    """Нормализованный набор навыков документа (вакансии или резюме)."""
    return normalize_skill_set({s for s in item.get("expected_skills", []) if s})


def compute_dataset_threshold(
    vacancies_path: str | Path,
    resumes_path: str | Path,
    *,
    floor_to: int = 3,
) -> Tuple[float, int, int]:
    """Считает порог по паре JSON-датасетов.

    Возвращает ``(threshold, n_vacancies, n_resumes)``.

    ``floor_to`` — сколько знаков после запятой оставлять. Округляем ВНИЗ,
    потому что фильтр на фронте использует ``overlap >= T``: если top-1
    вакансии ровно 0.2478, а мы округлим до 0.248, единственный кандидат
    её не пройдёт. Округление вниз гарантирует, что top-1 каждой вакансии
    останется проходящим.
    """
    vacancies = json.loads(Path(vacancies_path).read_text(encoding="utf-8"))
    resumes = json.loads(Path(resumes_path).read_text(encoding="utf-8"))

    if not vacancies or not resumes:
        return 0.0, len(vacancies), len(resumes)

    res_skills = [_gt_skills(r) for r in resumes]

    min_top1: float | None = None
    for vac in vacancies:
        v_skills = _gt_skills(vac)
        if not v_skills:
            continue

        best = 0.0
        for rs in res_skills:
            if not rs:
                continue
            ov = len(v_skills & rs) / len(v_skills)
            if ov > best:
                best = ov
                if best >= 1.0:
                    break

        if min_top1 is None or best < min_top1:
            min_top1 = best
            if min_top1 <= 0.0:
                break

    if min_top1 is None:
        return 0.0, len(vacancies), len(resumes)

    factor = 10 ** floor_to
    floored = math.floor(min_top1 * factor) / factor
    if floored < 0.0:
        floored = 0.0

    return floored, len(vacancies), len(resumes)