"""Сборка NER-датасета из PDF-корпуса с one-hot разметкой (distant supervision).

Источники по умолчанию:

    data/ground_truth_resumes_assembled.csv + data/resumes/*.pdf
    data/ground_truth_vacancies_assembled.csv + data/vacancies/*.pdf

Для каждого документа извлекается текст (``api.file_parser``), навыки из
разметки ищутся каскадом ``span_match.find_skill_spans`` (verbatim → ё//  →
морфология → алиасы), найденные спаны становятся entity «Skill». Навыки без
упоминания в тексте считаются шумом разметки и в обучение не попадают.

Выход: ``train.spacy`` / ``dev.spacy`` / ``test.spacy`` (DocBin, токенизатор
``spacy.blank("ru")``) и ``stats.json``. Сплит 80/10/10 детерминирован
(seed), стратифицирован по типу документа.

Запуск из корня проекта::

    python training/ner/build_ru_dataset.py
    python training/ner/build_ru_dataset.py --out training/ner/data/ru_v1 --seed 42
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import spacy  # noqa: E402
from spacy.tokens import DocBin  # noqa: E402

from api.file_parser import extract_text_from_file  # noqa: E402
from span_match import LABEL, build_entities, default_alias_map, split_ids  # noqa: E402

DATA = BASE_DIR / "data"

SOURCES = (
    ("resumes", "ground_truth_resumes_assembled.csv"),
    ("vacancies", "ground_truth_vacancies_assembled.csv"),
)


def read_labels(csv_path: Path) -> dict[str, list[str]]:
    """id -> список навыков с «1» (one-hot CSV)."""
    labels: dict[str, list[str]] = {}
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.DictReader(handle)
        if not rows.fieldnames or "id" not in rows.fieldnames:
            raise ValueError(f"CSV must have an id column: {csv_path}")
        for row in rows:
            num = str(row["id"]).strip()
            skills = [name.strip() for name, value in row.items()
                      if name != "id" and str(value).strip() == "1" and name.strip()]
            labels[num] = skills
    return labels


def build(out_dir: Path, seed: int, sources=SOURCES) -> dict:
    nlp = spacy.blank("ru")
    alias_map = default_alias_map()

    texts: dict[str, dict[str, tuple[str, list]]] = {}  # kind -> id -> (text, entities)
    stats: dict = {"seed": seed, "kinds": {}}
    totals = defaultdict(int)

    for kind, csv_name in sources:
        csv_path = DATA / csv_name
        pdf_dir = DATA / kind
        labels = read_labels(csv_path)
        kind_stats = {"documents": len(labels), "labeled_skills": 0,
                      "matched_skills": 0, "entities": 0}
        docs: dict[str, tuple[str, list]] = {}
        for num, skills in labels.items():
            pdf = pdf_dir / f"{num}.pdf"
            text = extract_text_from_file(pdf.read_bytes(), pdf.name) if pdf.is_file() else ""
            entities, st = build_entities(nlp, text, skills, alias_map)
            docs[num] = (text, entities)
            kind_stats["labeled_skills"] += st["matched_skills"] + st["unmatched_skills"]
            kind_stats["matched_skills"] += st["matched_skills"]
            kind_stats["entities"] += len(entities)
            totals["candidates_rejected"] += st["candidates_rejected"]
            totals["skipped_misaligned"] += st["skipped_misaligned"]
        kind_stats["coverage_pct"] = round(
            100 * kind_stats["matched_skills"] / kind_stats["labeled_skills"], 1
        ) if kind_stats["labeled_skills"] else 0.0
        stats["kinds"][kind] = kind_stats
        texts[kind] = docs

    # сплит: стратифицированно по типу, детерминированно
    splits: dict[str, dict[str, tuple[str, list]]] = {"train": {}, "dev": {}, "test": {}}
    stats["split_documents"] = {name: 0 for name in splits}
    for kind, docs in texts.items():
        train, dev, test = split_ids(list(docs), seed=seed)
        for name, ids in (("train", train), ("dev", dev), ("test", test)):
            for i in ids:
                splits[name][f"{kind}/{i}"] = docs[i]
                stats["split_documents"][name] += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, docs in splits.items():
        docbin = DocBin(store_user_data=False)
        for key, (text, entities) in docs.items():
            doc = nlp.make_doc(text)
            for start, end, label in entities:
                span = doc.char_span(start, end, label=label)
                if span is not None:  # build_entities уже выравнивал; защита от дрейфа
                    doc.ents = list(doc.ents) + [span]
            docbin.add(doc)
        docbin.to_disk(out_dir / f"{name}.spacy")

    stats["totals"] = dict(totals)
    stats["noise_estimate_pct"] = round(
        100 * sum(k["labeled_skills"] - k["matched_skills"] for k in stats["kinds"].values())
        / max(1, sum(k["labeled_skills"] for k in stats["kinds"].values())), 1)
    (out_dir / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=BASE_DIR / "training/ner/data/ru_v1")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    stats = build(args.out, args.seed)
    for kind, s in stats["kinds"].items():
        print(f"{kind}: документов={s['documents']} навыков={s['labeled_skills']} "
              f"найдено={s['matched_skills']} ({s['coverage_pct']}%) спанов={s['entities']}")
    print(f"сплит: {stats['split_documents']}")
    print(f"отброшено пересечений={stats['totals'].get('candidates_rejected', 0)} "
          f"пропущено невыровненных={stats['totals'].get('skipped_misaligned', 0)}")
    print(f"оценка шума разметки (навыки без упоминания): {stats['noise_estimate_pct']}%")
    print(f"выход: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
