"""HTTP routes — thin wrappers over ``db.mongo`` and ``scorer.service``."""
from __future__ import annotations
from data.synthetic import generate_dataset
from typing import Optional
from pathlib import Path
import hashlib
import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from db import mongo
from db.builders import parse_raw_text_to_resume, resume_text
from scorer import extract_skills
from scorer.service import score_vacancy
from fastapi.concurrency import run_in_threadpool
from .file_parser import extract_text_from_file, MAX_FILE_BYTES
from scorer.config import algorithm_manifest
from scorer.skills import normalize_skill_set
from .logger import LOG_PATH, setup_logger, event
from .schemas import FeedbackIn, ResumeIn, ScoreRequest, VacancyIn, CriticalSkillsIn, ResultsOut, UploadOut
from .threshold_service import (
    get_threshold_doc,
    recompute_threshold,
)

logger = setup_logger("api.routes")
router = APIRouter()


def _not_found(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.get("/health", summary="Health check")
def health() -> dict:
    mongo.get_client().admin.command("ping")
    return {"status": "ok", "db": mongo.MONGO_DB}


@router.get("/stats", summary="Количество вакансий и резюме в базе")
def get_stats() -> dict:
    """Текущее число документов в коллекциях вакансий и резюме."""
    return {
        "vacancies": mongo._coll(mongo.COLL_VACANCIES).count_documents({}),
        "resumes": mongo._coll(mongo.COLL_RESUMES).count_documents({}),
    }

# --- threshold -------------------------------------------------------------

@router.get("/threshold", summary="Текущий порог отбора кандидатов")
def get_threshold_endpoint() -> dict:
    """Возвращает сохранённый порог и метаданные его расчёта.

    Фронт использует поле ``value`` (число от 0 до 1) для фильтрации
    кандидатов: показываются те, у кого доля совпавших навыков вакансии
    больше или равна этому значению.
    """
    doc = get_threshold_doc()
    if not doc:
        # Не 404: фронт должен уметь работать в режиме «порог не задан».
        return {"value": None, "message": "Порог ещё не вычислен"}
    return doc


@router.post("/threshold/recompute", summary="Пересчитать порог из датасетов")
def recompute_threshold_endpoint() -> dict:
    """Принудительно пересчитывает порог по текущим датасетам.

    Полезно после обновления ``superjob_dataset.json`` / ``dataset_resume.json``,
    без перезапуска сервера.
    """
    try:
        doc = recompute_threshold(force=True)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except mongo.pymongo.errors.PyMongoError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[Threshold] Ошибка пересчёта: {exc}")
        raise HTTPException(status_code=500, detail=f"Сбой пересчёта порога: {exc}")
    return doc


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
    doc["skills"] = sorted(normalize_skill_set(set(doc["skills"])) | extract_skills(doc["title"] + "\n" + doc["description"]))
    doc["critical_skills"] = _critical(doc["critical_skills"], doc["skills"])
    doc["_id"] = mongo.insert_vacancy(doc)
    event(logger, "vacancy_created", document_id=doc["_id"], skills_count=len(doc["skills"]))
    return doc


def _critical(values, available):
    skills = normalize_skill_set(set(values))
    if not skills <= normalize_skill_set(set(available)):
        raise HTTPException(422, "Критические навыки должны входить в навыки вакансии")
    return sorted(skills)


def _store_file(kind: str, content: bytes, filename: str, critical_skills=None) -> dict:
    started = time.perf_counter()
    filename = Path((filename or "file").replace("\\", "/")).name
    event(logger, "upload_started", kind=kind, filename=filename, size_bytes=len(content))
    try:
        text = extract_text_from_file(content, filename)
        parsed = parse_raw_text_to_resume(text)
    except ValueError as exc:
        event(logger, "extraction_error", kind=kind, filename=filename, message=str(exc))
        raise HTTPException(400, str(exc)) from exc
    skills = parsed["skills"]
    digest = hashlib.sha256(content).hexdigest()
    common = {"filename": filename, "_original": content, "original_sha256": digest,
              "file_size_bytes": len(content), "_raw_text": text,
              "_source": "user_upload", "created_at": datetime.now(timezone.utc)}
    if kind == "vacancy":
        common.pop("_raw_text", None)
        doc = {**common, "title": filename.rsplit(".", 1)[0], "description": text,
               "skills": skills, "critical_skills": _critical(critical_skills or [], skills)}
        doc_id = mongo.insert_vacancy(doc)
    else:
        doc = {**parsed, **common, "_synthetic": False}
        doc_id = mongo.insert_resume(doc)
    duration = time.perf_counter() - started
    event(logger, "upload_completed", kind=kind, filename=filename, document_id=doc_id,
          size_bytes=len(content), text_length=len(text), skills_count=len(skills),
          sha256=digest, duration_seconds=round(duration, 6))
    return {kind + "_id": str(doc_id), "filename": filename, "file_size": len(content),
            "file_size_bytes": len(content), "text_length": len(text), "title": doc["title"],
            "model_name": "SkillExtractor", "skills_count": len(skills), "skills": skills,
            "original_sha256": digest, "critical_skills": doc.get("critical_skills", []),
            "duration_seconds": duration, "status": "success"}


@router.post("/upload_vacancy", status_code=201, response_model=UploadOut, summary="Загрузить PDF/TXT вакансии")
async def upload_vacancy_file(file: UploadFile = File(...), critical_skills: str = Form("[]")):
    try:
        critical = json.loads(critical_skills)
        if not isinstance(critical, list) or any(not isinstance(v, str) for v in critical):
            raise ValueError()
    except ValueError:
        raise HTTPException(422, "critical_skills должен быть JSON-массивом строк")
    content = await file.read(MAX_FILE_BYTES + 1)
    return await run_in_threadpool(_store_file, "vacancy", content, file.filename, critical)


@router.patch("/vacancies/{vacancy_id}/critical-skills", summary="Сохранить критические навыки вакансии")
def update_critical_skills(vacancy_id: str, payload: CriticalSkillsIn):
    vac = get_vacancy(vacancy_id)
    skills = _critical(payload.critical_skills, vac.get("skills", []))
    mongo.update_critical_skills(vacancy_id, skills)
    return {"vacancy_id": vacancy_id, "critical_skills": skills}


@router.delete("/vacancies/clear", summary="Удалить все вакансии и связанные результаты")
def clear_vacancies() -> dict:
    count = mongo.delete_documents("vacancies")
    event(logger, "documents_deleted", kind="vacancies", count=count)
    return {"deleted_count": count}


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
    from scorer.skills import _get_extractor
    res["skill_mentions"] = [
        {"skill": name, "text": match.group(0)}
        for name, pattern in _get_extractor().patterns
        for match in pattern.finditer(res["formatted_text"])
        if normalize_skill_set({name}) & set(res.get("skills", []))
    ]
    return res


@router.post("/candidates", status_code=status.HTTP_201_CREATED, summary="Upload a resume")
def create_resume(payload: ResumeIn) -> dict:
    doc = payload.model_dump()
    doc["skills"] = sorted(normalize_skill_set(set(doc["skills"])) | extract_skills(resume_text(doc)))
    doc["_id"] = mongo.insert_resume(doc)
    event(logger, "resume_created", document_id=doc["_id"], skills_count=len(doc["skills"]))
    return doc


@router.post("/upload_resume", status_code=201, response_model=UploadOut, summary="Загрузить PDF/TXT резюме")
async def upload_resume_file(file: UploadFile = File(...)):
    content = await file.read(MAX_FILE_BYTES + 1)
    return await run_in_threadpool(_store_file, "resume", content, file.filename)


@router.post("/upload_resumes", status_code=201, summary="Пакетная загрузка до 200 резюме")
async def upload_resumes(files: list[UploadFile] = File(...)):
    if not 1 <= len(files) <= 200:
        raise HTTPException(422, "Пакет должен содержать от 1 до 200 файлов")
    started = time.perf_counter()
    results, errors = [], []
    for file in files:
        try:
            content = await file.read(MAX_FILE_BYTES + 1)
            results.append(await run_in_threadpool(_store_file, "resume", content, file.filename))
        except HTTPException as exc:
            errors.append({"filename": file.filename, "detail": exc.detail})
    duration = time.perf_counter() - started
    event(logger, "batch_upload_completed", count=len(results), errors=len(errors), duration_seconds=duration)
    return {"count": len(results), "results": results, "errors": errors, "duration_seconds": duration}


@router.get("/candidates", summary="Список резюме")
def list_resumes(limit: Optional[int] = Query(None, ge=1)):
    return mongo.list_resumes(limit)


@router.delete("/resumes/clear", summary="Удалить все резюме и связанные результаты")
def clear_resumes() -> dict:
    count = mongo.delete_documents("resumes")
    event(logger, "documents_deleted", kind="resumes", count=count)
    return {"deleted_count": count}


def _delete(kind, doc_id):
    try:
        count = mongo.delete_documents(kind, doc_id)
    except ValueError:
        count = 0
    if not count:
        _not_found("Документ не найден")
    event(logger, "document_deleted", kind=kind, document_id=doc_id)
    return {"deleted_count": count}


@router.delete("/vacancies/{vacancy_id}")
def delete_vacancy(vacancy_id: str):
    return _delete("vacancies", vacancy_id)


@router.delete("/resumes/{resume_id}")
def delete_resume(resume_id: str):
    return _delete("resumes", resume_id)


@router.get("/files/{kind}/{document_id}", summary="Скачать сохранённый оригинал без преобразований")
def original_file(kind: str, document_id: str):
    if kind not in ("vacancies", "resumes"):
        _not_found("Неизвестный вид документа")
    try:
        doc = mongo.get_original(kind, document_id)
    except ValueError:
        doc = None
    if not doc or "_original" not in doc:
        _not_found("Оригинал не найден")
    return Response(bytes(doc["_original"]), media_type="application/octet-stream",
                    headers={"X-Content-SHA256": doc["original_sha256"]})


@router.get("/config", summary="Версия и хэши параметров алгоритма")
def algorithm_config():
    return algorithm_manifest()


# --- test data generation --------------------------------------------------
import json
import os


@router.post("/import_superjob_vacancies", summary="Импорт вакансий SuperJob из JSON")
def import_superjob_vacancies() -> dict:
    if os.environ.get("ENABLE_EXTERNAL_IMPORTS", "false").lower() != "true":
        raise HTTPException(403, "Импорт внешних данных отключён в демонстрационном режиме")
    file_path = os.path.join(os.getcwd(), "data", "superjob_dataset.json")
    if not os.path.exists(file_path):
        file_path = "/app/data/superjob_dataset.json"

    if not os.path.exists(file_path):
        logger.error(f"Файл датасета {file_path} не найден")
        raise HTTPException(status_code=404, detail="Файл superjob_dataset.json не найден")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    inserted_count = 0
    for item in data:
        description_parts = []
        if item.get("responsibilities"):
            description_parts.append(f"Обязанности: {item['responsibilities']}")
        if item.get("requirements"):
            description_parts.append(f"Требования: {item['requirements']}")
        if item.get("company_description"):
            description_parts.append(f"О компании: {item['company_description']}")
        if not description_parts and item.get("raw_text"):
            description_parts.append(item["raw_text"])

        full_description = "\n\n".join(description_parts)

        doc = {
            "title": item.get("vacancy") or item.get("title", "Без названия"),
            "description": full_description,
            "skills": item.get("expected_skills", []),
            "city": item.get("city"),
            "company_name": item.get("company_name"),
            "experience": item.get("experience"),
            "education": item.get("education"),
            "min_salary": item.get("min_salary"),
            "max_salary": item.get("max_salary"),
            "_source": "superjob_manual",
            "_external_id": item.get("id"),
        }
        mongo.insert_vacancy(doc)
        inserted_count += 1

    logger.info(f"Успешно импортировано {inserted_count} вакансий из SuperJob")
    return {"status": "ok", "imported_vacancies": inserted_count}


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
            "skills": sorted(extract_skills(vac_data["text"])),
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
                "experience_years": parsed.get("experience_years"),
                "skills": parsed.get("skills", []),
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

@router.post("/score", response_model=ResultsOut, summary="Run scoring for a vacancy")
async def score(payload: ScoreRequest) -> dict:
    started = time.perf_counter()
    event(logger, "scoring_started", vacancy_id=payload.vacancy_id)
    try:
        out = await run_in_threadpool(
            score_vacancy,
            payload.vacancy_id,
            resume_ids=payload.resume_ids,
            limit_resumes=payload.limit_resumes,
            weights=payload.weights,
            critical_skills=set(payload.critical_skills) if payload.critical_skills is not None else None,
        )
    except ValueError as exc:
        if "critical skills" in str(exc):
            raise HTTPException(422, str(exc))
        _not_found(str(exc))
    event(logger, "scoring_completed", vacancy_id=payload.vacancy_id, count=len(out["results"]),
          duration_seconds=round(time.perf_counter() - started, 6))
    return {
        "vacancy_id": payload.vacancy_id,
        "count": len(out["results"]),
        "results": out["results"],
    }


@router.get("/results/{vacancy_id}", response_model=ResultsOut, summary="Ranked results for a vacancy")
def results(
    vacancy_id: str,
    top: Optional[int] = Query(default=None, ge=1),
) -> dict:
    try:
        scores = mongo.get_scores(vacancy_id, top=top)
    except ValueError:
        _not_found(f"vacancy {vacancy_id} not found")
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
    get_vacancy(payload.vacancy_id)
    get_resume(payload.resume_id)
    saved = mongo.save_feedback(payload.vacancy_id, payload.resume_id, payload.decision)
    event(logger, "feedback_saved", vacancy_id=payload.vacancy_id, resume_id=payload.resume_id, decision=payload.decision)
    return {"ok": True, **payload.model_dump(), "event": saved}


@router.get("/feedback", summary="Get current HR decision")
def get_feedback(vacancy_id: str, resume_id: str) -> dict:
    get_vacancy(vacancy_id)
    get_resume(resume_id)
    history = mongo.feedback_history(vacancy_id, resume_id)
    return {"vacancy_id": vacancy_id, "resume_id": resume_id,
            "decision": history[-1]["decision"] if history else None,
            "updated_at": history[-1]["updated_at"] if history else None, "history": history}


@router.get("/logs", summary="Получить последние логи сервера")
def get_server_logs(lines: int = Query(default=50, ge=1)) -> dict:
    if not LOG_PATH.exists():
        return {"logs": []}

    with LOG_PATH.open("r", encoding="utf-8") as f:
        all_lines = f.readlines()
        last_lines = all_lines[-lines:]

    parsed_logs = []
    for line in reversed(last_lines):
        try:
            parts = line.strip().split(" | ", 2)
            if len(parts) >= 3:
                timestamp = parts[0]
                level = parts[1]
                msg = parts[2]

                if msg.startswith("INFO: "): msg = msg[6:]
                if msg.startswith("WARN: "): msg = msg[6:]

                parsed_logs.append({
                    "timestamp": timestamp,
                    "type": "WARN" if level == "WARNING" else level,
                    "message": msg
                })
        except Exception:
            continue

    return {"logs": parsed_logs}


@router.delete("/logs/clear", summary="Очистить файл логов")
def clear_server_logs() -> dict:
    if LOG_PATH.exists():
        LOG_PATH.write_text("", encoding="utf-8")
    return {"status": "ok"}


@router.post("/import_superjob_resumes", summary="Импорт реальных резюме SuperJob из JSON")
def import_superjob_resumes() -> dict:
    if os.environ.get("ENABLE_EXTERNAL_IMPORTS", "false").lower() != "true":
        raise HTTPException(403, "Импорт внешних данных отключён в демонстрационном режиме")

    candidates_paths = [
        os.path.join(os.getcwd(), "data", "dataset_resume.json"),
        "/app/data/dataset_resume.json",
    ]
    file_path = next((p for p in candidates_paths if os.path.exists(p)), None)

    if not file_path:
        logger.warning(f"[WARN] Неверный путь: файл 'dataset_resume.json' не найден")
        raise HTTPException(status_code=404, detail="Файл dataset_resume.json не найден")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"[ERROR] Ошибка чтения JSON: {e}")
        raise HTTPException(status_code=500, detail=f"Сбой чтения JSON: {e}")

    inserted = 0
    for item in data:
        target_role = "Кандидат"
        if item.get("career_goal"):
            target_role = item["career_goal"].split(".")[0].replace("Ищет позицию", "").replace("Ищет работу",
                                                                                                "").strip(" :—")
        elif item.get("previously_held_positions"):
            target_role = item["previously_held_positions"][0].get("position", "Кандидат")

        text_parts = []
        if item.get("career_goal"):
            text_parts.append(f"Цель: {item['career_goal']}")
        if item.get("key_strengths"):
            text_parts.append(f"Ключевые навыки и сильные стороны: {item['key_strengths']}")

        positions = item.get("previously_held_positions", [])
        if positions:
            exp_text = "\n".join([
                                     f"- {p.get('position', '')} в {p.get('company', '')} ({p.get('period', '')}): {p.get('responsibilities', '')}"
                                     for p in positions])
            text_parts.append(f"Опыт работы:\n{exp_text}")
        elif not text_parts and item.get("raw_text"):
            text_parts.append(item["raw_text"])

        exp_raw = item.get("experience")
        if exp_raw:
            experience_value = f"Опыт работы: {exp_raw}"
        elif positions:
            periods = "; ".join(p.get("period", "") for p in positions if p.get("period"))
            experience_value = f"Опыт работы: {periods}" if periods else "Без опыта"
        elif item.get("raw_text"):
            experience_value = ""
        else:
            experience_value = "Без опыта"

        edu = item.get("education")
        if isinstance(edu, dict):
            text_parts.append(
                f"Образование: {edu.get('level', '')} {edu.get('institution', '')} ({edu.get('specialty', '')})")

        doc = {
            "title": (target_role[:80] if target_role else "Кандидат"),
            "specialization": (target_role[:80] if target_role else "Кандидат"),
            "experience": experience_value,
            "skills": item.get("expected_skills", []),
            "city": item.get("city"),
            "age": item.get("age"),
            "_synthetic": False,
            "_source": "superjob_dataset",
            "_external_id": item.get("id"),
            "_raw_text": "\n\n".join(text_parts),
        }
        mongo.insert_resume(doc)
        inserted += 1

    model_name = globals().get("NLP_MODEL_NAME", "JSON Import")
    logger.info(f"[INFO] Успешно импортировано {inserted} резюме из SuperJob")

    return {
        "status": "ok",
        "imported_resumes": inserted,
        "model_name": model_name,
    }
