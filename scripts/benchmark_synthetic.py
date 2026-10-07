"""Reproducible ranking benchmark on the more realistic synthetic corpus.

Run from the project root::

    .venv/bin/python scripts/benchmark_synthetic.py

Binary relevance for P@K, R@K, MAP and MRR is true_relevance >= 0.65.
nDCG@K uses the full graded true_relevance value. Neither label is inferred
from the rendered text or the scorer output.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.synthetic import generate_dataset  # noqa: E402
from scorer.metrics import ndcg, spearman  # noqa: E402
from scorer.scoring import rank_candidates  # noqa: E402


def ranking_metrics(
    ranked: list[dict], truths: list[float], k: int, threshold: float
) -> dict:
    ordered = [truths[result["candidate_id"]] for result in ranked]
    relevant = [value >= threshold for value in ordered]
    positives = sum(relevant)
    hits = sum(relevant[:k])
    average_precision = 0.0
    reciprocal_rank = 0.0
    seen = 0
    for rank, is_relevant in enumerate(relevant, start=1):
        if is_relevant:
            seen += 1
            average_precision += seen / rank
            if reciprocal_rank == 0:
                reciprocal_rank = 1 / rank
    scores = {result["candidate_id"]: result["score"] for result in ranked}
    return {
        "precision_at_k": hits / k,
        "recall_at_k": hits / positives if positives else 0.0,
        "average_precision": average_precision / positives if positives else 0.0,
        "reciprocal_rank": reciprocal_rank,
        "ndcg_at_k": ndcg(ordered, k=k),
        "spearman_score": spearman(
            [scores[i] for i in range(len(truths))], truths
        ),
        "positive_count": positives,
    }


def evaluate(
    seeds: tuple[int, ...] = (42, 7, 99),
    vacancies: int = 12,
    resumes: int = 30,
    k: int = 10,
    threshold: float = 0.65,
) -> dict:
    if k < 1 or k > resumes:
        raise ValueError("k must be between 1 and resumes")
    if not 0 < threshold <= 1:
        raise ValueError("threshold must be in (0, 1]")
    rows = []
    corpus = []
    for seed in seeds:
        dataset = generate_dataset(vacancies, resumes, seed)
        corpus.extend(dataset)
        for entry in dataset:
            candidates = entry["candidates"]
            ranked = rank_candidates(
                entry["vacancy"]["text"],
                [candidate["text"] for candidate in candidates],
            )
            row = ranking_metrics(
                ranked, [candidate["true_relevance"] for candidate in candidates],
                k, threshold,
            )
            rows.append({"seed": seed, "role": entry["vacancy"]["role"], **row})

    keys = (
        "precision_at_k", "recall_at_k", "average_precision",
        "reciprocal_rank", "ndcg_at_k", "spearman_score",
    )
    means = {key: statistics.mean(row[key] for row in rows) for key in keys}
    by_seed = {
        str(seed): {key: statistics.mean(row[key] for row in rows if row["seed"] == seed)
                    for key in keys}
        for seed in seeds
    }
    all_candidates = [candidate for entry in corpus for candidate in entry["candidates"]]
    all_vacancies = [entry["vacancy"] for entry in corpus]
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "configuration": {
            "seeds": list(seeds), "vacancies_per_seed": vacancies,
            "resumes_per_vacancy": resumes, "k": k,
            "binary_relevance_threshold": threshold,
        },
        "corpus": {
            "queries": len(rows), "resumes": len(all_candidates),
            "roles": sorted({item["role"] for item in all_vacancies}),
            "vacancy_skill_count_median": statistics.median(len(v["skills"]) for v in all_vacancies),
            "resume_latent_skill_count_median": statistics.median(len(c["skills"]) for c in all_candidates),
            "resume_visible_skill_count_median": statistics.median(len(c["text_skills"]) for c in all_candidates),
            "vacancy_text_chars_median": statistics.median(len(v["text"]) for v in all_vacancies),
            "resume_text_chars_median": statistics.median(len(c["text"]) for c in all_candidates),
            "positive_pairs": sum(c["true_relevance"] >= threshold for c in all_candidates),
            "queries_without_positives": sum(row["positive_count"] == 0 for row in rows),
        },
        "mean": means,
        "by_seed": by_seed,
        "ndcg_at_10_requirement": 0.8 if k == 10 else None,
        "ndcg_requirement_passed": means["ndcg_at_k"] >= 0.8 if k == 10 else None,
    }


def markdown(report: dict) -> str:
    cfg, corpus, mean = (report[key] for key in ("configuration", "corpus", "mean"))
    k = cfg["k"]
    rows = [
        "# Бенчмарк обновлённой синтетики",
        "",
        f"Дата (UTC): {report['timestamp_utc']}",
        "",
        f"{corpus['queries']} вакансий-запросов, {corpus['resumes']} пар, "
        f"{len(corpus['roles'])} профессий, seed {', '.join(map(str, cfg['seeds']))}. "
        f"В каждой вакансии {cfg['resumes_per_vacancy']} кандидатов.",
        "",
        "Бинарная релевантность для Precision/Recall/MAP/MRR: "
        f"скрытая истинная релевантность ≥ {cfg['binary_relevance_threshold']}. "
        "NDCG использует непрерывную релевантность. Метки вычислены из скрытых "
        "навыков, критических требований, соответствия роли и опыта до написания текста.",
        "",
        f"- Precision@{k}: {mean['precision_at_k']:.3f}",
        f"- Recall@{k}: {mean['recall_at_k']:.3f}",
        f"- MAP: {mean['average_precision']:.3f}",
        f"- MRR: {mean['reciprocal_rank']:.3f}",
        f"- NDCG@{k}: {mean['ndcg_at_k']:.3f}",
        "",
        f"Дополнительно Spearman(Score, истинная релевантность): "
        f"{mean['spearman_score']:.3f}.",
        "",
        "| Seed | Precision | Recall | MAP | MRR | NDCG | Spearman |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for seed, scores in report["by_seed"].items():
        rows.append(
            f"| {seed} | {scores['precision_at_k']:.3f} | "
            f"{scores['recall_at_k']:.3f} | {scores['average_precision']:.3f} | "
            f"{scores['reciprocal_rank']:.3f} | {scores['ndcg_at_k']:.3f} | "
            f"{scores['spearman_score']:.3f} |"
        )
    rows += [
        "", "## Свойства набора", "",
        f"Медиана обязательных навыков вакансии: {corpus['vacancy_skill_count_median']}; "
        f"скрытых навыков резюме: {corpus['resume_latent_skill_count_median']}; "
        f"упомянутых в тексте: {corpus['resume_visible_skill_count_median']}.",
        f"Медианная длина текста вакансии: {corpus['vacancy_text_chars_median']} символов; "
        f"резюме: {corpus['resume_text_chars_median']} символов.",
        f"Положительных пар: {corpus['positive_pairs']} из {corpus['resumes']}; "
        f"вакансий без положительных кандидатов: {corpus['queries_without_positives']}.",
    ]
    if cfg["k"] == 10:
        rows += [
            "",
            "Порог ТЗ NDCG@10 ≥ 0,80: " +
            ("выполнен." if report["ndcg_requirement_passed"] else "не выполнен."),
        ]
    rows += [
        "",
        "Данные всё ещё синтетические: кандидаты формируются в контексте "
        "вакансии, тексты короче многих реальных PDF и не содержат всех "
        "особенностей кадровых документов. Показатели подтверждают работу "
        "алгоритма на этом контролируемом распределении, но не точность "
        "отбора на реальных кандидатах. Результат не использовался для "
        "подбора весов Score.",
        "",
    ]
    return "\n".join(rows)


def examples_markdown(seed: int = 42) -> str:
    """A few fake documents for human review of the wording and structure."""
    entry = generate_dataset(n_vacancies=6, n_resumes=20, seed=seed)[0]
    candidates = sorted(entry["candidates"], key=lambda item: item["true_relevance"])
    chosen = [candidates[0], candidates[len(candidates) // 2], candidates[-1]]
    lines = [
        "# Примеры синтетических документов",
        "",
        f"Seed {seed}. Имена и организации вымышлены; документы приведены "
        "для проверки правдоподобия, а не как реальные резюме.",
        "",
        "## Вакансия", "", entry["vacancy"]["text"], "",
    ]
    for title, candidate in zip(("Слабое", "Среднее", "Сильное"), chosen):
        years = candidate["experience_years"]
        years_word = "год" if years == 1 else "года" if years in (2, 3, 4) else "лет"
        lines += [
            f"## {title} резюме", "",
            f"Профессия: {candidate['role']}; стаж: {years} {years_word}; "
            f"истинная релевантность: {candidate['true_relevance']:.3f}; "
            f"скрытых навыков: {len(candidate['skills'])}; "
            f"упомянутых навыков: {len(candidate['text_skills'])}.",
            "", candidate["text"], "",
        ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 7, 99])
    parser.add_argument("--vacancies", type=int, default=12)
    parser.add_argument("--resumes", type=int, default=30)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=0.65)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    report = evaluate(tuple(args.seeds), args.vacancies, args.resumes,
                      args.k, args.threshold)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "synthetic_benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "synthetic_benchmark.md").write_text(
        markdown(report), encoding="utf-8"
    )
    (args.output_dir / "synthetic_examples.md").write_text(
        examples_markdown(args.seeds[0]), encoding="utf-8"
    )
    print(markdown(report))


if __name__ == "__main__":
    main()
