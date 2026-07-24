"""Integration glue: pull vacancies/resumes from MongoDB, score, persist.

This is the "parser -> scorer" bridge. It reads documents the Scrapy spider
(or the synthetic seeder) wrote, builds text with ``db.builders``, runs the
hybrid scorer, and upserts results into ``hh_scores``.

Library use::

    from scorer.service import score_vacancy
    out = score_vacancy(vacancy_id, limit_resumes=100)
    for r in out["results"]:
        ...

CLI::

    python -m scorer.service [VACANCY_ID] [--top N] [--limit-resumes N] [--no-save]
"""
from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Optional

from db import mongo
from db.builders import experience_years, resume_text, vacancy_text
from scorer import rank_candidates


def score_vacancy(
    vacancy_id: str,
    resume_ids: Optional[List[str]] = None,
    limit_resumes: Optional[int] = None,
    save: bool = True,
    weights: Optional[Dict[str, float]] = None,
) -> Dict:
    """Score the resumes of a vacancy and (optionally) persist results.

    *resume_ids* restricts the pool; otherwise the whole ``hh_resumes``
    collection is used (bounded by *limit_resumes*).
    """
    vac = mongo.get_vacancy(vacancy_id)
    if not vac:
        raise ValueError(f"vacancy {vacancy_id} not found")

    if resume_ids:
        resumes = [r for r in (mongo.get_resume(rid) for rid in resume_ids) if r]
    else:
        resumes = mongo.list_resumes(limit=limit_resumes)
    if not resumes:
        raise ValueError("no resumes to score")

    rids = [str(r["_id"]) for r in resumes]
    rtexts = [resume_text(r) for r in resumes]
    ranked = rank_candidates(vacancy_text(vac), rtexts, candidate_ids=rids, weights=weights)

    by_id = {str(r["_id"]): r for r in resumes}
    years_by_id = {str(r["_id"]): experience_years(r) for r in resumes}
    for r in ranked:
        rdoc = by_id.get(r["candidate_id"], {})
        r["url"] = rdoc.get("url")
        r["position"] = rdoc.get("title")
        r["experience_years"] = years_by_id.get(r["candidate_id"])

    # Tie-break: among candidates with the same score, the one with more years
    # of experience ranks higher. The score value itself is NOT changed — it
    # stays an absolute skill/text measure (architecture decision); this only
    # orders equal-score rows. ``experience_years`` of None sorts last.
    ranked.sort(
        key=lambda r: (r["score"], r.get("experience_years") or 0),
        reverse=True,
    )

    if save:
        mongo.save_scores(vacancy_id, ranked)
    return {"vacancy": vac, "results": ranked}


def _print_top(vacancy: Dict, results: List[Dict], top: int) -> None:
    title = vacancy.get("title") or "(без названия)"
    print(f"\nВакансия: {title}  [{vacancy['_id']}]")
    print(f"Оценено резюме: {len(results)}")
    print(f"Топ-{min(top, len(results))}:\n")
    for i, r in enumerate(results[:top], 1):
        matched = ", ".join(r.get("matched_skills", [])) or "—"
        years = r.get("experience_years")
        years_str = f"{years} лет" if years is not None else "—"
        print(
            f"  #{i:<2} Score {r['score']:>3}  (kw {r['keyword_score']:.2f} | cos {r['cosine_sim']:.2f})  "
            f"опыт {years_str}  {r.get('position') or '(резюме)'}"
        )
        print(f"      навыки: {matched}")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Score a vacancy's resumes via MongoDB.")
    p.add_argument("vacancy_id", nargs="?", help="vacancy _id (default: first vacancy)")
    p.add_argument("--top", type=int, default=10, help="how many top results to print")
    p.add_argument("--limit-resumes", type=int, default=None, help="cap pool size")
    p.add_argument("--no-save", action="store_true", help="don't persist scores")
    p.add_argument("--json", action="store_true", help="emit results as JSON")
    args = p.parse_args(argv)

    vid = args.vacancy_id
    if not vid:
        vacs = mongo.list_vacancies(limit=1)
        if not vacs:
            print("No vacancies in DB. Run: python -m db.seed", file=sys.stderr)
            return 1
        vid = vacs[0]["_id"]

    out = score_vacancy(vid, limit_resumes=args.limit_resumes, save=not args.no_save)
    if args.json:
        import json
        print(json.dumps(out["results"], ensure_ascii=False, indent=2))
    else:
        _print_top(out["vacancy"], out["results"], args.top)
        if not args.no_save:
            print(f"\nResults saved to collection 'hh_scores' in db '{mongo.MONGO_DB}' (vacancy {vid}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
