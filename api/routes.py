from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status, UploadFile, File
import subprocess

from db import mongo
from scorer.service import score_vacancy
from db.builders import resume_text, parse_raw_text_to_resume
from .schemas import FeedbackIn, ResumeIn, ScoreRequest, VacancyIn
from .file_parser import extract_text_from_file
from .nlp_parser import extract_smart_skills

router = APIRouter()


def _not_found(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.get("/health", summary="Health check")
def health() -> dict:
    mongo.get_client().admin.command("ping")
    return {"status": "ok", "db": mongo.MONGO_DB}


@router.get("/vacancies", summary="List vacancies")
def list_vacancies(limit: Optional[int] = Query(default=None, ge=1)) -> list:
    return mongo.list_vacancies(limit=limit)


@router.get("/vacancies/{vacancy_id}", summary="Get a vacancy")
def get_vacancy(vacancy_id: str) -> dict:
    try:
        vac = mongo.get_vacancy(vacancy_id)
    except ValueError:
        vac = None
    if vac is None:
        _not_found(f"vacancy {vacancy_id} not found")
    return vac


@router.post("/vacancies", status_code=status.HTTP_201_CREATED, summary="Upload a vacancy")
def create_vacancy(payload: VacancyIn) -> dict:
    doc = payload.model_dump()
    doc["_id"] = mongo.insert_vacancy(doc)
    return doc


@router.get("/resumes/{resume_id}", summary="Get a resume")
def get_resume(resume_id: str) -> dict:
    try:
        res = mongo.get_resume(resume_id)
    except ValueError:
        res = None
    if res is None:
        _not_found(f"resume {resume_id} not found")

    res["formatted_text"] = resume_text(res)
    return res


@router.post("/candidates", status_code=status.HTTP_201_CREATED, summary="Upload a resume")
def create_resume(payload: ResumeIn) -> dict:
    doc = payload.model_dump()
    doc["_id"] = mongo.insert_resume(doc)
    return doc


@router.post("/score", summary="Run scoring for a vacancy")
def score(payload: ScoreRequest) -> dict:
    try:
        out = score_vacancy(
            payload.vacancy_id,
            resume_ids=payload.resume_ids,
            limit_resumes=payload.limit_resumes,
            weights=payload.weights,
            critical_skills=set(payload.critical_skills) if payload.critical_skills else None,
        )
    except ValueError as exc:
        _not_found(str(exc))
    return {"vacancy_id": payload.vacancy_id, "count": len(out["results"]), "results": out["results"]}


@router.get("/results/{vacancy_id}", summary="Ranked results for a vacancy")
def results(
    vacancy_id: str,
    top: Optional[int] = Query(default=None, ge=1),
) -> dict:
    scores = mongo.get_scores(vacancy_id, top=top)
    if not scores:
        try:
            exists = mongo.get_vacancy(vacancy_id) is not None
        except ValueError:
            exists = False
        if not exists:
            _not_found(f"vacancy {vacancy_id} not found")
    return {"vacancy_id": vacancy_id, "count": len(scores), "results": scores}


@router.post("/feedback", summary="Record an HR decision")
def feedback(payload: FeedbackIn) -> dict:
    mongo.save_feedback(payload.vacancy_id, payload.resume_id, payload.decision)
    return {"ok": True, **payload.model_dump()}


@router.get("/feedback", summary="Get current HR decision")
def get_feedback(vacancy_id: str, resume_id: str) -> dict:
    decision = mongo.get_feedback(vacancy_id, resume_id)
    return {"vacancy_id": vacancy_id, "resume_id": resume_id, "decision": decision}


@router.post("/upload_resume", summary="Upload resume file (PDF/TXT)")
async def upload_resume_file(file: UploadFile = File(...)):
    try:
        content = await file.read()
        extracted_text = extract_text_from_file(content, file.filename)
        if not extracted_text:
            raise HTTPException(status_code=400, detail="Файл пуст или текст не распознан")

        parsed = parse_raw_text_to_resume(extracted_text)
        smart_skills = extract_smart_skills(extracted_text)

        resume_doc = {
            "title": parsed.get("title", ""),
            "specialization": parsed.get("specialization", ""),
            "experience": parsed.get("experience", ""),
            "skills": smart_skills,
            "tags": parsed.get("tags", []),
            "_synthetic": False,
            "_source": "user_upload",
            "_raw_text": extracted_text,
            "filename": file.filename,
        }

        resume_id = mongo.insert_resume(resume_doc)

        return {
            "resume_id": str(resume_id),
            "filename": file.filename,
            "status": "success",
            "parsed": {
                "title": parsed.get("title"),
                "experience": parsed.get("experience"),
                "skills_count": len(smart_skills),
                "skills": smart_skills[:5],
            },
            "text_preview": extracted_text[:300] + "..."
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки файла: {str(e)}")


@router.post("/upload_vacancy", summary="Upload vacancy file (PDF/TXT)")
async def upload_vacancy_file(file: UploadFile = File(...)):
    try:
        content = await file.read()
        extracted_text = extract_text_from_file(content, file.filename)
        if not extracted_text:
            raise HTTPException(status_code=400, detail="Файл пуст или текст не распознан")

        lines = [line.strip() for line in extracted_text.split('\n') if line.strip()]
        title = lines[0] if lines else "Не указано"

        smart_skills = extract_smart_skills(extracted_text)

        vacancy_doc = {
            "title": title,
            "description": extracted_text,
            "skills": smart_skills,
            "_synthetic": False,
            "_source": "user_upload",
            "_raw_text": extracted_text,
            "filename": file.filename,
        }

        vacancy_id = mongo.insert_vacancy(vacancy_doc)

        return {
            "vacancy_id": str(vacancy_id),
            "filename": file.filename,
            "status": "success",
            "parsed": {
                "title": title,
                "skills_count": len(smart_skills),
                "skills": smart_skills[:5]
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки файла: {str(e)}")


@router.delete("/resumes/clear", summary="Clear all resumes")
def clear_all_resumes():
    db = mongo.get_client()[mongo.MONGO_DB]
    res = db["hh_resumes"].delete_many({})
    db["hh_scores"].delete_many({})
    return {"status": "success", "deleted_count": res.deleted_count}


@router.delete("/vacancies/clear", summary="Clear all vacancies")
def clear_all_vacancies():
    db = mongo.get_client()[mongo.MONGO_DB]
    res = db["hh"].delete_many({})
    db["hh_scores"].delete_many({})
    return {"status": "success", "deleted_count": res.deleted_count}


@router.post("/generate_test_data", summary="Generate test data")
def generate_test_data(vacancies: int = 5, resumes: int = 20):
    try:
        subprocess.run(
            ["python", "-m", "db.seed", "--vacancies", str(vacancies), "--resumes", str(resumes)],
            check=True
        )
        return {"status": "success", "message": f"Сгенерировано {vacancies} вакансий и {resumes} резюме"}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {e}")