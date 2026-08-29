"""HTTP routes — thin wrappers over ``db.mongo`` and ``scorer.service``.

No business logic lives here: each endpoint maps one HTTP call to one
data/scorer function and shapes the response.

Error mapping:
* a missing document, a malformed ObjectId, or a "not found" raised by the
  scorer -> ``404`` (handled inline);
* a DB connection failure (``pymongo`` error) bubbles up to the global
  ``503`` handler in ``api.main``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from db import mongo

from scorer.service import score_vacancy
from db.builders import resume_text, parse_raw_text_to_resume
from .schemas import FeedbackIn, ResumeIn, ScoreRequest, VacancyIn

from fastapi import UploadFile, File, HTTPException
from .file_parser import extract_text_from_file

router = APIRouter()


def _not_found(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.get("/health", summary="Health check")
def health() -> dict:
    """Ping MongoDB. A connection failure propagates to the 503 handler."""
    mongo.get_client().admin.command("ping")
    return {"status": "ok", "db": mongo.MONGO_DB}


# --- vacancies -------------------------------------------------------------

@router.get("/vacancies", summary="List vacancies")
def list_vacancies(limit: Optional[int] = Query(default=None, ge=1)) -> list:
    return mongo.list_vacancies(limit=limit)


@router.get("/vacancies/{vacancy_id}", summary="Get a vacancy")
def get_vacancy(vacancy_id: str) -> dict:
    try:
        vac = mongo.get_vacancy(vacancy_id)
    except ValueError:
        vac = None  # not a valid ObjectId
    if vac is None:
        _not_found(f"vacancy {vacancy_id} not found")
    return vac


@router.post("/vacancies", status_code=status.HTTP_201_CREATED, summary="Upload a vacancy")
def create_vacancy(payload: VacancyIn) -> dict:
    doc = payload.model_dump()
    doc["_id"] = mongo.insert_vacancy(doc)
    return doc


# --- resumes / candidates --------------------------------------------------

@router.get("/resumes/{resume_id}", summary="Get a resume")
def get_resume(resume_id: str) -> dict:
    try:
        res = mongo.get_resume(resume_id)
    except ValueError:
        res = None
    if res is None:
        _not_found(f"resume {resume_id} not found")

    # Вариант Б: собираем красивый текст прямо здесь
    res["formatted_text"] = resume_text(res)

    return res


@router.post("/candidates", status_code=status.HTTP_201_CREATED, summary="Upload a resume")
def create_resume(payload: ResumeIn) -> dict:
    doc = payload.model_dump()
    doc["_id"] = mongo.insert_resume(doc)
    return doc


# --- scoring ---------------------------------------------------------------

@router.post("/score", summary="Run scoring for a vacancy")
def score(payload: ScoreRequest) -> dict:
    """Score the vacancy's resume pool and persist results to ``hh_scores``."""
    try:
        out = score_vacancy(
            payload.vacancy_id,
            resume_ids=payload.resume_ids,
            limit_resumes=payload.limit_resumes,
            weights=payload.weights,
        )
    except ValueError as exc:
        # "vacancy ... not found" / "no resumes to score"
        _not_found(str(exc))
    return {"vacancy_id": payload.vacancy_id, "count": len(out["results"]), "results": out["results"]}


@router.get("/results/{vacancy_id}", summary="Ranked results for a vacancy")
def results(
    vacancy_id: str,
    top: Optional[int] = Query(default=None, ge=1),
) -> dict:
    scores = mongo.get_scores(vacancy_id, top=top)
    if not scores:
        # Empty either means "not scored yet" or "vacancy unknown". Resolve the
        # ambiguity so a typo in the id isn't silently returned as an empty list.
        try:
            exists = mongo.get_vacancy(vacancy_id) is not None
        except ValueError:
            exists = False
        if not exists:
            _not_found(f"vacancy {vacancy_id} not found")
    return {"vacancy_id": vacancy_id, "count": len(scores), "results": scores}


# --- feedback --------------------------------------------------------------

@router.post("/feedback", summary="Record an HR decision")
def feedback(payload: FeedbackIn) -> dict:
    mongo.save_feedback(payload.vacancy_id, payload.resume_id, payload.decision)
    return {"ok": True, **payload.model_dump()}

@router.get("/feedback", summary="Get current HR decision")
def get_feedback(vacancy_id: str, resume_id: str) -> dict:
    decision = mongo.get_feedback(vacancy_id, resume_id)
    return {"vacancy_id": vacancy_id, "resume_id": resume_id, "decision": decision}


@router.post("/upload_resume", summary="Загрузить файл резюме (PDF/TXT)")
async def upload_resume_file(file: UploadFile = File(...)):
    try:
        content = await file.read()
        extracted_text = extract_text_from_file(content, file.filename)
        if not extracted_text:
            raise HTTPException(status_code=400, detail="Файл пуст или текст не распознан")
        parsed = parse_raw_text_to_resume(extracted_text)
        resume_doc = {
            "title": parsed.get("title", ""),
            "specialization": parsed.get("specialization", ""),
            "experience": parsed.get("experience", ""),
            "skills": parsed.get("skills", []),
            "tags": parsed.get("tags", []),
            "_synthetic": False,
            "_source": "user_upload",
            "_raw_text": extracted_text,
            "filename": file.filename,
        }
        from .schemas import ResumeIn
        try:
            validated = ResumeIn(**resume_doc)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Данные не прошли валидацию: {str(e)}"
            )
        resume_id = mongo.insert_resume(resume_doc)
        return {
            "resume_id": str(resume_id),
            "filename": file.filename,
            "status": "success",
            "parsed": {
                "title": parsed.get("title"),
                "experience": parsed.get("experience"),
                "skills_count": len(parsed.get("skills", [])),
                "skills": parsed.get("skills", [])[:5],
            },
            "text_preview": extracted_text[:300] + "..."
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки файла: {str(e)}")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки файла: {str(e)}")
