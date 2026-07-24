"""End-to-end integration demo: DB -> scorer -> DB.

Two parts:

1. **Quality check** on a synthetic vacancy whose resumes carry ground-truth
   relevance — proves the bridge ranks correctly (Spearman vs. truth).
2. **Real hh.ru vacancy** scored against the pool — proves the scorer works on
   genuine data collected by the parser (no ground truth, just show the ranking).

If there are no resumes yet (the parser can't fetch hh.ru resumes without an
employer login), synthetic vacancies+resumes are seeded — the 19 real
vacancies already in the DB are preserved.

Run: ``python tests/integration_demo.py``.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import mongo  # noqa: E402
from db.seed import seed  # noqa: E402
from scorer.metrics import spearman  # noqa: E402
from scorer.service import score_vacancy  # noqa: E402

QUALITY_BAR = 0.80


def _print_top(results, n, title):
    print(f"\n{title}\n")
    for r in results[:n]:
        matched = ", ".join(r.get("matched_skills", [])) or "—"
        print(f"  Score {r['score']:>3}  {r.get('position') or '(резюме)':<26} matched: {matched}")


def part_quality():
    """Score a synthetic vacancy, verify ranking quality vs. ground truth."""
    syn_vacs = [v for v in mongo.list_vacancies() if v.get("_synthetic")]
    resumes = mongo.list_resumes()
    vac = next((v for v in syn_vacs if any(r.get("_target_vacancy_url") == v["url"] for r in resumes)), None)
    assert vac, "no synthetic vacancy with target resumes — seed first"

    vid = vac["_id"]
    out = score_vacancy(vid)
    results = out["results"]

    saved = mongo.get_scores(vid)
    assert len(saved) == len(results), f"persist mismatch: {len(saved)} vs {len(results)}"

    truth = {
        str(r["_id"]): r.get("_true_relevance")
        for r in resumes
        if r.get("_target_vacancy_url") == vac["url"] and r.get("_true_relevance") is not None
    }
    by_id = {r["candidate_id"]: r["raw_score"] for r in results}
    preds = [(by_id[rid], tru) for rid, tru in truth.items() if rid in by_id]
    rho = spearman([p[0] for p in preds], [p[1] for p in preds])

    _print_top(results, 3, f"PART 1 — synthetic vacancy '{vac.get('title')}' (ground-truth pool)")
    print(f"\n  [PERSIST] OK — {len(saved)} scores saved to hh_scores.")
    print(f"  [QUALITY] Spearman(score, ground-truth) = {rho:+.3f}")
    assert rho >= QUALITY_BAR, f"quality {rho:.3f} below bar {QUALITY_BAR}"
    print(f"  [QUALITY] OK — above bar {QUALITY_BAR}.")


def part_real():
    """Score a real hh.ru vacancy (collected by the parser) against the pool."""
    real_vacs = [v for v in mongo.list_vacancies() if not v.get("_synthetic") and (v.get("skills"))]
    if not real_vacs:
        print("\nPART 2 — no real vacancies with skills, skipping.")
        return
    rv = real_vacs[0]
    out = score_vacancy(rv["_id"], save=False)  # don't pollute scores with cross-vacancy noise
    n_skills = len(rv.get("skills") or [])
    _print_top(
        out["results"], 5,
        f"PART 2 — REAL hh.ru vacancy '{rv.get('title')}' ({n_skills} tagged skills) vs pool",
    )
    print("  (no ground truth for real data — ranking shown for inspection)")


def main() -> int:
    if mongo.count_resumes() == 0:
        print(f"Resumes empty -> seeding synthetic pool (preserving {mongo.count_vacancies()} real vacancies)...")
        seed(n_vacancies=5, n_resumes=15, seed=42, clear=False)

    print(f"DB: {mongo.count_vacancies()} vacancies, {mongo.count_resumes()} resumes.")
    part_quality()
    part_real()
    print("\nINTEGRATION DEMO PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
