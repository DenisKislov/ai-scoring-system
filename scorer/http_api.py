"""Internal stateless scoring service. Exposed only on the Compose network."""
from typing import List, Optional, Set
from fastapi import FastAPI
from pydantic import BaseModel, model_validator
from .config import algorithm_manifest, validate_weights
from .scoring import rank_candidates

app = FastAPI(title='Scoring kernel', version='1.0.0')


class RankIn(BaseModel):
    vacancy_text: str
    candidate_texts: List[str]
    candidate_ids: Optional[List[str]] = None
    weights: Optional[dict[str, float]] = None
    min_score: Optional[float] = None
    critical_skills: Optional[Set[str]] = None
    vacancy_skills: Optional[Set[str]] = None
    resume_skills_list: Optional[List[Set[str]]] = None

    @model_validator(mode='after')
    def aligned(self):
        if self.weights is not None:
            validate_weights(self.weights)
        for values in [self.candidate_ids, self.resume_skills_list]:
            if values is not None and len(values) != len(self.candidate_texts):
                raise ValueError('candidate inputs must align')
        if self.candidate_ids is not None and len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError('candidate IDs must be unique')
        return self


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/config')
def config():
    return algorithm_manifest()


@app.post('/rank')
def rank(payload: RankIn):
    return {'results': rank_candidates(**payload.model_dump())}
