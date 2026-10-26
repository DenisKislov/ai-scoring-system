from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from scorer.config import validate_weights


class DocumentIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    skills: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    url: Optional[str] = None

    @field_validator('title')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Текст не должен быть пустым')
        return value.strip()

    @field_validator('skills', 'tags')
    @classmethod
    def clean_skills(cls, values):
        if any(not s.strip() for s in values):
            raise ValueError('Навык не должен быть пустым')
        return list(dict.fromkeys(s.strip() for s in values))


class VacancyIn(DocumentIn):
    description: str = ''
    author_name: Optional[str] = None
    critical_skills: List[str] = Field(default_factory=list)


class ResumeIn(DocumentIn):
    specialization: str = ''
    experience: str = ''


class CriticalSkillsIn(BaseModel):
    critical_skills: List[str]


class ScoreRequest(BaseModel):
    vacancy_id: str = Field(min_length=1)
    resume_ids: Optional[List[str]] = None
    limit_resumes: Optional[int] = Field(default=None, ge=1)
    weights: Optional[Dict[str, float]] = None
    critical_skills: Optional[List[str]] = None

    @field_validator('weights')
    @classmethod
    def valid_weights(cls, value):
        return validate_weights(value) if value is not None else value

    @field_validator('resume_ids')
    @classmethod
    def unique_ids(cls, values):
        if values is not None and (not values or any(not v.strip() for v in values)):
            raise ValueError('resume_ids must contain at least one ID')
        return list(dict.fromkeys(values)) if values is not None else None


class FeedbackIn(BaseModel):
    vacancy_id: str = Field(min_length=1)
    resume_id: str = Field(min_length=1)
    decision: Literal['yes', 'no']


class ScoreResult(BaseModel):
    model_config = ConfigDict(extra='allow')
    candidate_id: Optional[str] = None
    resume_id: Optional[str] = None
    score: int = Field(ge=0, le=100)
    keyword_score: float = 0
    cosine_sim: float = 0
    keyword_contribution: float = 0
    cosine_contribution: float = 0
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    missing_critical: List[str] = Field(default_factory=list)


class ResultsOut(BaseModel):
    vacancy_id: str
    count: int
    results: List[ScoreResult]


class UploadOut(BaseModel):
    model_config = ConfigDict(extra='allow')
    filename: str
    file_size_bytes: int
    text_length: int
    skills: List[str]
    skills_count: int
    original_sha256: str
    status: Literal['success'] = 'success'
