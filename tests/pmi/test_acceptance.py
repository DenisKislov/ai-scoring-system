"""Automatic coverage of A-1…A-20; deployment/manual evidence is kept separate."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from collections import Counter
import pymongo.errors
import pytest
from fastapi.testclient import TestClient
from api.file_parser import extract_text_from_file
from api.main import create_app
from db import mongo
from pmi.dataset import write_pdf
from pmi.quality import ranking_metrics, pmi_spearman
from scorer import calculate_score, extract_skills, rank_candidates
from scorer.config import algorithm_manifest
from scorer.http_api import app as kernel_app


@pytest.mark.pmi_case('A-1')
def test_a01_upload_and_original_hash(client, tmp_path):
    path = tmp_path/'vacancy.pdf'
    write_pdf(path, 'Вакансия: Разработчик\nНавыки: Python, PostgreSQL.\nОпыт работы: 2 года.')
    source = path.read_bytes()
    expected = hashlib.sha256(source).hexdigest()
    vac = client.post('/upload_vacancy', files={'file':('vacancy.pdf', source, 'application/pdf')},
                      data={'critical_skills':'["Postgres"]'})
    assert vac.status_code == 201
    body = vac.json()
    assert body['critical_skills'] == ['PostgreSQL']
    assert body['original_sha256'] == expected
    downloaded = client.get('/files/vacancies/'+body['vacancy_id'])
    assert downloaded.content == source
    assert downloaded.headers['x-content-sha256'] == expected
    batch = client.post('/upload_resumes', files=[('files',('one.pdf',source,'application/pdf')),
                                                 ('files',('two.pdf',source,'application/pdf'))])
    assert batch.status_code == 201 and batch.json()['count'] == 2
    ids = [r['resume_id'] for r in batch.json()['results']]
    assert len(set(ids)) == 2
    assert client.get('/stats').json() == {'vacancies':1,'resumes':2}
    assert client.get('/candidates').status_code == 200


@pytest.mark.pmi_case('A-2')
def test_a02_aliases_one_canonical(client):
    skills = extract_skills('PostgreSQL, Postgres, постгрес, psql, JS, JavaScript, k8s, Kubernetes')
    assert skills == {'PostgreSQL','JavaScript','Kubernetes'}
    assert extract_skills('1С: Бухгалтерия, 1С Бухгалтерия, 1C: Бухгалтерия') == {'1С: Бухгалтерия'}


@pytest.mark.pmi_case('A-3')
def test_a03_manifest_and_repeat(client, pair):
    config = client.get('/config').json()
    assert config['critical_weight'] > 1 and sum(config['weights'].values()) == 1
    assert config['file_hashes'] and config['dependencies'] and config['version']
    payload = {'vacancy_id':pair[0]}
    a, b = client.post('/score',json=payload), client.post('/score',json=payload)
    assert a.status_code == b.status_code == 200
    assert a.json()['results'] == b.json()['results']


@pytest.mark.pmi_case('A-4')
def test_a04_order_storage_upsert_and_pair(client, pair):
    # Same professional text and score; only experience breaks the tie.
    base = mongo.get_resume(pair[1])
    base.pop('_id'); base['experience_years'] = 9
    second = mongo.insert_resume(base)
    request = {'vacancy_id':pair[0]}
    for _ in range(2):
        response = client.post('/score',json=request)
        assert response.status_code == 200
    stored = client.get('/results/'+pair[0]).json()['results']
    assert len(stored) == 2
    assert len({r['_id'] for r in stored}) == 2
    assert stored[0]['resume_id'] == second
    assert all(0 <= r['score'] <= 100 for r in stored)
    for row in stored:
        assert {'updated_at','keyword_contribution','cosine_contribution','missing_critical','matched_skills','algorithm_fingerprint'} <= row.keys()
    single = client.post('/score',json={'vacancy_id':pair[0],'resume_ids':[pair[1],pair[1]]})
    assert single.status_code == 200 and single.json()['count'] == 1
    assert single.json()['results'][0]['score'] == stored[1]['score']
    assert client.post('/score', json={'vacancy_id':pair[0], 'weights':{'keyword':2, 'cosine':1}}).status_code == 422


@pytest.mark.pmi_case('A-5')
def test_a05_explanation_and_source(client, pair):
    r = client.post('/score',json={'vacancy_id':pair[0]}).json()['results'][0]
    assert r['matched_skills'] and r['missing_skills']
    assert r['score'] == pytest.approx(100*(r['keyword_contribution']+r['cosine_contribution']), abs=.6)
    source = client.get('/resumes/'+pair[1]).json()
    assert 'ФИО: Тестовый кандидат' in source['formatted_text']


@pytest.mark.pmi_case('A-6')
def test_a06_hr_history_and_missing_pair(client, pair):
    for decision in ['yes','no']:
        response = client.post('/feedback',json={'vacancy_id':pair[0],'resume_id':pair[1],'decision':decision})
        assert response.status_code == 200
        assert response.json()['event']['updated_at']
    saved = client.get('/feedback', params={'vacancy_id':pair[0],'resume_id':pair[1]}).json()
    assert saved['decision'] == 'no'
    assert [e['decision'] for e in saved['history']] == ['yes','no']
    assert all(e['updated_at'] for e in saved['history'])
    assert client.post('/feedback',json={'vacancy_id':'missing','resume_id':pair[1],'decision':'yes'}).status_code == 404


@pytest.mark.pmi_case('A-7')
def test_a07_openapi_and_validation(client, pair):
    spec = client.get('/openapi.json').json()
    assert spec['paths']['/score']['post']['responses']['200']['content']['application/json']['schema']['$ref'].endswith('ResultsOut')
    assert spec['components']['schemas']['ScoreResult']['properties']['score']['maximum'] == 100
    assert client.post('/score',json={}).status_code == 422
    assert client.get('/results/missing').status_code == 404
    assert client.patch('/vacancies/'+pair[0]+'/critical-skills',json={'critical_skills':['Postgres']}).json()['critical_skills'] == ['PostgreSQL']
    assert client.patch('/vacancies/'+pair[0]+'/critical-skills',json={'critical_skills':['AutoCAD']}).status_code == 422


@pytest.mark.pmi_case('A-8')
@pytest.mark.parametrize('kind',['vacancies','resumes'])
def test_a08_delete_cascades(client, pair, kind, caplog):
    client.post('/score',json={'vacancy_id':pair[0]})
    client.post('/feedback',json={'vacancy_id':pair[0],'resume_id':pair[1],'decision':'yes'})
    ident = pair[0] if kind == 'vacancies' else pair[1]
    assert client.delete(f'/{kind}/{ident}').status_code == 200
    assert mongo._coll(mongo.COLL_SCORES).count_documents({}) == 0
    assert mongo._coll(mongo.COLL_FEEDBACK).count_documents({}) == 0
    assert client.get(f'/files/{kind}/{ident}').status_code == 404
    assert client.get(f'/{kind}/{ident}').status_code == 404
    assert 'document_deleted' in caplog.text


@pytest.mark.pmi_case('A-9')
def test_a09_metric_formula_known_results():
    # Deliberately non-ideal order, with hand-computable binary metrics.
    result = ranking_metrics([0,1,1,0,0,0,0,0,0,0], list(range(10,0,-1)))
    assert result['precision_at_5'] == .4
    assert result['precision_at_10'] == .2
    assert result['recall_at_10'] == 1
    assert 0 < result['ndcg_at_10'] < 1
    assert pmi_spearman([1,2,3],[3,2,1]) == -1
    assert ranking_metrics([0]*10,[0]*10)['recall_at_10'] is None


@pytest.mark.pmi_case('A-10')
def test_a10_irrelevant_below_all_strong():
    ranked = rank_candidates('Python Django PostgreSQL',
        ['Python Django PostgreSQL','Python Django','Повар: приготовление супа.'],
        candidate_ids=['strong','partial','irrelevant'])
    byid = {r['candidate_id']:r for r in ranked}
    assert byid['irrelevant']['score'] <= 30
    assert byid['irrelevant']['score'] < byid['strong']['score']


@pytest.mark.pmi_case('A-11')
def test_a11_critical_equal_match_counts():
    results = rank_candidates('Python PostgreSQL Docker Git',
        ['Python PostgreSQL','Docker Git'], critical_skills={'Python','PostgreSQL'})
    assert len(results[0]['matched_skills']) == len(results[1]['matched_skills']) == 2
    assert results[0]['candidate_id'] == 0 and results[0]['score'] > results[1]['score']


@pytest.mark.pmi_case('A-12')
def test_a12_pool_10_200_and_pair():
    text, vacancy = 'Python PostgreSQL Docker', 'Python PostgreSQL Docker Git'
    small = rank_candidates(vacancy,[text]+['Повар']*9)
    large = rank_candidates(vacancy,[text]+['Повар']*199)
    target = lambda rows: next(r for r in rows if r['candidate_id']==0)
    assert target(small)['score'] == target(large)['score'] == calculate_score(text,vacancy)['score']
    assert target(small)['cosine_sim'] == target(large)['cosine_sim']


@pytest.mark.pmi_case('A-13')
@pytest.mark.parametrize('filename,content', [('empty.txt',b''),('broken.pdf',b'not a PDF'),('unsupported.doc',b'sample'),('invalid.txt',b'\xff\xfe')])
def test_a13_invalid_file_survival(client, filename, content, caplog):
    for endpoint in ['/upload_resume','/upload_vacancy']:
        response = client.post(endpoint, files={'file':(filename,content)})
        assert response.status_code == 400 and response.json()['detail']
    assert client.get('/stats').status_code == 200
    assert 'extraction_error' in caplog.text


@pytest.mark.pmi_case('A-13')
def test_a13_empty_text_zero_in_both_paths(client):
    for endpoint in ['/vacancies','/candidates']:
        assert client.post(endpoint,json={'title':' ','description':''}).status_code == 422
    assert calculate_score('', 'Python')['score'] == 0
    assert rank_candidates('Python',[''])[0]['score'] == 0
    assert rank_candidates('', ['Python'])[0]['score'] == 0


@pytest.mark.pmi_case('A-14')
def test_a14_db_unavailable_then_recovers(client, monkeypatch, caplog):
    real = mongo.get_db
    def down():
        raise pymongo.errors.ServerSelectionTimeoutError('simulated outage')
    monkeypatch.setattr(mongo,'get_db',down)
    for path in ['/vacancies','/candidates','/stats','/threshold']:
        response = client.get(path)
        assert response.status_code == 503 and response.json()['detail']
    assert 'database_error' in caplog.text
    monkeypatch.setattr(mongo,'get_db',real)
    assert client.get('/stats').status_code == 200


@pytest.mark.pmi_case('A-15')
def test_a15_new_api_instance_keeps_storage(client, pair):
    # Application restart only; container/volume restart is covered by pmi live.
    other = TestClient(create_app())
    assert other.get('/vacancies/'+pair[0]).json()['_id'] == pair[0]
    assert other.get('/resumes/'+pair[1]).json()['_id'] == pair[1]


@pytest.mark.pmi_case('A-16')
def test_a16_logs_include_measured_duration(client, pair, caplog):
    client.post('/score',json={'vacancy_id':pair[0]})
    events = [json.loads(r.message) for r in caplog.records if r.message.startswith('{')]
    completed = next(e for e in events if e['event']=='scoring_completed')
    assert completed['duration_seconds'] >= 0 and completed['count'] == 1


@pytest.mark.pmi_case('A-17')
def test_a17_personal_attributes_invariant():
    professional = '\nНавыки: Python, PostgreSQL, Docker.\nОпыт работы: 3 года.'
    first = 'ФИО: Тестовый А\nВозраст: 25\nПол: мужской\nАдрес: город А\nГражданство: страна А'
    second = 'ФИО: Тестовый Б\nВозраст: 53\nПол: женский\nАдрес: город Б\nГражданство: страна Б'
    vacancy = 'Python PostgreSQL Docker Git'
    a,b = (calculate_score(x+professional,vacancy) for x in [first,second])
    assert a == b
    ranked = rank_candidates(vacancy,[first+professional,second+professional])
    assert ranked[0]['score'] == ranked[1]['score'] == a['score']
    assert ranked[0]['cosine_sim'] == ranked[1]['cosine_sim']


@pytest.mark.pmi_case('A-18')
def test_a18_no_private_inputs_in_image():
    dockerfile = Path('backend.Dockerfile').read_text()
    assert 'COPY data/ data/' not in dockerfile
    assert 'SCORER_URL' in Path('docker-compose.yml').read_text()
    assert 'process.env.REACT_APP_API_URL' in Path('frontend/src/api/api.js').read_text()


@pytest.mark.pmi_case('A-19')
def test_a19_remote_kernel_contract(monkeypatch):
    from scorer import transport
    local = rank_candidates('Python',['Python','Повар'],candidate_ids=['a','b'])
    response = TestClient(kernel_app).post('/rank',json={
        'vacancy_text':'Python','candidate_texts':['Python','Повар'],'candidate_ids':['a','b']})
    assert response.status_code == 200 and response.json()['results'] == local
    assert TestClient(kernel_app).post('/rank',json={'vacancy_text':'Python','candidate_texts':['Python'],'candidate_ids':[]}).status_code == 422


@pytest.mark.pmi_case('A-20')
def test_a20_dictionary_extension_no_code_change(monkeypatch,tmp_path):
    dictionary = {'version':'test','directions':{'Новое направление':{'Квантовая метрология':['квантметр']}}}
    path = tmp_path/'skills.json';path.write_text(json.dumps(dictionary,ensure_ascii=False))
    monkeypatch.setenv('SKILLS_DICTIONARY',str(path))
    assert 'Квантовая метрология' in extract_skills('Практика: квантметр.')
    # Edit the same file, without resetting production globals or restarting API.
    dictionary['directions']['Новое направление']['Лазерная калибровка'] = ['лазеркалибр']
    path.write_text(json.dumps(dictionary,ensure_ascii=False))
    assert 'Лазерная калибровка' in extract_skills('Опыт: лазеркалибр.')
