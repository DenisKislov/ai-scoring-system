"""HTTP routes — thin wrappers over ``db.mongo`` and ``scorer.service``."""
from __future__ import annotations
from data.synthetic import generate_dataset
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from db import mongo
from db.builders import parse_raw_text_to_resume, resume_text
from scorer.service import score_vacancy

from .file_parser import extract_text_from_file
from .logger import setup_logger
from .schemas import FeedbackIn, ResumeIn, ScoreRequest, VacancyIn

logger = setup_logger("api.routes")
router = APIRouter()


def _not_found(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.get("/health", summary="Health check")
def health() -> dict:
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
        vac = None
    if vac is None:
        _not_found(f"vacancy {vacancy_id} not found")
    return vac


@router.post("/vacancies", status_code=status.HTTP_201_CREATED, summary="Upload a vacancy")
def create_vacancy(payload: VacancyIn) -> dict:
    doc = payload.model_dump()
    doc["_id"] = mongo.insert_vacancy(doc)
    return doc


@router.post("/upload_vacancy", status_code=status.HTTP_201_CREATED, summary="Загрузить файл вакансии")
async def upload_vacancy_file(file: UploadFile = File(...)):
    logger.info(f"Загружен файл вакансии: '{file.filename}'")
    try:
        content = await file.read()
        extracted_text = extract_text_from_file(content, file.filename)
        if not extracted_text:
            raise HTTPException(status_code=400, detail="Файл пуст или текст не распознан")

        vacancy_doc = {
            "title": file.filename.rsplit(".", 1)[0],
            "description": extracted_text,
            "skills": [],
            "_source": "user_upload",
            "filename": file.filename,
        }
        vac_id = mongo.insert_vacancy(vacancy_doc)
        return {"vacancy_id": str(vac_id), "status": "success", "filename": file.filename}
    except Exception as e:
        logger.error(f"Ошибка при загрузке вакансии: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/vacancies/clear", summary="Удалить все вакансии")
def clear_vacancies() -> dict:
    res = mongo._coll(mongo.COLL_VACANCIES).delete_many({})
    logger.info(f"Удалено вакансий: {res.deleted_count}")
    return {"deleted_count": res.deleted_count}


# --- resumes / candidates --------------------------------------------------

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


@router.post("/upload_resume", status_code=status.HTTP_201_CREATED, summary="Загрузить файл резюме (PDF/TXT)")
async def upload_resume_file(file: UploadFile = File(...)):
    logger.info(f"Загружен файл: '{file.filename}', размер: {file.size if hasattr(file, 'size') else 'неизвестен'} байт")

    try:
        content = await file.read()
        extracted_text = extract_text_from_file(content, file.filename)

        if not extracted_text:
            logger.warning(f"Файл '{file.filename}' пуст или текст не распознан")
            raise HTTPException(status_code=400, detail="Файл пуст или текст не распознан")

        logger.info(f"Извлечён текст из '{file.filename}': длина {len(extracted_text)} символов")
        parsed = parse_raw_text_to_resume(extracted_text)

        logger.info(
            f"Распаршено резюме: должность='{parsed.get('title', '')}', "
            f"навыков={len(parsed.get('skills', []))}, "
            f"опыт='{parsed.get('experience', '')}'"
        )
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
        try:
            ResumeIn(**resume_doc)
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка обработки резюме: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка обработки файла: {str(e)}")


@router.delete("/resumes/clear", summary="Удалить все резюме")
def clear_resumes() -> dict:
    res = mongo._coll(mongo.COLL_RESUMES).delete_many({})
    mongo._coll(mongo.COLL_SCORES).delete_many({})
    logger.info(f"Удалено резюме: {res.deleted_count}")
    return {"deleted_count": res.deleted_count}


# --- test data generation --------------------------------------------------

@router.post("/generate_test_data", summary="Генерация тестовых данных")
def generate_test_data(
    vacancies: int = Query(default=5, ge=1),
    resumes: int = Query(default=20, ge=1),
) -> dict:
    dataset = generate_dataset(n_vacancies=vacancies, n_resumes=resumes)
    created_resumes_count = 0

    for item in dataset:
        vac_data = item["vacancy"]
        vac_doc = {
            "title": vac_data["role"],
            "description": vac_data["text"],
            "skills": vac_data["skills"],
            "_synthetic": True,
            "_source": "generator",
        }
        mongo.insert_vacancy(vac_doc)

        for cand in item["candidates"]:
            parsed = parse_raw_text_to_resume(cand["text"])
            resume_doc = {
                "title": cand.get("role", parsed.get("title", "")),
                "specialization": parsed.get("specialization", ""),
                "experience": parsed.get("experience", ""),
                "skills": cand.get("skills", parsed.get("skills", [])),
                "tags": parsed.get("tags", []),
                "_raw_text": cand["text"],
                "_synthetic": True,
                "_source": "generator",
            }
            mongo.insert_resume(resume_doc)
            created_resumes_count += 1

    logger.info(f"Сгенерировано {len(dataset)} вакансий и {created_resumes_count} резюме")
    return {"status": "ok", "vacancies": len(dataset), "resumes": created_resumes_count}


# --- scoring ---------------------------------------------------------------

@router.post("/score", summary="Run scoring for a vacancy")
def score(payload: ScoreRequest) -> dict:
    try:
        out = score_vacancy(
            payload.vacancy_id,
            resume_ids=payload.resume_ids,
            limit_resumes=payload.limit_resumes,
            weights=payload.weights,
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


# --- feedback --------------------------------------------------------------

@router.post("/feedback", summary="Record an HR decision")
def feedback(payload: FeedbackIn) -> dict:
    mongo.save_feedback(payload.vacancy_id, payload.resume_id, payload.decision)
    return {"ok": True, **payload.model_dump()}


@router.get("/feedback", summary="Get current HR decision")
def get_feedback(vacancy_id: str, resume_id: str) -> dict:
    decision = mongo.get_feedback(vacancy_id, resume_id)
    return {"vacancy_id": vacancy_id, "resume_id": resume_id, "decision": decision}