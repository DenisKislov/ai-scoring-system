"""FastAPI application — thin HTTP layer over ``db.mongo`` + ``scorer.service``.

Run from the project root::

    uvicorn api.main:app --reload        # interactive dev
    python -m api                         # same, as a module

OpenAPI docs are served at ``http://localhost:8000/docs``.

CORS: ``API_CORS_ORIGINS`` (comma-separated) defaults to ``*`` — Streamlit
(:8501) and the API (:8000) live on different ports, so cross-origin requests
must be allowed. When the origins are ``*`` we disable credentials (per the
CORS spec, ``*`` + credentials is invalid).
"""
from __future__ import annotations



import os

import pymongo.errors
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routes import router


def _cors_origins() -> list:
    raw = os.environ.get("API_CORS_ORIGINS", "*")
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI-скоринг кандидатов — API",
        description=(
            "HTTP-слой над скорером и MongoDB: загрузка вакансий/резюме, "
            "запуск скоринга, ранжированные результаты, фидбек HR."
        ),
        version="0.1.0",
    )

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
        # Connection down / MongoDB not running — surface a clean 503 rather
        # than an opaque 500.
        return JSONResponse(
            status_code=503,
            content={"detail": f"database error: {exc.__class__.__name__}"},
        )

    app.include_router(router)
    return app


app = create_app()
