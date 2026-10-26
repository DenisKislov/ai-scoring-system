"""FastAPI application — thin HTTP layer over ``db.mongo`` + ``scorer.service``.

Run from the project root::

    uvicorn api.main:app --reload        # interactive dev
    python -m api                         # same, as a module

OpenAPI docs are served at ``http://localhost:8000/docs``.

На старте приложения один раз подготавливается порог отбора кандидатов
(см. ``api.threshold_service``): если в БД его нет — считаем по датасетам
``data/superjob_dataset.json`` и ``data/dataset_resume.json`` и сохраняем;
если есть — используем сохранённое значение. Фронт забирает его через
``GET /threshold``.

CORS: ``API_CORS_ORIGINS`` (comma-separated) defaults to ``*`` — React
(:3000) and the API (:8000) live on different ports, so cross-origin requests
must be allowed. When the origins are ``*`` we disable credentials (per the
CORS spec, ``*`` + credentials is invalid).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import pymongo.errors
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from uuid import uuid4

from .logger import setup_logger, event
from scorer.transport import ScorerUnavailable
from .routes import router
from .threshold_service import ensure_threshold_initialized

logger = setup_logger("api.main")


def _cors_origins() -> list:
    raw = os.environ.get("API_CORS_ORIGINS", "*")
    return [o.strip() for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    # Порог отбора кандидатов: если в БД нет — считаем по датасетам и
    # сохраняем; если есть — используем сохранённый. Ошибки не валят
    # приложение — лог покажет причину, а GET /threshold вернёт null.
    logger.info("[Startup] Подготовка порога отбора кандидатов...")
    try:
        ensure_threshold_initialized()
    except Exception as exc:  # noqa: BLE001 — startup не должен падать из-за порога
        logger.warning(f"[Startup] Не удалось подготовить порог: {exc}")

    yield

    # --- shutdown ---
    logger.info("[Shutdown] API остановлено")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI-скоринг кандидатов — API",
        description=(
            "HTTP-слой над скорером и MongoDB: загрузка вакансий/резюме, "
            "запуск скоринга, ранжированные результаты, фидбек HR."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    app.state.instance_id = str(uuid4())

    @app.get("/status", summary="Process liveness without requiring MongoDB")
    def process_status():
        return {"status": "running", "instance_id": app.state.instance_id, "version": "1.0.0"}

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        event(logger, "validation_error", path=request.url.path, count=len(exc.errors()))
        return await request_validation_exception_handler(request, exc)

    origins = _cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials="*" not in origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(pymongo.errors.PyMongoError)
    async def _db_unavailable(_: Request, exc: pymongo.errors.PyMongoError) -> JSONResponse:
        event(logger, "database_error", path=_.url.path, error=type(exc).__name__)
        # Connection down / MongoDB not running — surface a clean 503 rather
        # than an opaque 500.
        return JSONResponse(
            status_code=503,
            content={"detail": f"database error: {exc.__class__.__name__}"},
        )

    @app.exception_handler(ScorerUnavailable)
    async def _scorer_unavailable(_: Request, exc: ScorerUnavailable):
        event(logger, "scorer_error", message=str(exc))
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    app.include_router(router)
    return app


app = create_app()
