"""Regression cases found during the October 2026 end-to-end logic review."""
import json
from datetime import date

import pytest

from api.nlp_parser import extract_experience_years
from db import mongo
from scorer.service import score_vacancy
from scorer.skills import normalize_skill_set


@pytest.mark.parametrize('extra', [{}, {'skills': []}, {'skills': None}])
def test_scoring_legacy_documents_without_skills(client, extra):
    vid = mongo.insert_vacancy({'title': 'Python Docker', **extra})
    rid = mongo.insert_resume({'title': 'Python Docker', **extra})
    row = client.post('/score', json={'vacancy_id': vid}).json()['results'][0]
    assert row['resume_id'] == rid
    assert row['score'] > 80
    assert set(row['matched_skills']) == {'Python', 'Docker'}


def test_critical_edit_invalidates_previous_scores(client, pair):
    client.post('/score', json={'vacancy_id': pair[0]})
    assert client.get('/results/' + pair[0]).json()['count'] == 1
    client.patch('/vacancies/' + pair[0] + '/critical-skills', json={'critical_skills': []})
    assert client.get('/results/' + pair[0]).json()['count'] == 0


def test_no_save_has_no_side_effects(client, pair):
    before = mongo.get_vacancy(pair[0])
    score_vacancy(pair[0], critical_skills=set(), save=False)
    assert mongo.get_vacancy(pair[0]) == before


def test_failed_scoring_preserves_critical_selection(client, pair, monkeypatch):
    from scorer.transport import ScorerUnavailable
    def fail(**kwargs):
        raise ScorerUnavailable('test outage')
    monkeypatch.setattr('scorer.service.rank_candidates', fail)
    response = client.post('/score', json={'vacancy_id': pair[0], 'critical_skills': []})
    assert response.status_code == 503
    assert mongo.get_vacancy(pair[0])['critical_skills'] == ['PostgreSQL', 'Python']


def test_partial_rescore_does_not_mix_different_weights(client, pair):
    rid = mongo.insert_resume({'title': 'Docker', 'skills': ['Docker']})
    client.post('/score', json={'vacancy_id': pair[0]})
    assert client.get('/results/' + pair[0]).json()['count'] == 2
    client.post('/score', json={'vacancy_id': pair[0], 'resume_ids': [rid],
                               'weights': {'keyword': 1, 'cosine': 0}})
    rows = client.get('/results/' + pair[0]).json()['results']
    assert len(rows) == 1
    assert rows[0]['weights'] == {'keyword': 1, 'cosine': 0}


def test_object_id_case_does_not_duplicate_scores_or_feedback(client, pair):
    client.post('/score', json={'vacancy_id': pair[0]})
    client.post('/score', json={'vacancy_id': pair[0].upper()})
    assert mongo._coll(mongo.COLL_SCORES).count_documents({}) == 1
    assert client.get('/results/' + pair[0].upper()).json()['count'] == 1
    client.post('/feedback', json={'vacancy_id': pair[0].upper(),
                                  'resume_id': pair[1].upper(), 'decision': 'yes'})
    response = client.get('/feedback', params={'vacancy_id': pair[0], 'resume_id': pair[1]})
    assert response.json()['decision'] == 'yes'


def test_score_and_saved_order_match_for_complete_ties(client):
    vid = mongo.insert_vacancy({'title': 'Python', 'skills': ['Python']})
    ids = [mongo.insert_resume({'title': 'Python', 'skills': ['Python']}) for _ in range(2)]
    response = client.post('/score', json={'vacancy_id': vid, 'resume_ids': ids[::-1]})
    direct = [r['resume_id'] for r in response.json()['results']]
    saved = [r['resume_id'] for r in client.get('/results/' + vid).json()['results']]
    assert direct == saved


def test_dictionary_reload_updates_precomputed_skills_without_extraction(tmp_path, monkeypatch):
    path = tmp_path / 'skills.json'
    monkeypatch.setenv('SKILLS_DICTIONARY', str(path))
    path.write_text(json.dumps({'directions': {'test': {'Old skill': ['custom-alias']}}}))
    assert normalize_skill_set({'custom-alias'}) == {'Old skill'}
    path.write_text(json.dumps({'directions': {'test': {'New canonical skill': ['custom-alias']}}}))
    assert normalize_skill_set({'custom-alias'}) == {'New canonical skill'}


@pytest.mark.parametrize('text,expected', [
    ('Опыт работы: 0 лет', 0),
    ('Образование:\nУниверситет\n2015 — 2019\nОпыт работы:\nБез опыта', 0),
    ('Курсы Python: полгода.\nБез опыта', 0),
    ('Работа: 2020 — 2099', None),
    ('Опыт работы: 2027 — 2030', None),
])
def test_experience_rejects_education_and_future_periods(text, expected):
    assert extract_experience_years(text, now=date(2026, 10, 26)) == expected


@pytest.mark.parametrize('weight', [float('nan'), float('inf'), True, '2'])
def test_invalid_critical_weight_is_rejected(tmp_path, monkeypatch, weight):
    from scorer.config import load_config
    path = tmp_path / 'algorithm.json'
    path.write_text(json.dumps({'weights': {'keyword': .85, 'cosine': .15}, 'critical_weight': weight}))
    monkeypatch.setenv('ALGORITHM_CONFIG', str(path))
    with pytest.raises(ValueError):
        load_config()


@pytest.mark.parametrize('payload', [
    b'not json', b'{}', b'{"results":null}',
    b'{"results":[{"score":101,"candidate_id":"r1"}]}',
    b'{"results":[]}', b'{"results":[{"score":50,"candidate_id":"wrong"}]}',
])
def test_invalid_remote_scorer_response_is_service_error(monkeypatch, payload):
    from io import BytesIO
    from scorer.transport import rank, ScorerUnavailable
    monkeypatch.setenv('SCORER_URL', 'http://test-scorer')
    monkeypatch.setattr('scorer.transport.urlopen', lambda *args, **kwargs: BytesIO(payload))
    with pytest.raises(ScorerUnavailable):
        rank(vacancy_text='Python', candidate_texts=['Python'], candidate_ids=['r1'])


def test_equivalent_id_spellings_do_not_duplicate_input_candidates(client, pair):
    response = client.post('/score', json={'vacancy_id': pair[0], 'resume_ids': [pair[1], pair[1].upper()]})
    assert response.status_code == 200
    assert response.json()['count'] == 1


def test_partial_rescore_same_setup_retains_other_candidates(client, pair):
    rid = mongo.insert_resume({'title': 'Docker', 'skills': ['Docker']})
    client.post('/score', json={'vacancy_id': pair[0]})
    client.post('/score', json={'vacancy_id': pair[0], 'resume_ids': [rid]})
    assert client.get('/results/' + pair[0]).json()['count'] == 2


@pytest.mark.parametrize('resume,vacancy', [('', 'Python'), ('Python', ''), ('', '')])
def test_empty_pair_and_batch_have_same_explanation_and_threshold(resume, vacancy):
    from scorer import calculate_score, rank_candidates
    pair = calculate_score(resume, vacancy, critical_skills={'Python'}, min_score=1)
    batch = rank_candidates(vacancy, [resume], critical_skills={'Python'}, min_score=1)[0]
    assert pair['score'] == 0 and pair['passed_threshold'] is False
    for key in pair:
        assert pair[key] == batch[key]


def test_stored_dates_keep_utc_offset_for_browser(client, pair):
    client.post('/score', json={'vacancy_id': pair[0]})
    client.post('/feedback', json={'vacancy_id': pair[0], 'resume_id': pair[1], 'decision': 'yes'})
    feedback = client.get('/feedback', params={'vacancy_id': pair[0], 'resume_id': pair[1]}).json()
    rows = client.get('/results/' + pair[0]).json()['results']
    from datetime import datetime, timedelta
    for stamp in [feedback['updated_at'], feedback['history'][0]['created_at'], rows[0]['updated_at']]:
        assert datetime.fromisoformat(stamp).utcoffset() == timedelta(0)


def test_known_zero_experience_sorts_before_unknown_in_api_and_database(client):
    vid = mongo.insert_vacancy({'title': 'Python', 'skills': ['Python']})
    unknown = mongo.insert_resume({'title': 'Python', 'skills': ['Python']})
    zero = mongo.insert_resume({'title': 'Python', 'skills': ['Python'], 'experience_years': 0})
    output = client.post('/score', json={'vacancy_id': vid}).json()['results']
    stored = client.get('/results/' + vid).json()['results']
    assert [r['resume_id'] for r in output] == [r['resume_id'] for r in stored] == [zero, unknown]
