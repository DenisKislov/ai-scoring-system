"""Сервис хранения и пересчёта порога отбора кандидатов.

Порог — единственное число в [0, 1], хранится в MongoDB в коллекции
``system_config`` под документом ``_id="skill_overlap_threshold"``.
Структура документа:

    {
      "_id": "skill_overlap_threshold",
      "value": 0.247,           # сам порог
      "updated_at": "2026-...",  # ISO-8601 UTC
      "source_vacancies": ".../superjob_dataset.json",
      "source_resumes":   ".../dataset_resume.json",
      "n_vacancies": 101,
      "n_resumes":   100
    }
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from db import mongo
from scorer.auto_threshold import compute_dataset_threshold

logger = logging.getLogger("api.threshold")

CONFIG_COLLECTION = "system_config"
THRESHOLD_DOC_ID = "skill_overlap_threshold"

# Относительные пути внутри проекта / контейнера.
_VACANCIES_CANDIDATES = (
    os.path.join("data", "superjob_dataset.json"),
    "/app/data/superjob_dataset.json",
)
_RESUMES_CANDIDATES = (
    os.path.join("data", "dataset_resume.json"),
    "/app/data/dataset_resume.json",
)


def _config_coll():
    return mongo._coll(CONFIG_COLLECTION)


def _resolve_path(candidates) -> Optional[str]:
    for rel in candidates:
        p = os.path.join(os.getcwd(), rel) if not rel.startswith("/") else rel
        if os.path.exists(p):
            return p
    return None


def get_threshold_doc() -> Optional[dict]:
    """Возвращает документ порога из БД или None."""
    return _config_coll().find_one({"_id": THRESHOLD_DOC_ID})


def get_threshold_value() -> Optional[float]:
    """Удобный шорткат: только число, без обёртки."""
    doc = get_threshold_doc()
    if not doc:
        return None
    v = doc.get("value")
    return float(v) if v is not None else None


def _save(doc: dict) -> dict:
    _config_coll().replace_one({"_id": THRESHOLD_DOC_ID}, doc, upsert=True)
    return doc


def recompute_threshold(*, force: bool = False) -> dict:
    """Считает порог по датасетам и сохраняет в БД.

    ``force=False`` — если порог уже есть в БД, ничего не делает и возвращает
    существующий документ. ``force=True`` — всегда пересчитывает.
    """
    existing = get_threshold_doc()
    if existing and not force:
        return existing

    vac_path = _resolve_path(_VACANCIES_CANDIDATES)
    res_path = _resolve_path(_RESUMES_CANDIDATES)

    if not vac_path or not res_path:
        raise FileNotFoundError(
            f"Датасеты для расчёта порога не найдены: "
            f"vacancies={vac_path}, resumes={res_path}"
        )

    value, n_vac, n_res = compute_dataset_threshold(vac_path, res_path)

    doc = {
        "_id": THRESHOLD_DOC_ID,
        "value": value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source_vacancies": vac_path,
        "source_resumes": res_path,
        "n_vacancies": n_vac,
        "n_resumes": n_res,
    }
    _save(doc)
    logger.info(
        f"[Threshold] Порог={value:.4f} по {n_vac} вакансиям и {n_res} резюме "
        f"(vacancies={vac_path}, resumes={res_path})"
    )
    return doc


def ensure_threshold_initialized() -> None:
    """Гарантирует, что в БД есть порог.

    Вызывается один раз при старте API. Если порог уже сохранён — ничего
    не делает. Если нет — считает по датасетам и сохраняет. Ошибки не
    валят приложение: логируем warning и продолжаем без порога (фронт
    в этом случае покажет сообщение).
    """
    try:
        doc = get_threshold_doc()
        if doc:
            logger.info(
                f"[Threshold] Использую сохранённый порог: "
                f"{doc.get('value')} (от {doc.get('updated_at')})"
            )
            return
        logger.info("[Threshold] Порога нет в БД — вычисляю при старте...")
        recompute_threshold(force=False)
    except Exception as e:  # noqa: BLE001 — хотим поймать всё, включая проблемы с файлами
        logger.warning(f"[Threshold] Не удалось подготовить порог при старте: {e}")