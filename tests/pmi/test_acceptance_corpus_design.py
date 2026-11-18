"""The prepared acceptance cohort and references must remain reproducible."""
from collections import Counter
import json

import pytest

from pmi.dataset import generate,restore_missing,sha256


@pytest.fixture(scope='module')
def corpus(tmp_path_factory):
    root=tmp_path_factory.mktemp('acceptance-cohort')
    return root,generate(root,style='acceptance')


def test_disclosed_cohort_and_direct_references(corpus):
    root,data=corpus
    assert len(data['vacancies'])==10 and len(data['resumes'])==200 and len(data['pairs'])==2000
    assert set(Counter(r['direction'] for r in data['resumes']).values())=={40}
    assert Counter(r['scenario'] for r in data['resumes'])=={'novice':50,'rare_mobile':3,'python_professional':147}
    rare=next(v for v in data['vacancies'] if v['scenario']=='scarce_specialty')
    assert sum(p['relevance']>=.1 for p in data['pairs'] if p['vacancy_id']==rare['id'])==3
    assert 'not blind' in data['protocol']['purpose']
    resumes={r['id']:r for r in data['resumes']};vacancies={v['id']:v for v in data['vacancies']}
    for pair in data['pairs']:
        v,r=vacancies[pair['vacancy_id']],resumes[pair['resume_id']]
        assert set(r['text_skills'])<=set(r['latent_skills'])
        weights={s:2 if s in v['critical_skills'] else 1 for s in v['skills']}
        assert pair['relevance']==sum(w for s,w in weights.items() if s in r['latent_skills'])/sum(weights.values())
        if r['scenario']=='novice':assert pair['relevance']==0


def test_acceptance_inputs_restore_byte_for_byte(corpus,tmp_path):
    root,data=corpus
    hashes={str(p.relative_to(root)):sha256(p) for p in root.rglob('*') if p.is_file()}
    frozen=json.dumps({'dataset_style':'acceptance','dataset_files':hashes})
    (tmp_path/'manifest.json').write_text(frozen)
    assert set(restore_missing(tmp_path))==set(hashes)
    assert all(sha256(tmp_path/name)==digest for name,digest in hashes.items())
    assert (tmp_path/'manifest.json').read_text()==frozen
