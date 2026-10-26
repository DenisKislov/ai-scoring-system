"""Append labelled PDF records to the SuperJob JSON corpora.

Despite its historical filename, defaults use canonical data/ground_truth_*.csv
and data/{resumes,vacancies}/. Alternate source paths must be selected explicitly.
Existing records (including their labels) are preserved; duplicate JSON IDs keep
the last revision. This is an append procedure, not label synchronisation.

    python scripts/extend_datasets_from_assembled.py --dry-run
    python scripts/extend_datasets_from_assembled.py --resume-csv path/to/source.csv \
        --resume-pdf path/to/resumes --dry-run
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from api.file_parser import extract_text_from_file  # noqa: E402

DATA = BASE_DIR / "data"
RESUME_JSON = DATA / "dataset_resume.json"
VAC_JSON = DATA / "superjob_dataset.json"
RESUME_CSV = DATA / "ground_truth_resumes.csv"
VAC_CSV = DATA / "ground_truth_vacancies.csv"
RESUME_PDF = DATA / "resumes"
VAC_PDF = DATA / "vacancies"

_HEADER_NOISE = re.compile(
    r"^(?:обновлен[аы]?\b|№|дата|город:?\s*$|\d{1,2}\s+[а-яё]+\s+\d{4}\s*$)",
    re.IGNORECASE,
)


def _read_labels(path: Path) -> dict[str, list[str]]:
    labels = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        if not rows.fieldnames or "id" not in rows.fieldnames:
            raise ValueError(f"CSV must have an id column: {path}")
        for row in rows:
            num = str(row["id"]).strip()
            if not num.isdecimal():
                raise ValueError(f"PDF IDs must be decimal filenames: {path}")
            skills = [name for name, value in row.items()
                      if name != "id" and str(value).strip() == "1"]
            if num in labels and set(labels[num]) != set(skills):
                raise ValueError(f"Conflicting CSV labels for id {num}: {path}")
            labels[num] = skills
    return labels


def _pdf_text(pdf_dir: Path, num: str) -> str:
    path = pdf_dir / f"{num}.pdf"
    return extract_text_from_file(path.read_bytes(), path.name) if path.is_file() else ""


def _guess_vacancy_title(text: str) -> str:
    for line in text.splitlines():
        value = line.strip(" —-|")
        if len(value) >= 4 and not _HEADER_NOISE.match(value):
            return value[:120]
    return ""


def process(kind: str, json_path: Path, csv_path: Path, pdf_dir: Path,
            prefix: str, dry_run: bool) -> dict:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    labels = _read_labels(csv_path)
    deduped, seen = [], set()
    for record in reversed(data):
        if record["id"] not in seen:
            seen.add(record["id"])
            deduped.append(record)
    deduped.reverse()
    removed_dupes = len(data) - len(deduped)
    added, no_pdf = [], []
    for num, skills in labels.items():
        record_id = f"{prefix}{num}"
        if record_id in seen:
            continue
        text = _pdf_text(pdf_dir, num)
        if not text.strip():
            no_pdf.append(num)
            continue
        record = {"id": record_id, "expected_skills": skills,
                  "raw_text": text, "_source": "pdf_corpus"}
        if kind == "vacancies":
            record["vacancy"] = _guess_vacancy_title(text)
        deduped.append(record)
        seen.add(record_id)
        added.append(num)
    if not dry_run and (removed_dupes or added):
        json_path.write_text(json.dumps(deduped, ensure_ascii=False, indent=1) + "\n",
                             encoding="utf-8")
    return {"kind": kind, "before": len(data), "dupes_removed": removed_dupes,
            "added": added, "no_pdf": no_pdf, "after": len(deduped),
            "source_csv": str(csv_path), "source_pdf": str(pdf_dir)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="only report; do not change JSON")
    parser.add_argument("--resume-json", type=Path, default=RESUME_JSON)
    parser.add_argument("--vacancy-json", type=Path, default=VAC_JSON)
    parser.add_argument("--resume-csv", type=Path, default=RESUME_CSV)
    parser.add_argument("--vacancy-csv", type=Path, default=VAC_CSV)
    parser.add_argument("--resume-pdf", type=Path, default=RESUME_PDF)
    parser.add_argument("--vacancy-pdf", type=Path, default=VAC_PDF)
    args = parser.parse_args()
    sources = (("resumes", args.resume_json, args.resume_csv, args.resume_pdf, "sj_r_"),
               ("vacancies", args.vacancy_json, args.vacancy_csv, args.vacancy_pdf, "sj_"))
    for _, json_path, csv_path, pdf_dir, _ in sources:
        if not json_path.is_file() or not csv_path.is_file() or not pdf_dir.is_dir():
            parser.error(f"Missing source: {json_path}, {csv_path} or {pdf_dir}")
        _read_labels(csv_path)  # validate both sets before any JSON is changed
    for kind, json_path, csv_path, pdf_dir, prefix in sources:
        summary = process(kind, json_path, csv_path, pdf_dir, prefix, args.dry_run)
        mode = "DRY-RUN " if args.dry_run else ""
        print(f"[{mode}{kind}] {summary['before']} -> {summary['after']}; "
              f"duplicate IDs removed: {summary['dupes_removed']}; "
              f"new PDF records: {len(summary['added'])}; "
              f"labels without a readable PDF: {len(summary['no_pdf'])}")
        print(f"  CSV: {csv_path}; PDF: {pdf_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
