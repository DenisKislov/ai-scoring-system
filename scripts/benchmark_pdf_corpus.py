"""Benchmark the upload-to-ranking pipeline on the local PDF corpus.

Run from the project root::

    .venv/bin/python scripts/benchmark_pdf_corpus.py

Only aggregate results are written. The CSV files label individual skills, not
vacancy/resume relevance. Ranking metrics therefore use labelled skill coverage
as a *proxy* and must not be presented as human-judged relevance metrics.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.file_parser import extract_text_from_file  # noqa: E402
from data.synthetic import generate_dataset  # noqa: E402
from db.builders import (  # noqa: E402
    experience_years,
    parse_raw_text_to_resume,
    resume_text,
    vacancy_text,
    logger as builders_logger,
)
from scorer.metrics import ndcg, precision_at_k, spearman  # noqa: E402
from scorer.scoring import rank_candidates  # noqa: E402
from scorer.skills_categories import CATEGORIES, SKILL_CATEGORIES, category_of  # noqa: E402


def normalized_skill(name: str) -> str:
    return name.strip().casefold()


def prf(counts: Counter) -> dict:
    tp, fp, fn = (counts[key] for key in ("tp", "fp", "fn"))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1}


def labels(kind: str) -> tuple[dict[str, dict[str, str]], dict]:
    path = ROOT / "data" / f"ground_truth_{kind}.csv"
    by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            by_id[row["id"]].append(
                {normalized_skill(skill): skill for skill, value in row.items()
                 if skill != "id" and str(value).strip() == "1"}
            )
    ambiguous = {doc_id for doc_id, variants in by_id.items()
                 if len({frozenset(variant) for variant in variants}) > 1}
    unambiguous = {doc_id: variants[0] for doc_id, variants in by_id.items()
                   if doc_id not in ambiguous}
    return unambiguous, {
        "csv_rows": sum(map(len, by_id.values())),
        "unique_ids": len(by_id),
        "ambiguous_ids": len(ambiguous),
        "duplicate_ids_same_labels": sum(len(v) > 1 and k not in ambiguous
                                         for k, v in by_id.items()),
        "ambiguous_pdf_count": sum(
            (ROOT / "data" / kind / f"{doc_id}.pdf").exists()
            for doc_id in ambiguous
        ),
    }


def read_corpus(kind: str) -> tuple[list[dict], dict]:
    truth, label_info = labels(kind)
    pdfs = sorted((ROOT / "data" / kind).glob("*.pdf"))
    records = []
    failures = Counter()
    start = time.perf_counter()
    for path in pdfs:
        try:
            raw = extract_text_from_file(path.read_bytes(), path.name)
            if not raw:
                failures["empty_text"] += 1
                continue
            parsed = parse_raw_text_to_resume(raw)
        except Exception:
            failures["parse_error"] += 1
            continue
        if path.stem not in truth:
            failures["without_unambiguous_label"] += 1
            continue
        records.append({
            "id": path.stem,
            "truth": truth[path.stem],
            "predicted": {normalized_skill(s): s for s in parsed["skills"]},
            "raw": raw,
            "parsed": parsed,
        })
    return records, {
        **label_info,
        "pdf_count": len(pdfs),
        "parsed_pdf_count": len(pdfs) - failures["empty_text"] - failures["parse_error"],
        "evaluated_count": len(records),
        "excluded": dict(failures),
        "parse_seconds": round(time.perf_counter() - start, 3),
    }


def extraction_metrics(records: list[dict]) -> dict:
    totals = Counter()
    by_category: dict[str, Counter] = {name: Counter() for name in CATEGORIES}
    canonical_categories = {normalized_skill(name): category
                            for name, category in SKILL_CATEGORIES.items()}
    for record in records:
        pred, true = set(record["predicted"]), set(record["truth"])
        for outcome, skills in (("tp", pred & true), ("fp", pred - true),
                                ("fn", true - pred)):
            totals[outcome] += len(skills)
            for skill in skills:
                display = record["predicted"].get(skill) or record["truth"].get(skill)
                category = canonical_categories.get(skill, category_of(display))
                by_category[category][outcome] += 1
    return {
        "micro": prf(totals),
        "by_category": {category: prf(by_category[category]) for category in CATEGORIES},
    }


def rank_metrics(resumes: list[dict], vacancies: list[dict]) -> dict:
    ids = [r["id"] for r in resumes]
    resume_docs = [{
        "title": r["parsed"]["title"],
        "specialization": r["parsed"]["specialization"],
        "experience": r["parsed"]["experience"],
        "skills": r["parsed"]["skills"],
        "tags": r["parsed"]["tags"],
    } for r in resumes]
    texts = [resume_text(doc) for doc in resume_docs]
    skills = [set(doc["skills"]) for doc in resume_docs]
    years = {r["id"]: experience_years(doc) for r, doc in zip(resumes, resume_docs)}
    truth = {r["id"]: set(r["truth"]) for r in resumes}

    rows = []
    zero_overlap_pairs = high_score_zero_overlap = 0
    max_zero_overlap_score = 0
    score_changes = []
    start = time.perf_counter()
    for index, vacancy in enumerate(vacancies):
        vac_truth = set(vacancy["truth"])
        vac_doc = {"title": vacancy["id"], "description": vacancy["raw"],
                   "skills": vacancy["parsed"]["skills"]}
        vac_text = vacancy_text(vac_doc)
        ranked = rank_candidates(
            vac_text, texts, candidate_ids=ids,
            vacancy_skills=set(vac_doc["skills"]), resume_skills_list=skills,
        )
        ranked.sort(key=lambda r: (r["score"], years[r["candidate_id"]] or 0),
                    reverse=True)
        coverage = {rid: len(vac_truth & truth[rid]) / len(vac_truth)
                    if vac_truth else 0.0 for rid in ids}
        ordered_truth = [coverage[r["candidate_id"]] for r in ranked]
        scores = {r["candidate_id"]: r["score"] for r in ranked}
        positive = sum(value >= 0.5 for value in coverage.values())
        nonzero = sum(value > 0 for value in coverage.values())
        if nonzero:
            rows.append({
                "ndcg_at_10": ndcg(ordered_truth, k=10),
                "ndcg_all": ndcg(ordered_truth),
                "precision_at_5_threshold_0_5": precision_at_k(ordered_truth, 5, 0.5),
                "spearman": spearman([scores[rid] for rid in ids],
                                     [coverage[rid] for rid in ids]),
                "positives_at_0_5": positive,
            })
        for result in ranked:
            if coverage[result["candidate_id"]] == 0:
                zero_overlap_pairs += 1
                if result["score"] > 30:
                    high_score_zero_overlap += 1
                max_zero_overlap_score = max(max_zero_overlap_score, result["score"])

        # A fixed pair's score should be independent of the other candidates.
        if index < min(5, len(vacancies)):
            subset = rank_candidates(
                vac_text, texts[:20], candidate_ids=ids[:20],
                vacancy_skills=set(vac_doc["skills"]), resume_skills_list=skills[:20],
            )
            score_changes.extend(abs(scores[r["candidate_id"]] - r["score"])
                                 for r in subset)
        if (index + 1) % 8 == 0:
            print(f"Ranked {index + 1}/{len(vacancies)} vacancies", flush=True)

    def mean(key: str) -> float | None:
        return statistics.mean(row[key] for row in rows) if rows else None

    return {
        "vacancies_ranked": len(vacancies),
        "resumes_per_vacancy": len(resumes),
        "pairs": len(vacancies) * len(resumes),
        "vacancies_with_nonzero_proxy_relevance": len(rows),
        "vacancies_with_positive_at_0_5": sum(row["positives_at_0_5"] > 0
                                               for row in rows),
        "proxy_mean_ndcg_at_10": mean("ndcg_at_10"),
        "proxy_mean_ndcg_all": mean("ndcg_all"),
        "proxy_mean_precision_at_5_threshold_0_5": mean("precision_at_5_threshold_0_5"),
        "proxy_mean_spearman": mean("spearman"),
        "zero_overlap_pairs": zero_overlap_pairs,
        "zero_overlap_pairs_score_above_30": high_score_zero_overlap,
        "max_zero_overlap_score": max_zero_overlap_score,
        "pool_independence_pairs_checked": len(score_changes),
        "pool_independence_scores_changed": sum(delta > 0 for delta in score_changes),
        "pool_independence_max_score_delta": max(score_changes, default=0),
        "rank_seconds": round(time.perf_counter() - start, 3),
    }


def synthetic_metrics() -> dict:
    """Evaluate the specification's labelled synthetic ranking criterion."""
    rows = []
    for entry in generate_dataset(n_vacancies=6, n_resumes=20, seed=42):
        candidates = entry["candidates"]
        ranked = rank_candidates(
            entry["vacancy"]["text"], [candidate["text"] for candidate in candidates]
        )
        truth = {index: candidate["true_relevance"]
                 for index, candidate in enumerate(candidates)}
        ordered_truth = [truth[result["candidate_id"]] for result in ranked]
        scores = {result["candidate_id"]: result["score"] for result in ranked}
        rows.append({
            "ndcg_at_10": ndcg(ordered_truth, k=10),
            "ndcg_all": ndcg(ordered_truth),
            "precision_at_5": precision_at_k(ordered_truth, k=5, threshold=0.5),
            "spearman_score": spearman([scores[i] for i in range(len(candidates))],
                                       [truth[i] for i in range(len(candidates))]),
        })

    def mean(key: str) -> float:
        return statistics.mean(row[key] for row in rows)

    mean_ndcg = mean("ndcg_at_10")
    return {
        "vacancies": len(rows),
        "resumes_per_vacancy": 20,
        "seed": 42,
        "mean_ndcg_at_10": mean_ndcg,
        "mean_ndcg_all": mean("ndcg_all"),
        "mean_precision_at_5": mean("precision_at_5"),
        "mean_spearman_score": mean("spearman_score"),
        "ndcg_at_10_requirement": 0.8,
        "ndcg_at_10_passed": mean_ndcg >= 0.8,
    }


def control_pair_metrics() -> dict:
    """A plainly unrelated pair for the explicit ≤30 and order requirement."""
    vacancy = "Требуется Python-разработчик: Python, Django, PostgreSQL, Git."
    relevant = "Python-разработчик: Python, Django, PostgreSQL, Git, REST API."
    irrelevant = "Работал поваром: борщ, компоты, выпечка."
    ranked = rank_candidates(vacancy, [relevant, irrelevant],
                             candidate_ids=["relevant", "irrelevant"])
    by_id = {result["candidate_id"]: result for result in ranked}
    return {
        "relevant_score": by_id["relevant"]["score"],
        "irrelevant_score": by_id["irrelevant"]["score"],
        "irrelevant_score_at_most_30": by_id["irrelevant"]["score"] <= 30,
        "irrelevant_ranked_below_relevant": ranked[0]["candidate_id"] == "relevant",
    }


def markdown(report: dict) -> str:
    def pct(value: float | None) -> str:
        return "н/д" if value is None else f"{value:.3f}"

    lines = [
        "# Бенчмарк скорера на PDF-корпусе",
        "",
        f"Дата (UTC): {report['timestamp_utc']}",
        "",
        "## Метод",
        "",
        "PDF обрабатываются через `api.file_parser.extract_text_from_file`, "
        "`db.builders.parse_raw_text_to_resume` и `scorer.scoring.rank_candidates`. "
        "Для ранжирования применяется тот же текст и разбор навыков, что при загрузке "
        "документов через API; порядок при равном Score уточняется опытом, как в `scorer.service`.",
        "",
        "Эталон навыков — `data/ground_truth_resumes.csv` и "
        "`data/ground_truth_vacancies.csv`. Сопоставление только по точному ID имени PDF; "
        "ID с противоречивыми строками CSV исключены. Сравнение навыков "
        "регистронезависимое, на уровне документа; TP/FP/FN суммируются до расчёта P/R/F1.",
        "",
        "**Экспертной разметки релевантности пар нет.** Для ранжирования "
        "использован только диагностический proxy: доля размеченных навыков вакансии, "
        "присутствующих среди размеченных навыков резюме. Это не оценка качества "
        "подбора людей и не подтверждение порога nDCG@10 ≥ 0.80 из ТЗ. "
        "P@5 использует порог proxy ≥ 0.5, как реализация `precision_at_k`.",
        "",
        "## Покрытие корпуса",
        "",
        "| Корпус | PDF | Прочитано | С разметкой | Конфликтных ID в CSV | PDF с конфликтным ID |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for kind, title in (("resumes", "Резюме"), ("vacancies", "Вакансии")):
        row = report["corpus"][kind]
        lines.append(f"| {title} | {row['pdf_count']} | {row['parsed_pdf_count']} | "
                     f"{row['evaluated_count']} | "
                     f"{row['ambiguous_ids']} | {row['ambiguous_pdf_count']} |")
    lines += ["", "## Извлечение навыков", "",
              "| Корпус | Precision | Recall | F1 | TP | FP | FN |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for kind, title in (("resumes", "Резюме"), ("vacancies", "Вакансии")):
        m = report["extraction"][kind]["micro"]
        lines.append(f"| {title} | {pct(m['precision'])} | {pct(m['recall'])} | "
                     f"{pct(m['f1'])} | {m['tp']} | {m['fp']} | {m['fn']} |")
    for kind, title in (("resumes", "резюме"), ("vacancies", "вакансий")):
        lines += ["", f"### По категориям {title}", "",
                  "| Категория | Precision | Recall | F1 | TP | FP | FN |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        for category, m in report["extraction"][kind]["by_category"].items():
            lines.append(f"| {category} | {pct(m['precision'])} | {pct(m['recall'])} | "
                         f"{pct(m['f1'])} | {m['tp']} | {m['fp']} | {m['fn']} |")
    rank = report["ranking"]
    lines += ["", "## Ранжирование по proxy-разметке", "",
              f"Оценено {rank['pairs']} пар: {rank['vacancies_ranked']} вакансии × "
              f"{rank['resumes_per_vacancy']} резюме. У "
              f"{rank['vacancies_with_nonzero_proxy_relevance']} вакансий есть хотя бы "
              "одно ненулевое пересечение навыков; средние ниже рассчитаны по ним.",
              "", "| Метрика | Среднее |", "|---|---:|",
              f"| nDCG@10 (proxy) | {pct(rank['proxy_mean_ndcg_at_10'])} |",
              f"| nDCG (proxy) | {pct(rank['proxy_mean_ndcg_all'])} |",
              f"| Precision@5, proxy ≥ 0.5 | {pct(rank['proxy_mean_precision_at_5_threshold_0_5'])} |",
              f"| Spearman(Score, proxy) | {pct(rank['proxy_mean_spearman'])} |",
              "",
              f"Вакансий с хотя бы одним кандидатом при proxy ≥ 0.5: "
              f"{rank['vacancies_with_positive_at_0_5']}. Нулевое пересечение навыков: "
              f"{rank['zero_overlap_pairs']} пар, из них Score > 30 у "
              f"{rank['zero_overlap_pairs_score_above_30']}; максимальный Score "
              f"{rank['max_zero_overlap_score']}.",
              "",
              f"Проверка независимости Score от пула: {rank['pool_independence_pairs_checked']} "
              f"общих пар в полном пуле и пуле из 20 резюме; Score изменился у "
              f"{rank['pool_independence_scores_changed']}, максимальная разница "
              f"{rank['pool_independence_max_score_delta']} пунктов.",
              "",
              "## Синтетический набор с известной релевантностью", ""]
    synthetic = report["synthetic"]
    lines += [
        f"Существующий генератор `data.synthetic.generate_dataset`: "
        f"{synthetic['vacancies']} вакансий × {synthetic['resumes_per_vacancy']} "
        f"резюме, seed={synthetic['seed']}. Spearman рассчитан именно по "
        "целочисленному Score, как сформулировано в ТЗ.",
        "", "| Метрика | Среднее |", "|---|---:|",
        f"| nDCG@10 | {pct(synthetic['mean_ndcg_at_10'])} |",
        f"| nDCG | {pct(synthetic['mean_ndcg_all'])} |",
        f"| Precision@5 | {pct(synthetic['mean_precision_at_5'])} |",
        f"| Spearman(Score, истинная релевантность) | "
        f"{pct(synthetic['mean_spearman_score'])} |",
        "",
        f"Порог ТЗ nDCG@10 ≥ {synthetic['ndcg_at_10_requirement']:.2f}: "
        f"{'выполнен' if synthetic['ndcg_at_10_passed'] else 'не выполнен'}.",
        "Это короткий контроль на 6 вакансиях × 20 резюме с одним seed. "
        "Основной бенчмарк обновлённой синтетики на трёх seed: "
        "[synthetic_benchmark.md](synthetic_benchmark.md).",
        "",
        "## Контроль заведомо нерелевантной пары",
        "",
        "Фиксированная тестовая вакансия Python-разработчика; релевантный "
        "кандидат владеет Python, Django, PostgreSQL и Git, нерелевантный — "
        "повар без перечисленных навыков. Прогон через `rank_candidates`.",
        "",
        f"Score релевантного: {report['control_pair']['relevant_score']}; "
        f"нерелевантного: {report['control_pair']['irrelevant_score']}. "
        f"Условие Score ≤ 30: "
        f"{'выполнено' if report['control_pair']['irrelevant_score_at_most_30'] else 'не выполнено'}; "
        f"ранжирование ниже релевантного: "
        f"{'выполнено' if report['control_pair']['irrelevant_ranked_below_relevant'] else 'не выполнено'}.",
        "",
        "Разметка навыков CSV может не перечислять все навыки, упомянутые в PDF. "
        "Поэтому часть FP может означать неполную разметку, а не ошибку парсера. "
        "Для настоящих метрик ранжирования на PDF нужна независимая экспертная "
        "оценка релевантности пар «вакансия — резюме». Синтетический набор "
        "проверяет алгоритм, но не заменяет эту оценку.", "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    # The parser logs extracted skills and resume titles. Keep benchmark output
    # aggregate-only and avoid writing personal data to logs.
    builders_logger.disabled = True
    resumes, resume_info = read_corpus("resumes")
    vacancies, vacancy_info = read_corpus("vacancies")
    if not resumes or not vacancies:
        raise RuntimeError("No unambiguously labelled PDF resumes or vacancies")
    print(f"Parsed {len(resumes)} labelled resumes and "
          f"{len(vacancies)} labelled vacancies", flush=True)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "corpus": {"resumes": resume_info, "vacancies": vacancy_info},
        "extraction": {
            "resumes": extraction_metrics(resumes),
            "vacancies": extraction_metrics(vacancies),
        },
        "ranking": rank_metrics(resumes, vacancies),
        "synthetic": synthetic_metrics(),
        "control_pair": control_pair_metrics(),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "pdf_benchmark.json"
    md_path = args.output_dir / "pdf_benchmark.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    md_path.write_text(markdown(report), encoding="utf-8")
    print(f"Saved {json_path} and {md_path}", flush=True)


if __name__ == "__main__":
    main()
