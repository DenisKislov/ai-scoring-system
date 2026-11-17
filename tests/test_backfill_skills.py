import pytest

mongomock = pytest.importorskip("mongomock")

from db import mongo  # noqa: E402
from scripts.backfill_skills import backfill  # noqa: E402
from scorer import extract_skills  # noqa: E402


@pytest.fixture
def mock_db(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    return mongo.get_db()


def _insert(db, doc):
    return db[mongo.COLL_RESUMES].insert_one(doc).inserted_id


def test_backfill_updates_stale_skills(mock_db):
    text = "Опыт работы: 3 года. Навыки: Python, PostgreSQL, Docker."
    rid = _insert(mock_db, {"_raw_text": text, "_source": "user_upload",
                            "skills": ["Python"], "tags": ["Python"], "title": "Канд"})
    summary = backfill(dry_run=False)
    assert summary["updated"] == 1
    doc = mock_db[mongo.COLL_RESUMES].find_one({"_id": rid})
    expected = extract_skills(text)
    assert set(doc["skills"]) == expected == set(doc["tags"])
    assert "PostgreSQL" in expected


def test_dry_run_changes_nothing(mock_db):
    _insert(mock_db, {"_raw_text": "Навыки: Python, PostgreSQL.", "_source": "user_upload",
                      "skills": ["Python"], "tags": ["Python"]})
    summary = backfill(dry_run=True)
    assert summary["updated"] == 1 and summary["plan"][0]["added"]
    doc = mock_db[mongo.COLL_RESUMES].find_one({})
    assert doc["skills"] == ["Python"]  # не изменён


def test_superjob_import_untouched_by_default(mock_db):
    _insert(mock_db, {"_raw_text": "Навыки: Python, PostgreSQL.",
                      "_source": "superjob_dataset", "skills": ["Python"]})
    summary = backfill(dry_run=False)
    assert summary["updated"] == 0
    assert mock_db[mongo.COLL_RESUMES].find_one({})["skills"] == ["Python"]


def test_all_sources_overwrites_when_asked(mock_db):
    _insert(mock_db, {"_raw_text": "Навыки: Python, PostgreSQL.",
                      "_source": "superjob_dataset", "skills": ["Python"]})
    assert backfill(dry_run=False, all_sources=True)["updated"] == 1


def test_docs_without_raw_text_ignored(mock_db):
    _insert(mock_db, {"_source": "user_upload", "skills": ["Python"],
                      "experience": "Опыт работы: 2 года"})
    assert backfill(dry_run=False)["updated"] == 0


def test_fresh_skills_unchanged(mock_db):
    text = "Опыт работы: 3 года. Навыки: Python, PostgreSQL, Docker."
    _insert(mock_db, {"_raw_text": text, "_source": "user_upload",
                      "skills": sorted(extract_skills(text))})
    summary = backfill(dry_run=False)
    assert summary["updated"] == 0 and summary["unchanged"] == 1


def test_vacancy_refresh_preserves_critical_selection_and_feedback(mock_db):
    vacancy_id = mongo._coll(mongo.COLL_VACANCIES).insert_one({
        'description': 'Навыки: Python, PostgreSQL.', '_source': 'user_upload',
        'skills': ['Python'], 'critical_skills': ['Docker']}).inserted_id
    mock_db[mongo.COLL_SCORES].insert_one({'vacancy_id': str(vacancy_id), 'score': 1})
    mock_db[mongo.COLL_FEEDBACK].insert_one({'vacancy_id': str(vacancy_id), 'decision': 'yes'})
    summary = backfill(dry_run=False, kind='both')
    assert summary['updated'] == 1
    doc = mock_db[mongo.COLL_VACANCIES].find_one({'_id': vacancy_id})
    assert set(doc['skills']) == {'Python', 'PostgreSQL', 'Docker'}
    assert doc['critical_skills'] == ['Docker']
    assert mock_db[mongo.COLL_SCORES].count_documents({}) == 0
    assert mock_db[mongo.COLL_FEEDBACK].count_documents({}) == 1
    assert backfill(dry_run=False, kind='both')['updated'] == 0
