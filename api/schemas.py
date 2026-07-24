"""Pydantic request models for the FastAPI layer.

Deliberately thin — they only validate the HTTP surface. All business logic
lives in ``db.mongo`` and ``scorer.service``; the routes forward these models
straight to those functions.
"""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class VacancyIn(BaseModel):
    """Vacancy in the hh.ru item shape (what the parser / seeder write)."""

    title: str
    description: str = ""
    skills: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    url: Optional[str] = None
    author_name: Optional[str] = None


class ResumeIn(BaseModel):
    """Resume in the hh.ru item shape."""

    title: str
    specialization: str = ""
    experience: str = ""
    skills: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    url: Optional[str] = None


class ScoreRequest(BaseModel):
    """Trigger scoring for a vacancy.

    *resume_ids* restricts the pool; otherwise the whole ``hh_resumes``
    collection is used (bounded by *limit_resumes*). *weights* override the
    keyword/cosine blend — keys are ``"keyword"`` / ``"cosine"``, see
    ``scorer.scoring.DEFAULT_WEIGHTS``.
    """

    vacancy_id: str
    resume_ids: Optional[List[str]] = None
    limit_resumes: Optional[int] = Field(default=None, ge=1)
    weights: Optional[Dict[str, float]] = None


class FeedbackIn(BaseModel):
    """HR decision for a (vacancy, resume) pair — the "Да/Нет" from the ТЗ."""

    vacancy_id: str
    resume_id: str
    decision: Literal["yes", "no"]
