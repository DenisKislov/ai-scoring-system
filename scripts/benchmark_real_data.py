"""Diagnostic benchmark on the baseline labelled SuperJob JSON corpus.

Extraction is measured against expected_skills, document by document. Ranking
uses labelled skill coverage as a proxy, not expert relevance of people to jobs.
The default annotated mode reproduces the baseline known-skill ranking test.
The explicit extracted mode measures the additional skill-extraction stage.

Examples::

    python scripts/benchmark_real_data.py  # baseline protocol: first 10, annotated skills, threshold 0.1
    python scripts/benchmark_real_data.py --limit 0
    python scripts/benchmark_real_data.py --limit 0 --threshold 0.1
    python scripts/benchmark_real_data.py --limit 10 --ranking-inputs extracted

A threshold of 0.1 permits the relevance convention described by the PMI; running
this script alone does not establish acceptance against the complete PMI.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import warnings
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from scorer import extract_skills, rank_candidates  # noqa: E402
from scorer.metrics import ndcg, precision_at_k, recall_at_k, spearman  # noqa: E402
from scorer.skills import normalize_skill_set  # noqa: E402

VAC_PATH = BASE_DIR / "data" / "superjob_dataset.json"
RES_PATH = BASE_DIR / "data" / "dataset_resume.json"


def vacancy_text_of(item: dict) -> str:
    body = []
    if item.get("responsibilities"):
        body.append(f"Обязанности: {item['responsibilities']}")
    if item.get("requirements"):
        body.append(f"Требования: {item['requirements']}")
    if body:
        return "\n\n".join([item.get("vacancy") or ""] + body).strip()
    return item.get("raw_text") or item.get("vacancy") or ""


def resume_text_of(item: dict) -> str:
    parts = []
    if item.get("career_goal"):
        parts.append(f"Цель: {item['career_goal']}")
    if item.get("key_strengths"):
        parts.append(f"Ключевые навыки и сильные стороны: {item['key_strengths']}")
    positions = item.get("previously_held_positions") or []
    if positions:
        exp_text = "\n".join(
            f"- {p.get('position', '')} в {p.get('company', '')} "
            f"({p.get('period', '')}): {p.get('responsibilities', '')}"
            for p in positions
        )
        parts.append(f"Опыт работы:\n{exp_text}")
    return "\n\n".join(p for p in parts if p).strip() or item.get("raw_text") or ""


def gt_skills(item: dict) -> set:
    return normalize_skill_set({s for s in item.get("expected_skills", []) if s})


def extraction_metrics(items: list[dict], text_of,
                       predicted_skills: list[set] | None = None) -> dict:
    """Micro P/R/F1; keep rich excerpts and full PDF texts visible separately."""
    if predicted_skills is None:
        predicted_skills = [set(extract_skills(text_of(item))) for item in items]
    if len(predicted_skills) != len(items):
        raise ValueError("predicted_skills must align with documents")
    groups = defaultdict(Counter)
    for item, predicted in zip(items, predicted_skills):
        truth = {s.casefold() for s in gt_skills(item)}
        pred = {s.casefold() for s in normalize_skill_set(predicted)}
        counts = Counter(tp=len(truth & pred), fp=len(pred - truth), fn=len(truth - pred),
                         documents=1, documents_without_labels=int(not truth))
        groups[item.get("_source") or "rich-json"].update(counts)
    totals = Counter()
    for counts in groups.values():
        totals.update(counts)

    def report(counts):
        tp, fp, fn = (counts[key] for key in ("tp", "fp", "fn"))
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        return {**counts, "precision": p, "recall": r,
                "f1": 2 * p * r / (p + r) if p + r else 0.0}

    return {"micro": report(totals),
            "by_source": {name: report(counts) for name, counts in sorted(groups.items())}}


def experience_doc(item: dict) -> dict:
    positions = item.get("previously_held_positions") or []
    if item.get("experience"):
        experience = str(item["experience"])
    elif positions:
        experience = "Опыт работы:\n" + "\n".join(
            f"- {p.get('position', '')} ({p.get('period', '')})" for p in positions)
    else:
        experience = ""
    return {"experience": experience, "_raw_text": resume_text_of(item)}


def evaluate(vacancies: list[dict], resumes: list[dict], threshold: float = 0.1,
             ranking_inputs: str = "annotated") -> dict:
    if not vacancies or not resumes:
        raise ValueError("Both JSON corpora must contain documents")
    if not 0 < threshold <= 1:
        raise ValueError("threshold must be in (0, 1]")
    if ranking_inputs not in {"extracted", "annotated"}:
        raise ValueError("ranking_inputs must be extracted or annotated")
    res_texts = [resume_text_of(r) for r in resumes]
    res_skills = [gt_skills(r) for r in resumes]
    vac_texts = [vacancy_text_of(vac) for vac in vacancies]
    vac_skills = [gt_skills(vac) for vac in vacancies]
    # Production parses each uploaded document once and stores its skills.
    # Cache text-derived sets independently of expected_skills: the same resume
    # must not be re-extracted for every vacancy in the all-pairs benchmark.
    preparation_start = time.perf_counter()
    extracted_resumes = [set(extract_skills(text)) for text in res_texts]
    extracted_vacancies = [set(extract_skills(text)) for text in vac_texts]
    preparation_elapsed = time.perf_counter() - preparation_start
    rows, all_scores, all_kw = [], [], []
    start = time.perf_counter()
    for index, (v_text, v_skills) in enumerate(zip(vac_texts, vac_skills)):
        kwargs = {"vacancy_skills": extracted_vacancies[index],
                  "resume_skills_list": extracted_resumes}
        if ranking_inputs == "annotated":
            # Keep the baseline known-skill scenario, explicitly labelled oracle.
            v_text = " ".join([v_text, " ".join(sorted(v_skills))])
            kwargs = {"vacancy_skills": v_skills, "resume_skills_list": res_skills}
        true_rels = [len(v_skills & rs) / len(v_skills) if v_skills else 0.0
                     for rs in res_skills]
        ranked = rank_candidates(v_text, res_texts, **kwargs)
        scores = {row["candidate_id"]: row["score"] for row in ranked}
        ordered = [true_rels[row["candidate_id"]] for row in ranked]
        rows.append({
            "ndcg_at_10": ndcg(ordered, k=10),
            "precision_at_5": precision_at_k(ordered, 5, threshold),
            "precision_at_10": precision_at_k(ordered, 10, threshold),
            "recall_at_10": recall_at_k(ordered, 10, threshold),
            "recall_at_50": recall_at_k(ordered, 50, threshold),
            "spearman_score": spearman([scores[i] for i in range(len(resumes))], true_rels),
            "relevant_candidates": sum(r >= threshold for r in true_rels),
        })
        all_scores.extend(scores.values())
        all_kw.extend(row["keyword_score"] for row in ranked)
    elapsed = time.perf_counter() - start

    means = {}
    denominators = {}
    for key in ("ndcg_at_10", "precision_at_5", "precision_at_10", "recall_at_10",
                "recall_at_50", "spearman_score"):
        values = [row[key] for row in rows if row[key] is not None]
        means[key] = statistics.mean(values) if values else None
        denominators[key] = len(values)

    from db.builders import experience_years
    found = sum(experience_years(experience_doc(item)) is not None for item in resumes)
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "configuration": {"protocol_version": "integrated_baseline_json_v1",
                          "ranking_inputs": ranking_inputs,
                          "binary_relevance_threshold": threshold,
                          "relevance_source": "normalised expected_skills coverage proxy",
                          "skill_extraction": "once_per_document_from_text",
                          "expert_pair_relevance": False},
        "corpus": {"vacancies": len(vacancies), "resumes": len(resumes),
                   "pairs": len(vacancies) * len(resumes),
                   "queries_without_relevant_candidates": sum(not r["relevant_candidates"] for r in rows)},
        "extraction": {"vacancies": extraction_metrics(vacancies, vacancy_text_of, extracted_vacancies),
                       "resumes": extraction_metrics(resumes, resume_text_of, extracted_resumes),
                       "seconds": round(preparation_elapsed, 3)},
        "ranking": {"mean": means, "queries_per_metric": denominators,
                    "seconds": round(elapsed, 3)},
        "scores": {"mean": statistics.mean(all_scores), "median": statistics.median(all_scores),
                   "max": max(all_scores), "keyword_mean": statistics.mean(all_kw)},
        "experience": {"documents_with_number": found, "documents": len(resumes),
                       "coverage": found / len(resumes), "accuracy_measured": False},
    }


def markdown(report: dict) -> str:
    cfg, corpus, ranking = (report[key] for key in ("configuration", "corpus", "ranking"))
    mode = ("навыки однократно извлекаются скорером из текстов, как при загрузке документов" if cfg["ranking_inputs"] == "extracted"
            else "oracle: размеченные expected_skills переданы скореру, а навыки вакансии добавлены в её текст")
    lines = ["# Диагностический бенчмарк JSON-корпуса", "",
             f"Дата (UTC): {report['timestamp_utc']}", "",
             f"Версия протокола: `{cfg['protocol_version']}`.", "",
             f"{corpus['vacancies']} вакансий × {corpus['resumes']} резюме = {corpus['pairs']} пар.",
             f"Вход ранжирования: **{cfg['ranking_inputs']}** — {mode}.", "",
             "**Релевантность — proxy покрытия размеченных навыков, а не экспертная оценка пар.** "
             "Режим annotated изолирует матчинг от ошибок извлечения и не оценивает загрузку PDF.",
             f"Бинарный порог для Precision/Recall: **≥ {cfg['binary_relevance_threshold']}**. "
             "NDCG и Spearman используют непрерывное покрытие.", "",
             "## Извлечение навыков", "",
             "На каждом документе сравниваются нормализованные expected_skills и навыки, "
             "извлечённые из текста. TP/FP/FN суммируются до вычисления micro P/R/F1. "
             "Полные PDF-тексты и rich-json выдержки показаны раздельно; неполная разметка "
             "может давать ложные FP.", "",
             "| Корпус / источник | Документов | Precision | Recall | F1 | TP | FP | FN |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for kind, title in (("vacancies", "Вакансии"), ("resumes", "Резюме")):
        extraction = report["extraction"][kind]
        for name, m in [("итого", extraction["micro"]), *extraction["by_source"].items()]:
            lines.append(f"| {title}: {name} | {m['documents']} | {m['precision']:.3f} | "
                         f"{m['recall']:.3f} | {m['f1']:.3f} | {m['tp']} | {m['fp']} | {m['fn']} |")
    lines += ["", "## Ранжирование по proxy-разметке", "",
              "| Метрика | Среднее | Вакансий в среднем |", "|---|---:|---:|"]
    names = {"ndcg_at_10": "NDCG@10", "precision_at_5": "Precision@5", "precision_at_10": "Precision@10",
             "recall_at_10": "Recall@10", "recall_at_50": "Recall@50", "spearman_score": "Spearman(Score, proxy)"}
    for key, name in names.items():
        value = ranking["mean"][key]
        display = "н/д" if value is None else f"{value:.3f}"
        lines.append(f"| {name} | {display} | {ranking['queries_per_metric'][key]} |")
    exp = report["experience"]
    lines += ["", f"Вакансий без кандидатов выше порога: {corpus['queries_without_relevant_candidates']}. "
              "Recall усредняется только там, где есть релевантные кандидаты; "
              "Precision, NDCG и Spearman — по всем вакансиям (нулевой ideal DCG даёт NDCG=0).",
              f"Время ранжирования: {ranking['seconds']:.3f} с.", "",
              f"Число опыта распознано у {exp['documents_with_number']}/{exp['documents']} "
              f"резюме ({exp['coverage']:.1%}). Это покрытие парсера; правильность числа здесь не проверяется.", "",
              "Порог 0.1 можно выбрать для сопоставления с методикой ПМИ, но этот отчёт "
              "не подтверждает полный ПМИ: здесь нет экспертной разметки релевантности, "
              "проверки интерфейса и сравнения пулов 10/200.", ""]
    return "\n".join(lines)


def main() -> int:
    warnings.filterwarnings("ignore", message="An input array is constant")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10, help="число вакансий; 0 = все")
    parser.add_argument("--threshold", type=float, default=0.1,
                        help="бинарный порог proxy-релевантности (исходный протокол и ПМИ: 0.1)")
    parser.add_argument("--ranking-inputs", choices=("extracted", "annotated"), default="annotated")
    parser.add_argument("--output-dir", type=Path, default=BASE_DIR / "reports" / "baseline_benchmark")
    parser.add_argument("--output-prefix", default="real_data_benchmark")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    if not 0 < args.threshold <= 1:
        parser.error("--threshold must be in (0, 1]")
    if Path(args.output_prefix).name != args.output_prefix:
        parser.error("--output-prefix must be a filename prefix")
    vacancies = json.loads(VAC_PATH.read_text(encoding="utf-8"))
    resumes = json.loads(RES_PATH.read_text(encoding="utf-8"))
    if args.limit:
        vacancies = vacancies[:args.limit]
    report = evaluate(vacancies, resumes, args.threshold, args.ranking_inputs)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / f"{args.output_prefix}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / f"{args.output_prefix}.md").write_text(markdown(report), encoding="utf-8")
    print(markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
