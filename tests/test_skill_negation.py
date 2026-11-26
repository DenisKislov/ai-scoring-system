import pytest

from api.nlp_parser import extract_experience_years
from scorer import calculate_score, extract_skills
from scorer import skills
from scorer.ner_skills import ner_skill_mentions


@pytest.mark.parametrize(('text', 'expected'), [
    ('Не знаю Docker и Python', set()),
    ('Docker не использовал. На Python работал.', {'Python'}),
    ('На Python работал. Docker не применял.', {'Python'}),
    ('Docker и Python не знаю', set()),
    ('Python, без опыта Docker', {'Python'}),
    ('Без опыта SQL, Python использую без Docker', {'Python'}),
    ('Без опыта Node.js и .NET. Python', {'Python'}),
    ('Без опыта Docker\nPython', {'Python'}),
    ('Не только Python, но и SQL', {'Python', 'SQL'}),
    ('Без ошибок работал на Python', {'Python'}),
    ('No experience with Docker and SQL. Used Python.', {'Python'}),
    ('Python, Docker (не требуется), SQL', {'Python', 'SQL'}),
    ('Не знаю PostgreSQL. Использую Postgres.', {'PostgreSQL'}),
])
def test_negation_scope(text, expected):
    assert extract_skills(text) == expected


def test_ner_only_span_does_not_restore_negated_skill(monkeypatch):
    monkeypatch.setenv('NER_SKILLS_ENABLED', '1')
    text = 'Не использую QuasarX. Использую Python.'
    start = text.index('QuasarX')
    monkeypatch.setattr(skills, 'ner_skill_mentions', lambda _: [('QuasarX', start, start + len('QuasarX'))])
    masked, extracted, denied = skills.prepare_skill_input(text)
    assert extracted == {'Python'} and denied == {'QuasarX'}
    assert 'QuasarX' not in masked


def test_real_ner_extraction_respects_negation(monkeypatch):
    monkeypatch.setenv('NER_SKILLS_ENABLED', '1')
    text = 'Работаю с Python, не использую Docker.'
    assert 'Docker' in {name for name, _, _ in ner_skill_mentions(text)}
    assert extract_skills(text) == {'Python'}


def test_explicit_denial_blocks_family_match_and_tfidf_term():
    vacancy = 'SQL и Python'
    negative = calculate_score('Использую MySQL и Python. Не использую SQL.', vacancy)
    control = calculate_score('Использую MySQL и Python. Не использую .', vacancy)
    assert negative['matched_skills'] == ['Python']
    assert control['matched_skills'] == ['Python', 'SQL']
    assert negative['cosine_sim'] == control['cosine_sim']


def test_denial_of_specific_technology_is_not_zero_total_experience():
    assert extract_experience_years('Без опыта работы с Docker') is None
    assert extract_experience_years('Опыт работы: Без опыта работы') == 0
