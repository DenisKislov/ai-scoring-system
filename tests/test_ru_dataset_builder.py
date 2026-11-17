import os
import pytest

spacy = pytest.importorskip("spacy")

from training.ner.span_match import (  # noqa: E402
    build_entities,
    default_alias_map,
    find_skill_spans,
    split_ids,
)

RU = spacy.blank("ru")
LABEL = "Skill"

ALIASES = {"postgresql": ["Postgres", "psql"]}


# --- каскад матчинга --------------------------------------------------------

def test_verbatim_match_case_insensitive_both_occurrences():
    spans = find_skill_spans("Владею Django и DJANGO", "Django", ALIASES)
    assert spans == [(7, 13), (16, 22)]


def test_no_match_gives_empty():
    assert find_skill_spans("Работал сварщиком", "Django", ALIASES) == []


def test_word_boundaries_prevent_substrings():
    assert find_skill_spans("Знаю JavaScript", "Java", ALIASES) == []
    assert len(find_skill_spans("Знаю Java и JavaScript", "Java", ALIASES)) == 1


def test_tier_normalization_backslash_and_yo():
    assert find_skill_spans("настроил CI\\CD процессы", "CI/CD", ALIASES)
    assert find_skill_spans("Владею ТЁРМИНАЛЫ", "Терминалы", ALIASES)  # ё→е + регистр


def test_tier_morphology_russian_stems():
    text = "Занимался параллельным программированием и алгоритмами"
    spans = find_skill_spans(text, "параллельное программирование", ALIASES)
    assert spans == [(text.index("параллельным"), text.index("параллельным") + len("параллельным программированием"))]


def test_tier_aliases_last_resort():
    spans = find_skill_spans("Работал с Postgres и psql", "PostgreSQL", ALIASES)
    assert len(spans) == 2
    text = "Работал с Postgres и psql"
    assert all(text[s:e].lower() != "postgresql" for s, e in spans)


def test_verbatim_and_alias_occurrences_combined():
    spans = find_skill_spans("PostgreSQL, Postgres", "PostgreSQL", ALIASES)
    assert len(spans) == 2


# --- пересечения и токен-выравнивание ---------------------------------------

def test_longest_span_wins_nested():
    text = "Опыт: 1С УПП и 1С"
    entities, stats = build_entities(RU, text, ["1С УПП", "1С"])
    spans = [(s, e) for s, e, _ in entities]
    # вложенное «1С» (6,8) не размечено; длинное и standalone — размечены
    assert (6, 12) in spans and (15, 17) in spans
    assert (6, 8) not in spans
    assert stats["candidates_rejected"] == 1


def test_non_overlapping_all_kept():
    text = "Django, PostgreSQL"
    entities, stats = build_entities(RU, text, ["Django", "PostgreSQL"])
    assert len(entities) == 2
    assert stats["matched_skills"] == 2 and stats["unmatched_skills"] == 0


def test_entities_aligned_to_tokens():
    text = "Владею CI/CD, Django (уверенно)"
    entities, stats = build_entities(RU, text, ["CI/CD", "Django"])
    assert stats["skipped_misaligned"] == 0
    doc = RU.make_doc(text)
    for start, end, label in entities:
        assert doc.char_span(start, end, label=label) is not None


def test_zero_skills_document_ok():
    entities, stats = build_entities(RU, "Резюме без навыков вовсе", [])
    assert entities == []
    assert stats["matched_skills"] == 0


def test_stats_report_unmatched():
    entities, stats = build_entities(RU, "Знаю только Django", ["Django", "Kafka"])
    assert stats["matched_skills"] == 1 and stats["unmatched_skills"] == 1


# --- сплит -------------------------------------------------------------------

def test_split_deterministic_and_proportional():
    ids = [str(i) for i in range(100)]
    assert split_ids(ids, seed=42) == split_ids(ids, seed=42)
    train, dev, test = split_ids(ids, seed=42)
    assert len(train) == 80 and len(dev) == 10 and len(test) == 10
    assert set(train) | set(dev) | set(test) == set(ids)
    assert not (set(train) & set(dev)) and not (set(dev) & set(test))


def test_split_small_corpus():
    train, dev, test = split_ids(["1", "2", "3", "4", "5"], seed=7)
    assert len(train) + len(dev) + len(test) == 5
    assert len(dev) >= 1 and len(test) >= 1


# --- алиасный словарь по умолчанию -------------------------------------------

def test_default_alias_map_contains_known_alias():
    amap = default_alias_map()
    assert "postgres" in [a.lower() for a in amap.get("postgresql", [])]


# --- смок на реальных данных (пропуск, если корпус не выгружен) --------------

import json
from pathlib import Path

from training.ner import build_ru_dataset as builder

REAL = Path("data/ground_truth_resumes_assembled.csv")

@pytest.mark.skipif(os.environ.get("RUN_LOCAL_PDF_TRAINING") != "1" or not REAL.exists(),
                    reason="чтение локального PDF-корпуса требует RUN_LOCAL_PDF_TRAINING=1")
def test_build_real_corpus_smok(tmp_path):
    stats = builder.build(tmp_path, seed=42)
    r = stats["kinds"]["resumes"]
    assert r["documents"] >= 150 and r["coverage_pct"] >= 90
    assert stats["split_documents"]["train"] >= 0.75 * sum(stats["split_documents"].values())
    for name in ("train", "dev", "test"):
        assert (tmp_path / f"{name}.spacy").stat().st_size > 0
    assert json.loads((tmp_path / "stats.json").read_text())["noise_estimate_pct"] < 10
