import json

import mongomock

from scorer import auto_threshold
from api import threshold_service
from db import mongo


def test_calibration_uses_extraction_not_ground_truth(tmp_path, monkeypatch):
    vacancy_path, resume_path = tmp_path/'v.json', tmp_path/'r.json'
    vacancy_path.write_text(json.dumps([{'raw_text': 'Python', 'expected_skills': ['Wrong']}]))
    resume_path.write_text(json.dumps([{'raw_text': 'Python'}]))
    monkeypatch.setattr(auto_threshold, 'extract_skills', lambda text: {'Python'})
    def rank(text, texts, **kwargs):
        assert kwargs['vacancy_skills'] == {'Python'}
        assert kwargs['resume_skills_list'] == [{'Python'}]
        return [{'matched_skills': ['Python']}]
    monkeypatch.setattr(auto_threshold, 'rank_candidates', rank)
    assert auto_threshold.compute_dataset_threshold(vacancy_path, resume_path) == (1.0, 1, 1)


def test_old_or_changed_algorithm_threshold_is_disabled(monkeypatch):
    client = mongomock.MongoClient()
    monkeypatch.setattr(mongo, '_client', client)
    monkeypatch.setattr(threshold_service, 'algorithm_manifest', lambda: {'fingerprint': 'current'})
    coll = threshold_service._config_coll()
    coll.insert_one({'_id': threshold_service.THRESHOLD_DOC_ID, 'value': .9})
    assert threshold_service.get_threshold_doc() is None
    coll.update_one({}, {'$set': {'method': auto_threshold.METHOD, 'algorithm_fingerprint': 'current'}})
    assert threshold_service.get_threshold_value() == .9
    coll.update_one({}, {'$set': {'algorithm_fingerprint': 'previous'}})
    assert threshold_service.get_threshold_doc() is None
