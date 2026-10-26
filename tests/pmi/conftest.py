"""Hermetic API/storage integration. Real Docker faults are a separate command."""
import inspect
import mongomock
import pytest
from fastapi.testclient import TestClient
from api.main import create_app
from db import mongo


@pytest.fixture
def client(monkeypatch):
    import mongomock.collection
    # mongomock 4.3 predates PyMongo's optional sort argument on bulk updates.
    original = mongomock.collection.BulkOperationBuilder.add_update
    def add_update(self, selector, doc, multi=False, upsert=False, collation=None, array_filters=None, hint=None, sort=None):
        return original(self, selector, doc, multi, upsert, collation, array_filters, hint)
    if 'sort' not in inspect.signature(original).parameters:
        monkeypatch.setattr(mongomock.collection.BulkOperationBuilder, 'add_update', add_update)
    monkeypatch.setattr(mongo, '_client', mongomock.MongoClient())
    monkeypatch.delenv('SCORER_URL', raising=False)
    return TestClient(create_app())


@pytest.fixture
def pair(client):
    vacancy = client.post('/vacancies', json={
        'title':'Разработчик', 'description':'Нужны Python, PostgreSQL, Docker, Git.',
        'skills':['Python','PostgreSQL','Docker','Git'], 'critical_skills':['Python','Postgres']}).json()
    resume = client.post('/upload_resume', files={'file':('resume.txt',
        'ФИО: Тестовый кандидат\nОпыт работы: 3 года.\nНавыки: Python, PostgreSQL, Docker.', 'text/plain')}).json()
    return vacancy['_id'], resume['resume_id']
