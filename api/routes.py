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
    content = await file.read()
    file_size = len(content)

    if file_size == 0:
        logger.warning(f"WARN: Файл вакансии '{file.filename}' имеет нулевой размер (пустой текст или неверный путь)")
        raise HTTPException(status_code=400, detail="Файл пуст")

    extracted_text = extract_text_from_file(content, file.filename)
    text_len = len(extracted_text) if extracted_text else 0

    if text_len == 0:
        logger.warning(f"WARN: Не удалось извлечь текст вакансии из '{file.filename}'. Текст пуст.")
        raise HTTPException(status_code=400, detail="Текст вакансии не распознан")

    parsed = parse_raw_text_to_resume(extracted_text)
    skills = parsed.get("skills", [])
    title = file.filename.rsplit(".", 1)[0]

    vacancy_doc = {
        "title": title,
        "description": extracted_text,
        "skills": skills,
        "_source": "user_upload",
        "filename": file.filename,
    }

    vac_id = mongo.insert_vacancy(vacancy_doc)

    # INFO-лог с детализацией (имя модели, длина, сколько и каких навыков)
    logger.info(
        f"INFO: [NLP: ru_core_news_sm] Вакансия '{file.filename}' сохранена. "
        f"Длина текста: {text_len} симв. "
        f"Извлечено навыков ({len(skills)} шт.): {', '.join(skills) if skills else 'Нет'}"
    )

    return {
        "vacancy_id": str(vac_id),
        "filename": file.filename,
        "file_size": file_size,
        "text_length": text_len,
        "title": title,
        "skills_count": len(skills),
        "skills": skills,
        "status": "success"
    }


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


@router.post("/upload_resume", status_code=status.HTTP_201_CREATED, summary="Загрузить файл резюме")
async def upload_resume_file(file: UploadFile = File(...)):
    content = await file.read()
    file_size = len(content)

    if file_size == 0:
        logger.warning(f"WARN: Файл '{file.filename}' имеет нулевой размер (пустой текст или неверный путь)")
        raise HTTPException(status_code=400, detail="Файл пуст")

    extracted_text = extract_text_from_file(content, file.filename)
    text_len = len(extracted_text) if extracted_text else 0

    if text_len == 0:
        logger.warning(f"WARN: Не удалось извлечь текст из файла '{file.filename}'. Текст пуст.")
        raise HTTPException(status_code=400, detail="Текст в файле не обнаружен")

    parsed = parse_raw_text_to_resume(extracted_text)
    skills = parsed.get("skills", [])
    title = parsed.get("title", "") or "Кандидат"

    resume_doc = {
        "title": title,
        "specialization": parsed.get("specialization", ""),
        "experience": parsed.get("experience", ""),
        "skills": skills,
        "tags": parsed.get("tags", []),
        "_synthetic": False,
        "_source": "user_upload",
        "_raw_text": extracted_text,
        "filename": file.filename,
    }

    resume_id = mongo.insert_resume(resume_doc)

    # INFO-лог с детализацией (имя модели, длина, сколько и каких навыков)
    logger.info(
        f"INFO: [NLP: ru_core_news_sm] Резюме '{file.filename}' сохранено. "
        f"Длина текста: {text_len} симв. "
        f"Извлечено навыков ({len(skills)} шт.): {', '.join(skills) if skills else 'Нет'}"
    )

    return {
        "resume_id": str(resume_id),
        "filename": file.filename,
        "file_size": file_size,
        "text_length": text_len,
        "title": title,
        "skills_count": len(skills),
        "skills": skills,
        "status": "success"
    }

@router.delete("/resumes/clear", summary="Удалить все резюме")
def clear_resumes() -> dict:
    res = mongo._coll(mongo.COLL_RESUMES).delete_many({})
    mongo._coll(mongo.COLL_SCORES).delete_many({})
    logger.info(f"Удалено резюме: {res.deleted_count}")
    return {"deleted_count": res.deleted_count}


# --- test data generation --------------------------------------------------
import json
import os


@router.post("/import_superjob_vacancies", summary="Импорт вакансий SuperJob из JSON")
def import_superjob_vacancies() -> dict:
    file_path = os.path.join(os.getcwd(), "data", "superjob_dataset.json")
    if not os.path.exists(file_path):
        # Если запущено внутри контейнера /app
        file_path = "/app/data/superjob_dataset.json"

    if not os.path.exists(file_path):
        logger.error(f"Файл датасета {file_path} не найден")
        raise HTTPException(status_code=404, detail="Файл superjob_dataset.json не найден")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    inserted_count = 0
    for item in data:
        # Собираем полное текстовое описание для скорера
        description_parts = []
        if item.get("responsibilities"):
            description_parts.append(f"Обязанности: {item['responsibilities']}")
        if item.get("requirements"):
            description_parts.append(f"Требования: {item['requirements']}")
        if item.get("company_description"):
            description_parts.append(f"О компании: {item['company_description']}")

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


@router.get("/logs", summary="Получить последние логи сервера")
def get_server_logs(lines: int = Query(default=50, ge=1)) -> dict:
    log_file = os.path.join(os.getcwd(), "app.log")
    if not os.path.exists(log_file):
        return {"logs": []}

    with open(log_file, "r", encoding="utf-8") as f:
        # Читаем все строки и забираем только последние
        all_lines = f.readlines()
        last_lines = all_lines[-lines:]

    parsed_logs = []
    # Переворачиваем, чтобы самые свежие логи были сверху
    for line in reversed(last_lines):
        try:
            parts = line.strip().split(" | ", 2)
            if len(parts) >= 3:
                timestamp = parts[0]
                level = parts[1]
                msg = parts[2]

                # Убираем дублирование INFO:/WARN:, если они остались в тексте
                if msg.startswith("INFO: "): msg = msg[6:]
                if msg.startswith("WARN: "): msg = msg[6:]

                # В Python предупреждения пишутся как WARNING, маппим в WARN для фронта
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
    log_file = os.path.join(os.getcwd(), "app.log")
    if os.path.exists(log_file):
        open(log_file, 'w').close()  # Очищаем содержимое файла
    return {"status": "ok"}


@router.post("/import_superjob_resumes", summary="Импорт реальных резюме SuperJob из JSON")
def import_superjob_resumes() -> dict:
    import json
    import os

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

        edu = item.get("education")
        if isinstance(edu, dict):
            text_parts.append(
                f"Образование: {edu.get('level', '')} {edu.get('institution', '')} ({edu.get('specialty', '')})")

        doc = {
            "title": (target_role[:80] if target_role else "Кандидат"),
            "specialization": (target_role[:80] if target_role else "Кандидат"),
            "experience": item.get("experience") or "Без опыта",
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