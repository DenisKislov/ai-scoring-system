from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class VacancyIn(BaseModel):
    title: str
    description: str = ""
    skills: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    url: Optional[str] = None
    author_name: Optional[str] = None


class ResumeIn(BaseModel):
    title: str
    specialization: str = ""
    experience: str = ""
    skills: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    url: Optional[str] = None


class ScoreRequest(BaseModel):
    vacancy_id: str
    resume_ids: Optional[List[str]] = None
    limit_resumes: Optional[int] = Field(default=None, ge=1)
    weights: Optional[Dict[str, float]] = None
    critical_skills: Optional[List[str]] = None


class FeedbackIn(BaseModel):
    vacancy_id: str
    resume_id: str
    decision: Literal["yes", "no"]