"""MongoDB access layer for the candidate-scoring pipeline.

Reads vacancies/resumes from the same collections the Scrapy parser writes to
(``hh`` and ``hh_resumes``) and persists scoring results to ``hh_scores``.
Connection is configured via environment, falling back to the parser's defaults
(``mongodb://localhost:27017``, db ``gb_parse``).

The Scrapy spider and the synthetic seeder both emit documents in the hh.ru
item shape, so this layer is agnostic to where the data came from — swapping
synthetic seed for a live crawl needs no code change here.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pymongo
from bson import ObjectId
from bson.errors import InvalidId

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "gb_parse")

COLL_VACANCIES = "hh"
COLL_RESUMES = "hh_resumes"
COLL_SCORES = "hh_scores"
COLL_FEEDBACK = "hh_feedback"

_client: Optional[pymongo.MongoClient] = None


def get_client() -> pymongo.MongoClient:
    """Lazily create and reuse a single client (connection-pooled)."""
    global _client
    if _client is None:
        _client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return _client


def get_db():
    return get_client()[MONGO_DB]


def _coll(name: str):
    return get_db()[name]


def _to_oid(doc_id: str) -> ObjectId:
    try:
        return ObjectId(doc_id)
    except (InvalidId, TypeError):
        raise ValueError(f"not an ObjectId: {doc_id!r}")


def _str_id(doc: Optional[Dict]) -> Optional[Dict]:
    """Expose ``_id`` as a plain string for JSON-friendly downstream use."""
    if doc is not None and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# --- vacancies -------------------------------------------------------------

def count_vacancies() -> int:
    return _coll(COLL_VACANCIES).count_documents({})


def list_vacancies(limit: Optional[int] = None) -> List[Dict]:
    cur = _coll(COLL_VACANCIES).find().limit(limit or 0)
    return [_str_id(d) for d in cur]


def get_vacancy(vacancy_id: str) -> Optional[Dict]:
    return _str_id(_coll(COLL_VACANCIES).find_one({"_id": _to_oid(vacancy_id)}))


def insert_vacancy(doc: Dict) -> str:
    """Insert a vacancy item and return its ``_id`` as a string.

    The caller supplies the hh.ru item shape (``title``, ``description``,
    ``skills``, …). Used by the FastAPI ``POST /vacancies`` endpoint.
    """
    result = _coll(COLL_VACANCIES).insert_one(doc)
    return str(result.inserted_id)


# --- resumes ---------------------------------------------------------------

def count_resumes() -> int:
    return _coll(COLL_RESUMES).count_documents({})


def list_resumes(limit: Optional[int] = None) -> List[Dict]:
    cur = _coll(COLL_RESUMES).find().limit(limit or 0)
    return [_str_id(d) for d in cur]


def get_resume(resume_id: str) -> Optional[Dict]:
    return _str_id(_coll(COLL_RESUMES).find_one({"_id": _to_oid(resume_id)}))


def insert_resume(doc: Dict) -> str:
    """Insert a resume item and return its ``_id`` as a string.

    Used by the FastAPI ``POST /candidates`` endpoint. Synthetic and live
    crawls write the same shape, so the scorer is agnostic to the source.
    """
    result = _coll(COLL_RESUMES).insert_one(doc)
    return str(result.inserted_id)


# --- scores ----------------------------------------------------------------

def save_scores(vacancy_id: str, ranked: List[Dict]) -> int:
    """Upsert scoring results for *vacancy_id*.

    Keyed by ``(vacancy_id, resume_id)`` so re-running the scorer replaces
    rather than duplicates. Returns the number of documents written.
    """
    now = datetime.now(timezone.utc)
    coll = _coll(COLL_SCORES)
    ops = []
    for r in ranked:
        resume_id = r.get("resume_id") or r.get("candidate_id")
        doc = {
            "vacancy_id": vacancy_id,
            "resume_id": resume_id,
            "score": r.get("score"),
            "raw_score": r.get("raw_score"),
            "keyword_score": r.get("keyword_score"),
            "cosine_sim": r.get("cosine_sim"),
            "matched_skills": r.get("matched_skills", []),
            "missing_skills": r.get("missing_skills", []),
            "rank_percentile": r.get("rank_percentile"),
            "experience_years": r.get("experience_years"),
            "updated_at": now,
        }
        ops.append(
            pymongo.UpdateOne(
                {"vacancy_id": vacancy_id, "resume_id": resume_id},
                {"$set": doc, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
        )
    if ops:
        coll.bulk_write(ops)
    return len(ops)


def get_scores(vacancy_id: str, top: Optional[int] = None) -> List[Dict]:
    cur = (
        _coll(COLL_SCORES)
        .find({"vacancy_id": vacancy_id})
        .sort("score", pymongo.DESCENDING)
        .limit(top or 0)
    )
    return [_str_id(d) for d in cur]


# --- feedback --------------------------------------------------------------

def save_feedback(vacancy_id: str, resume_id: str, decision: str) -> None:
    """Record an HR decision for a (vacancy, resume) pair.

    ``decision`` ∈ {"yes", "no"} (the "Да/Нет" the customer specified).
    Upserted so re-deciding overwrites the previous verdict.
    """
    if decision not in ("yes", "no"):
        raise ValueError(f"decision must be 'yes' or 'no', got {decision!r}")
    now = datetime.now(timezone.utc)
    _coll(COLL_FEEDBACK).update_one(
        {"vacancy_id": vacancy_id, "resume_id": resume_id},
        {"$set": {"decision": decision, "updated_at": now}, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )


def get_feedback(vacancy_id: str, resume_id: str) -> Optional[str]:
    """Return the recorded decision ("yes"/"no") or ``None`` if not yet decided."""
    doc = _coll(COLL_FEEDBACK).find_one({"vacancy_id": vacancy_id, "resume_id": resume_id})
    return doc.get("decision") if doc else None
