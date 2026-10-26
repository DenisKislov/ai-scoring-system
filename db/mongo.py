import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pymongo
from bson import ObjectId
from bson.errors import InvalidId

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://mongo:27017")
MONGO_DB = os.environ.get("MONGO_DB", "gb_parse")

COLL_VACANCIES = "hh"
COLL_RESUMES = "hh_resumes"
COLL_SCORES = "hh_scores"
COLL_FEEDBACK = "hh_feedback"

_client: Optional[pymongo.MongoClient] = None


def get_client() -> pymongo.MongoClient:
    global _client
    if _client is None:
        _client = pymongo.MongoClient(MONGO_URI, tz_aware=True,
                                     serverSelectionTimeoutMS=int(os.environ.get("MONGO_TIMEOUT_MS", "2000")), connectTimeoutMS=2000)
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
    if doc is not None and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    if doc is not None:
        # BSON dates are UTC even when an older client returns naive datetimes.
        # Without an offset the browser interprets them as local wall time.
        for key, value in doc.items():
            if isinstance(value, datetime) and value.tzinfo is None:
                doc[key] = value.replace(tzinfo=timezone.utc)
    return doc


def count_vacancies() -> int:
    return _coll(COLL_VACANCIES).count_documents({})


def list_vacancies(limit: Optional[int] = None) -> List[Dict]:
    cur = _coll(COLL_VACANCIES).find({}, {"_original": 0}).limit(limit or 0)
    return [_str_id(d) for d in cur]


def get_vacancy(vacancy_id: str) -> Optional[Dict]:
    return _str_id(_coll(COLL_VACANCIES).find_one({"_id": _to_oid(vacancy_id)}, {"_original": 0}))


def insert_vacancy(doc: Dict) -> str:
    result = _coll(COLL_VACANCIES).insert_one(doc)
    return str(result.inserted_id)


def count_resumes() -> int:
    return _coll(COLL_RESUMES).count_documents({})


def list_resumes(limit: Optional[int] = None) -> List[Dict]:
    cur = _coll(COLL_RESUMES).find({}, {"_original": 0}).limit(limit or 0)
    return [_str_id(d) for d in cur]


def get_resume(resume_id: str) -> Optional[Dict]:
    return _str_id(_coll(COLL_RESUMES).find_one({"_id": _to_oid(resume_id)}, {"_original": 0}))


def insert_resume(doc: Dict) -> str:
    result = _coll(COLL_RESUMES).insert_one(doc)
    return str(result.inserted_id)


def save_scores(vacancy_id: str, ranked: List[Dict]) -> int:
    vacancy_id = str(_to_oid(vacancy_id))
    now = datetime.now(timezone.utc)
    coll = _coll(COLL_SCORES)
    coll.create_index([("vacancy_id", 1), ("resume_id", 1)], unique=True)
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
            "missing_critical": r.get("missing_critical", []),
            "rank_percentile": r.get("rank_percentile"),
            "experience_years": r.get("experience_years"),
            "updated_at": now,
        }
        for key in ("keyword_contribution", "cosine_contribution", "matched_critical",
                    "critical_skills", "vacancy_skills", "algorithm_fingerprint", "weights", "position"):
            if key in r:
                doc[key] = r[key]
        doc["candidate_id"] = resume_id
        ops.append(
            pymongo.UpdateOne(
                {"vacancy_id": vacancy_id, "resume_id": resume_id},
                {"$set": doc, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
        )
    if ops:
        coll.bulk_write(ops, ordered=True)
        # A partial rerun may retain scores only from the same scoring setup.
        # Otherwise GET /results silently mixes incomparable rankings.
        context = ranked[0]
        coll.delete_many({'vacancy_id': vacancy_id, '$or': [
            {key: {'$ne': context.get(key)}}
            for key in ('algorithm_fingerprint', 'weights', 'critical_skills')
        ]})
    return len(ops)


def get_scores(vacancy_id: str, top: Optional[int] = None) -> List[Dict]:
    vacancy_id = str(_to_oid(vacancy_id))
    cur = (
        _coll(COLL_SCORES)
        .find({"vacancy_id": vacancy_id})
        .sort([("score", pymongo.DESCENDING), ("experience_years", pymongo.DESCENDING), ("resume_id", 1)])
        .limit(top or 0)
    )
    return [_str_id(d) for d in cur]


def save_feedback(vacancy_id: str, resume_id: str, decision: str) -> Dict:
    vacancy_id, resume_id = str(_to_oid(vacancy_id)), str(_to_oid(resume_id))
    if decision not in ("yes", "no"):
        raise ValueError("decision must be yes or no")
    now = datetime.now(timezone.utc)
    event = {"vacancy_id": vacancy_id, "resume_id": resume_id,
             "decision": decision, "updated_at": now, "created_at": now}
    event["_id"] = str(_coll(COLL_FEEDBACK).insert_one(event).inserted_id)
    return event


def feedback_history(vacancy_id: str, resume_id: str) -> List[Dict]:
    vacancy_id, resume_id = str(_to_oid(vacancy_id)), str(_to_oid(resume_id))
    events = _coll(COLL_FEEDBACK).find({"vacancy_id": vacancy_id, "resume_id": resume_id})
    return [_str_id(e) for e in events.sort([("updated_at", 1), ("_id", 1)])]


def get_feedback(vacancy_id: str, resume_id: str) -> Optional[str]:
    history = feedback_history(vacancy_id, resume_id)
    return history[-1]["decision"] if history else None


def update_critical_skills(vacancy_id: str, skills: List[str]) -> bool:
    vacancy_id = str(_to_oid(vacancy_id))
    result = _coll(COLL_VACANCIES).update_one(
        {"_id": _to_oid(vacancy_id)}, {"$set": {"critical_skills": sorted(set(skills))}})
    if result.modified_count:
        _coll(COLL_SCORES).delete_many({'vacancy_id': vacancy_id})
    return result.matched_count > 0


def get_original(kind: str, doc_id: str) -> Optional[Dict]:
    coll = COLL_RESUMES if kind == "resumes" else COLL_VACANCIES
    return _coll(coll).find_one({"_id": _to_oid(doc_id)}, {"_original": 1, "filename": 1, "original_sha256": 1})


def delete_documents(kind: str, doc_id: Optional[str] = None) -> int:
    if doc_id is not None:
        doc_id = str(_to_oid(doc_id))
    coll, field = ((COLL_RESUMES, "resume_id") if kind == "resumes"
                   else (COLL_VACANCIES, "vacancy_id"))
    query = {"_id": _to_oid(doc_id)} if doc_id is not None else {}
    # Related objects are removed first, so retries are safe after a partial DB failure.
    related = {field: doc_id} if doc_id is not None else {}
    _coll(COLL_SCORES).delete_many(related)
    _coll(COLL_FEEDBACK).delete_many(related)
    return _coll(coll).delete_many(query).deleted_count
