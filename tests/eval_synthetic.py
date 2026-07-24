"""Evaluation on synthetic data: does the scorer rank candidates correctly?

Generates a labelled dataset (known true relevance per resume), runs the
scorer, and reports nDCG@k / precision@k / Spearman per vacancy plus a
component breakdown (keyword vs. cosine). This is the quantitative evidence
for "Показ 3" — a single number that says the algorithm ranks sensibly.

Run: ``python tests/eval_synthetic.py``.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from data.synthetic import generate_dataset  # noqa: E402
from scorer import rank_candidates  # noqa: E402
from scorer.metrics import ndcg, precision_at_k, spearman  # noqa: E402

N_VACANCIES = 6
N_RESUMES = 20
SEED = 42
QUALITY_BAR = 0.80  # nDCG@10 we expect the scorer to clear


def evaluate():
    dataset = generate_dataset(n_vacancies=N_VACANCIES, n_resumes=N_RESUMES, seed=SEED)

    headers = ["vacancy", "role", "nDCG@10", "nDCG", "P@5", "spearman"]
    print(f"{headers[0]:<22}{headers[1]:<18}{headers[2]:>9}{headers[3]:>9}{headers[4]:>8}{headers[5]:>10}")
    print("-" * 76)

    rows = []
    # Pools for component analysis (predicted sub-score vs. true relevance).
    all_keyword, all_cosine, all_score, all_true = [], [], [], []

    for i, entry in enumerate(dataset):
        vac = entry["vacancy"]
        candidates = entry["candidates"]
        texts = [c["text"] for c in candidates]
        true_rels = [c["true_relevance"] for c in candidates]

        ranked = rank_candidates(vac["text"], texts)

        # True relevance in the predicted order.
        pred_rels = [true_rels[r["candidate_id"]] for r in ranked]

        # Predicted sub-scores in the ORIGINAL item order, aligned with true_rels.
        pred_score = np.zeros(len(candidates))
        pred_kw = np.zeros(len(candidates))
        pred_cos = np.zeros(len(candidates))
        for r in ranked:
            cid = r["candidate_id"]
            pred_score[cid] = r["raw_score"]
            pred_kw[cid] = r["keyword_score"]
            pred_cos[cid] = r["cosine_sim"]

        row = {
            "ndcg10": ndcg(pred_rels, k=10),
            "ndcg": ndcg(pred_rels),
            "p5": precision_at_k(pred_rels, k=5),
            "spearman": spearman(pred_score, true_rels),
        }
        rows.append(row)
        title = f"V{i+1}"
        print(
            f"{title:<22}{vac['role']:<18}"
            f"{row['ndcg10']:>9.3f}{row['ndcg']:>9.3f}{row['p5']:>8.3f}{row['spearman']:>10.3f}"
        )

        all_keyword.extend(pred_kw)
        all_cosine.extend(pred_cos)
        all_score.extend(pred_score)
        all_true.extend(true_rels)

    print("-" * 76)
    mean_ndcg10 = float(np.mean([r["ndcg10"] for r in rows]))
    print(
        f"{'MEAN':<40}{mean_ndcg10:>9.3f}{np.mean([r['ndcg'] for r in rows]):>9.3f}"
        f"{np.mean([r['p5'] for r in rows]):>8.3f}{np.mean([r['spearman'] for r in rows]):>10.3f}"
    )

    print("\nComponent correlation with true relevance (Spearman):")
    print(f"  keyword_score : {spearman(all_keyword, all_true):+.3f}")
    print(f"  cosine_sim    : {spearman(all_cosine, all_true):+.3f}")
    print(f"  combined      : {spearman(all_score, all_true):+.3f}")

    print(f"\nMean nDCG@10 = {mean_ndcg10:.3f}  (quality bar = {QUALITY_BAR})")
    ok = mean_ndcg10 >= QUALITY_BAR
    print("RESULT: PASS — scorer ranks candidates correctly." if ok else "RESULT: FAIL — below quality bar.")
    assert ok, f"nDCG@10 {mean_ndcg10:.3f} below bar {QUALITY_BAR}"
    return mean_ndcg10


if __name__ == "__main__":
    evaluate()
