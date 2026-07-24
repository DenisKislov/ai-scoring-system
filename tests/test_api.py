"""Smoke test for the FastAPI layer — hermetic, no MongoDB required.

The data layer (``db.mongo``) and the scorer bridge (``score_vacancy``) are
stubbed via monkeypatch, so this runs anywhere without a running Mongo or
seeded data. It checks the HTTP contract: status codes, pydantic validation,
and that each endpoint forwards to the right backend function.

Run: ``pytest tests/test_api.py -q`` (or ``python tests/test_api.py``).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymongo.errors  # noqa: E402

import api.routes as routes  # noqa: E402
import db.mongo as mongo  # noqa: E402
from api.main import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


# --- fakes -----------------------------------------------------------------

class _FakeAdmin:
    @staticmethod
    def command(name="ping"):
        return {"ok": 1}


class _FakeClient:
    admin = _FakeAdmin()


def _client(monkeypatch, **stubs) -> TestClient:
    """Build a TestClient with selected ``db.mongo``/route functions stubbed."""
    monkeypatch.setattr(mongo, "get_client", lambda: _FakeClient())
    for name, fn in stubs.items():
        if name == "score_vacancy":
            monkeypatch.setattr(routes, "score_vacancy", fn)
        else:
            monkeypatch.setattr(mongo, name, fn)
    return TestClient(create_app())


def _ranked():
    return {
        "vacancy": {"_id": "v1", "title": "Python developer"},
        "results": [
            {"candidate_id": "r1", "score": 80, "matched_skills": ["Python"]},
            {"candidate_id": "r2", "score": 40, "matched_skills": []},
        ],
    }


# --- tests -----------------------------------------------------------------

def test_health_ok(monkeypatch):
    r = _client(monkeypatch).get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_vacancy_201(monkeypatch):
    seen = {}
    def _insert(doc):
        seen.update(doc)
        return "newvacid"
    c = _client(monkeypatch, insert_vacancy=_insert)
    r = c.post("/vacancies", json={"title": "ML engineer", "skills": ["Python", "PyTorch"]})
    assert r.status_code == 201
    body = r.json()
    assert body["_id"] == "newvacid"
    assert body["title"] == "ML engineer"
    assert seen["title"] == "ML engineer"  # forwarded to the data layer


def test_create_vacancy_invalid_422(monkeypatch):
    c = _client(monkeypatch, insert_vacancy=lambda doc: "x")
    r = c.post("/vacancies", json={"skills": ["Python"]})  # missing required title
    assert r.status_code == 422


def test_create_candidate_201(monkeypatch):
    c = _client(monkeypatch, insert_resume=lambda doc: "newresid")
    r = c.post("/candidates", json={"title": "Data Scientist", "experience": "Опыт работы: 5 лет"})
    assert r.status_code == 201
    assert r.json()["_id"] == "newresid"


def test_score_returns_ranked(monkeypatch):
    called = {}
    def _score(vid, resume_ids=None, limit_resumes=None, weights=None):
        called["args"] = (vid, resume_ids, limit_resumes, weights)
        return _ranked()
    c = _client(monkeypatch, score_vacancy=_score)
    r = c.post("/score", json={"vacancy_id": "v1", "limit_resumes": 20})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert body["results"][0]["score"] == 80  # ranked descending
    assert called["args"][0] == "v1" and called["args"][2] == 20  # forwarded


def test_score_not_found_404(monkeypatch):
    def _score(*a, **k):
        raise ValueError("vacancy nope not found")
    c = _client(monkeypatch, score_vacancy=_score)
    assert c.post("/score", json={"vacancy_id": "nope"}).status_code == 404


def test_results_unknown_vacancy_404(monkeypatch):
    c = _client(monkeypatch, get_scores=lambda vid, top=None: [], get_vacancy=lambda vid: None)
    assert c.get("/results/nope").status_code == 404


def test_results_not_scored_returns_empty(monkeypatch):
    # vacancy exists but has no scores yet -> 200 with empty results
    c = _client(monkeypatch, get_scores=lambda vid, top=None: [], get_vacancy=lambda vid: {"_id": vid})
    r = c.get("/results/v1")
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_get_vacancy_bad_objectid_404(monkeypatch):
    def _raise(vid):
        raise ValueError("not an ObjectId")
    c = _client(monkeypatch, get_vacancy=_raise)
    assert c.get("/vacancies/zzz").status_code == 404


def test_feedback_ok(monkeypatch):
    seen = {}
    def _save(vid, rid, decision):
        seen.update(vacancy_id=vid, resume_id=rid, decision=decision)
    c = _client(monkeypatch, save_feedback=_save)
    r = c.post("/feedback", json={"vacancy_id": "v1", "resume_id": "r1", "decision": "yes"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert seen["decision"] == "yes"


def test_feedback_invalid_decision_422(monkeypatch):
    c = _client(monkeypatch, save_feedback=lambda *a: None)
    r = c.post("/feedback", json={"vacancy_id": "v1", "resume_id": "r1", "decision": "maybe"})
    assert r.status_code == 422


def test_db_down_returns_503(monkeypatch):
    # Any pymongo error must surface as 503, never a bare 500.
    def _boom():
        raise pymongo.errors.ServerSelectionTimeoutError("no mongo")
    monkeypatch.setattr(mongo, "get_client", _boom)
    c = TestClient(create_app())
    assert c.get("/vacancies").status_code == 503


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
