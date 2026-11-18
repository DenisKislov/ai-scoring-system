"""Reference construction must not mistake another team's skill for a claim."""
from collections import Counter
import json

import pytest

from pmi.dataset import generate, restore_missing, sha256


@pytest.fixture(scope='module')
def corpus(tmp_path_factory):
    root = tmp_path_factory.mktemp('it-corpus')
    return root,generate(root,style='it')


def test_challenging_reference_excludes_context_and_tracks_omissions(corpus):
    root,data = corpus
    assert data['seed'] == 2026111802
    assert len(data['vacancies']) == 10 and len(data['resumes']) == 200
    assert len(data['pairs']) == 2000
    assert set(Counter(r['direction'] for r in data['resumes']).values()) == {40}
    assert sum(bool(r['context_only_skills']) for r in data['resumes']) == 40
    assert sum(r['transition_profile'] for r in data['resumes']) == 50
    assert any(set(r['text_skills']) < set(r['latent_skills']) for r in data['resumes'])
    assert sum(r['experience_years'] is None for r in data['resumes']) == 10
    for resume in data['resumes']:
        assert not set(resume['context_only_skills']) & set(resume['latent_skills'])
        assert set(resume['text_skills']) <= set(resume['latent_skills'])
        if resume['context_only_skills']:
            assert 'лично с этой технологией не работал' in resume['text']
    vacancies = {v['id']:v for v in data['vacancies']}
    resumes = {r['id']:r for r in data['resumes']}
    for pair in data['pairs']:
        v,r = vacancies[pair['vacancy_id']],resumes[pair['resume_id']]
        weights = {s:2 if s in v['critical_skills'] else 1 for s in v['skills']}
        assert pair['relevance'] == sum(w for s,w in weights.items() if s in r['latent_skills'])/sum(weights.values())


def test_it_corpus_restores_identical_pdf_and_label_bytes(corpus,tmp_path):
    root,data = corpus
    hashes = {str(p.relative_to(root)):sha256(p) for p in root.rglob('*') if p.is_file()}
    frozen = json.dumps({'dataset_style':'it','dataset_files':hashes})
    (tmp_path/'manifest.json').write_text(frozen)
    assert set(restore_missing(tmp_path)) == set(hashes)
    assert (tmp_path/'manifest.json').read_text() == frozen
    assert all(sha256(tmp_path/p) == digest for p,digest in hashes.items())
