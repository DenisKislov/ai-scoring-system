import json

import pytest
import spacy
from spacy.tokens import Span

from scorer import ner_skills
from scorer import skills as skills_module
from scorer.ner_skills import ner_enabled, ner_extract_skills, ner_status
from scorer.config import algorithm_manifest
from scorer.skills import extract_skills

EN_RESUME = """Alex Johnson
Experience: Data Scientist at Acme Corp 2019-2022.
Skills: Python, TensorFlow, SQL, AWS, Docker.
Built ML pipelines with scikit-learn."""

RU_RESUME = """Иванов Пётр Сергеевич
Опыт работы: 5 лет.
Разработчик на Python, использую Django, PostgreSQL, Docker.
Работал с машинным обучением: scikit-learn, PyTorch."""


@pytest.fixture(autouse=True)
def _isolated_ner(monkeypatch):
    ner_skills._reset_for_tests()
    monkeypatch.delenv("NER_SKILLS_ENABLED", raising=False)
    monkeypatch.delenv("NER_SKILLS_MODEL", raising=False)
    yield
    ner_skills._reset_for_tests()


def test_model_loads_and_returns_only_skill_entities():
    ents = ner_extract_skills(EN_RESUME)
    assert isinstance(ents, set)
    assert all(isinstance(e, str) and e for e in ents)
    assert {"Python", "SQL", "Docker"} <= ents


def test_russian_resume_latin_skills_extracted():
    ents = ner_extract_skills(RU_RESUME)
    assert {"Python", "Django", "PostgreSQL"} <= ents


def test_extracts_skill_label_only(monkeypatch):
    # RU-модель одноклассовая (только Skill), поэтому фильтрацию не-Skill
    # меток проверяем на тестовом пайплайне — модель-независимо.
    @spacy.language.Language.component("set_ents_test", assigns=["doc.ents"])
    def _set_ents(doc):
        by_text = {t.text: t for t in doc}
        doc.ents = [Span(doc, by_text["Python"].i, by_text["Python"].i + 1, label="Skill"),
                    Span(doc, by_text["English"].i, by_text["English"].i + 1, label="Language")]
        return doc

    nlp = spacy.blank("ru")
    nlp.add_pipe("set_ents_test")
    monkeypatch.setattr(ner_skills, "_nlp", nlp)
    monkeypatch.setattr(ner_skills, "_loaded_signature", ner_skills._signature())
    assert ner_extract_skills("Владею Python и English") == {"Python"}


def test_deterministic():
    assert ner_extract_skills(RU_RESUME) == ner_extract_skills(RU_RESUME)


def test_empty_text_gives_empty_set():
    assert ner_extract_skills("") == set()
    assert ner_extract_skills("   ") == set()


def test_broken_model_degrades_to_empty_and_latches(monkeypatch):
    monkeypatch.setenv("NER_SKILLS_MODEL", "/nonexistent/model")
    assert ner_extract_skills(EN_RESUME) == set()
    assert ner_skills._load_failed is True  # latch: повтора загрузки не будет
    assert ner_status()["available"] is False


def _cfg(tmp_path, **extra):
    payload = {"weights": {"keyword": 0.85, "cosine": 0.15},
               "critical_weight": 2.0, **extra}
    p = tmp_path / "algorithm.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def test_repo_flag_enabled(monkeypatch):
    monkeypatch.delenv("NER_SKILLS_ENABLED", raising=False)
    assert ner_enabled() is True


def test_flag_env_enables(monkeypatch):
    monkeypatch.setenv("NER_SKILLS_ENABLED", "1")
    assert ner_enabled() is True


def test_flag_env_disables_over_config_true(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGORITHM_CONFIG", _cfg(tmp_path, ner_skills_enabled=True))
    monkeypatch.setenv("NER_SKILLS_ENABLED", "false")
    assert ner_enabled() is False


def test_flag_config_true_without_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGORITHM_CONFIG", _cfg(tmp_path, ner_skills_enabled=True))
    monkeypatch.delenv("NER_SKILLS_ENABLED", raising=False)
    assert ner_enabled() is True


def test_flag_missing_key_means_false(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGORITHM_CONFIG", _cfg(tmp_path))
    monkeypatch.delenv("NER_SKILLS_ENABLED", raising=False)
    assert ner_enabled() is False


UNION_TEXT = "Skills: Python, SQL, Docker. Опыт: Django, PostgreSQL."


def test_union_adds_ner_skills_when_enabled(monkeypatch):
    monkeypatch.setenv("NER_SKILLS_ENABLED", "1")
    # Детерминированный мок: "Kafka" нет в тексте → словарь его не даст,
    # значит в результате он мог появиться только из NER-ветки union.
    # "Kafka" каноникализируется в "Apache Kafka" (raw-алиас в таксономии).
    monkeypatch.setattr(skills_module, "ner_extract_skills", lambda t: {"Kafka"})
    assert "Apache Kafka" in extract_skills(UNION_TEXT)
    assert "Python" in extract_skills(UNION_TEXT)


def test_union_superset_of_real_ner_when_enabled(monkeypatch):
    monkeypatch.setenv("NER_SKILLS_ENABLED", "1")
    result = extract_skills(UNION_TEXT)
    dict_only = skills_module.normalize_skill_set(
        skills_module._get_extractor().extract(skills_module.professional_text(UNION_TEXT)))
    assert result >= dict_only
    assert result >= skills_module.normalize_skill_set(ner_extract_skills(UNION_TEXT))


def test_flag_off_keeps_dictionary_result(monkeypatch):
    monkeypatch.setenv("NER_SKILLS_ENABLED", "0")
    monkeypatch.setattr(skills_module, "ner_extract_skills",
                        lambda t: pytest.fail("NER не должен вызываться при выключенном флаге"))
    dict_only = skills_module.normalize_skill_set(
        skills_module._get_extractor().extract(skills_module.professional_text(UNION_TEXT)))
    assert extract_skills(UNION_TEXT) == dict_only


def test_manifest_excludes_ner_when_disabled(monkeypatch):
    monkeypatch.setenv("NER_SKILLS_ENABLED", "0")
    m = algorithm_manifest()
    assert "spacy" not in m["dependencies"]
    assert "scorer/ner_skills.py" not in m["file_hashes"]
    assert "scorer/models/resume_ner/meta.json" not in m["file_hashes"]
    assert m["ner_skills"] == {"enabled": False, "available": False}


def test_manifest_includes_ner_when_enabled(monkeypatch):
    monkeypatch.setenv("NER_SKILLS_ENABLED", "0")
    off = algorithm_manifest()["fingerprint"]
    monkeypatch.setenv("NER_SKILLS_ENABLED", "1")
    m = algorithm_manifest()
    assert m["dependencies"]["spacy"]
    assert "scorer/ner_skills.py" in m["file_hashes"]
    assert "scorer/models/resume_ner/meta.json" in m["file_hashes"]
    assert m["ner_skills"]["enabled"] is True
    assert m["fingerprint"] != off


def test_manifest_hashes_effective_model_weights(tmp_path, monkeypatch):
    model = tmp_path / 'model'
    (model / 'ner').mkdir(parents=True)
    (model / 'ner/model').write_bytes(b'first weights')
    (model / 'meta.json').write_text('{}')
    monkeypatch.setenv('NER_SKILLS_ENABLED', '1')
    monkeypatch.setenv('NER_SKILLS_MODEL', str(model))
    monkeypatch.setattr(ner_skills, '_load', lambda: object())
    before = algorithm_manifest()
    (model / 'ner/model').write_bytes(b'other weights')
    after = algorithm_manifest()
    assert before['file_hashes']['scorer/models/resume_ner/meta.json'] == after['file_hashes']['scorer/models/resume_ner/meta.json']
    assert before['fingerprint'] != after['fingerprint']
    assert after['ner_skills']['available'] is True


def test_uninstalled_spacy_degrades_to_dictionary(monkeypatch):
    import builtins
    original = builtins.__import__
    def missing(name, *args, **kwargs):
        if name == 'spacy':
            raise ImportError('uninstalled for test')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', missing)
    monkeypatch.setenv('NER_SKILLS_ENABLED', '1')
    assert ner_extract_skills('Python') == set()
    assert ner_status() == {'enabled': True, 'available': False}
    assert 'Python' in extract_skills('Python')


def test_ner_does_not_duplicate_a_nested_skill(monkeypatch):
    monkeypatch.setenv('NER_SKILLS_ENABLED', '1')
    monkeypatch.setattr(skills_module, 'ner_extract_skills', lambda text: {'1С'})
    assert extract_skills('1С: Бухгалтерия, 1С Бухгалтерия, 1C: Бухгалтерия') == {'1С: Бухгалтерия'}
    assert extract_skills('1С: Бухгалтерия и 1С') == {'1С: Бухгалтерия', '1С'}
