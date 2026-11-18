"""Prevent reference-field leakage and preserve the legacy frozen generator."""
import hashlib
import json
from pathlib import Path

import pytest

from pmi.dataset import generate, restore_missing, sha256
from pmi.quality import evaluate, summarize_rankings
from pmi.live_quality import evaluate_api_outputs


def test_quality_uses_pdf_predictions_not_reference_years_or_skills(tmp_path,monkeypatch):
    data = {'version':'test','vacancies':[{'id':'v','file':'v.pdf','direction':'test',
             'skills':['SQL'],'critical_skills':[]}],
            'resumes':[{'id':rid,'file':rid+'.pdf','direction':'test',
                        'text_skills':['SQL'],'experience_years':gold}
                       for rid,gold in [('unknown',99),('zero',98),('senior',0)]],
            'pairs':[{'vacancy_id':'v','resume_id':rid,'relevance':1}
                     for rid in ['unknown','zero','senior']]}
    (tmp_path/'dataset.json').write_text(json.dumps(data))
    (tmp_path/'manifest.json').write_text('{}')
    for item in data['vacancies']+data['resumes']:
        (tmp_path/item['file']).write_text(item['id'])
    monkeypatch.setattr('pmi.quality.verify',lambda _: {'ok':True})
    monkeypatch.setattr('pmi.quality.extract_text_from_file',lambda content,name:content.decode())
    years = {'v':None,'unknown':None,'zero':0,'senior':7}
    monkeypatch.setattr('pmi.quality.parse_raw_text_to_resume',
                        lambda text:{'skills':['Python'],'experience_years':years[text]})
    def rank(vacancy,texts,**kwargs):
        assert kwargs['vacancy_skills'] == {'Python'}
        assert kwargs['resume_skills_list'] == [{'Python'}]*3
        return [{'candidate_id':rid,'score':50} for rid in kwargs['candidate_ids']]
    monkeypatch.setattr('pmi.quality.rank_candidates',rank)
    report = evaluate(tmp_path,tmp_path/'report')
    assert [r['resume_id'] for r in report['rankings']['v']] == ['senior','zero','unknown']
    assert report['experience_extraction']['correct'] == 0
    assert report['experience_extraction']['ranking_source'] == 'parsed_from_pdf'


def test_api_quality_preserves_service_order_instead_of_sorting_by_gold(tmp_path):
    data = {'version':'test','vacancies':[{'id':'v','direction':'test','skills':['Python']}],
            'resumes':[{'id':rid,'text_skills':['Python'],'experience_years':10-i}
                       for i,rid in enumerate(['a','b'])],
            'pairs':[{'vacancy_id':'v','resume_id':'a','relevance':1},
                     {'vacancy_id':'v','resume_id':'b','relevance':0}]}
    documents = {rid:{'skills':['Python'],'experience_years':0} for rid in ['v','a','b']}
    rankings = {'v':[{'candidate_id':'b','score':50},{'candidate_id':'a','score':50}]}
    report = evaluate_api_outputs(data,documents,rankings,tmp_path)
    assert [row['resume_id'] for row in report['rankings']['v']] == ['b','a']
    assert report['metrics']['mrr'] == .5
    assert report['parser_reference_fields_used_for_prediction'] is False
    with pytest.raises(ValueError,match='exactly once'):
        summarize_rankings(data,{'v':[rankings['v'][0]]})


@pytest.fixture(scope='module')
def hh_dataset(tmp_path_factory):
    root = tmp_path_factory.mktemp('hh-corpus')
    return root,generate(root,style='hh')


def test_hh_corpus_has_frozen_design_counts_and_independent_labels(hh_dataset):
    root,data = hh_dataset
    from collections import Counter
    assert len(data['vacancies']) == 10
    assert len(data['resumes']) == 200
    assert len(data['pairs']) == 2000
    assert set(Counter(r['direction'] for r in data['resumes']).values()) == {40}
    assert data['seed'] == 20261118
    assert data['scoring_input_contract'] == 'pdf_upload'
    assert sum(r['experience_years'] is None for r in data['resumes']) == 10
    assert any(set(r['text_skills']) != set(r['latent_skills']) for r in data['resumes'])
    assert {r['layout_variant'] for r in data['resumes']} == {0,1,2}
    for item in data['vacancies']+data['resumes']:
        assert (root/item['file']).is_file()
    vacancies = {v['id']:v for v in data['vacancies']}
    resumes = {r['id']:r for r in data['resumes']}
    for pair in data['pairs']:
        vac,res = vacancies[pair['vacancy_id']],resumes[pair['resume_id']]
        weights = {skill:2 if skill in vac['critical_skills'] else 1 for skill in vac['skills']}
        expected = sum(weight for skill,weight in weights.items() if skill in res['latent_skills'])/sum(weights.values())
        assert pair['relevance'] == expected


def test_hh_restore_all_inputs_without_replacing_manifest(hh_dataset,tmp_path):
    root,data = hh_dataset
    # Include a missing dataset.json: its style must be recovered from manifest.
    digests = {str(p.relative_to(root)):sha256(p) for p in root.rglob('*') if p.is_file()}
    manifest = {'dataset_style':'hh','dataset_files':digests}
    frozen = json.dumps(manifest)
    (tmp_path/'manifest.json').write_text(frozen)
    restored = restore_missing(tmp_path)
    assert set(restored) == set(digests)
    assert (tmp_path/'manifest.json').read_text() == frozen
    assert all(sha256(tmp_path/name) == digest for name,digest in digests.items())


def test_legacy_generator_retains_historical_input_bytes(tmp_path):
    data = generate(tmp_path)
    project = Path(__file__).resolve().parents[2]
    manifest = json.loads((project/'data/pmi/manifest.json').read_text())
    assert data['version'] == 'pmi-synthetic-1'
    assert all(sha256(tmp_path/name) == digest for name,digest in manifest['dataset_files'].items())
