"""Интеграционный слой: достаёт вакансии/резюме из MongoDB, считает скоры, сохраняет.

Это мост «парсер -> скорер». Читает документы, которые записал Scrapy-паук
(или синтетический сидер), собирает тексты через ``db.builders``, запускает
гибридный скорер и сохраняет результаты в коллекцию ``hh_scores``.

Использование как библиотеки::

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
from typing import Dict, List, Optional, Set

from db import mongo
from db.builders import experience_years, resume_text, vacancy_text
from scorer.transport import rank as rank_candidates
from scorer.config import algorithm_manifest
from scorer.skills import extract_skills, normalize_skill_set


def score_vacancy(
    vacancy_id: str,
    resume_ids: Optional[List[str]] = None,
    limit_resumes: Optional[int] = None,
    save: bool = True,
    weights: Optional[Dict[str, float]] = None,
    min_score: Optional[float] = None,
    critical_skills: Optional[Set[str]] = None,
) -> Dict:
    """Считает скоры резюме одной вакансии и (опционально) сохраняет результаты.

    *resume_ids* ограничивает пул; иначе берётся вся коллекция ``hh_resumes``
    (с ограничением *limit_resumes*).
    *critical_skills* — необязательное множество must-have навыков.
    *min_score* — минимальный порог Score для флага ``passed_threshold``.
    """
    vac = mongo.get_vacancy(vacancy_id)
    if not vac:
        raise ValueError(f"vacancy {vacancy_id} not found")
    vacancy_id = str(vac['_id'])

    if resume_ids is not None:
        resume_ids = list(dict.fromkeys(resume_ids))
        resumes = [mongo.get_resume(rid) for rid in resume_ids]
        if any(r is None for r in resumes):
            raise ValueError("one or more resumes not found")
        resumes = list({str(r['_id']): r for r in resumes}.values())
    else:
        resumes = mongo.list_resumes(limit=limit_resumes)
    if not resumes:
        raise ValueError("no resumes to score")

    rids = [str(r["_id"]) for r in resumes]
    rtexts = [resume_text(r) for r in resumes]

    v_skills = (set(vac['skills']) if vac.get('skills')
                else extract_skills(vacancy_text(vac)))
    explicit_critical = critical_skills is not None
    if explicit_critical:
        normalized_critical = normalize_skill_set(critical_skills)
        if not normalized_critical <= normalize_skill_set(v_skills):
            raise ValueError("critical skills must belong to vacancy skills")
        critical_skills = normalized_critical
    critical_skills = (set(vac.get("critical_skills", []))
                       if critical_skills is None else critical_skills)
    r_skills_list = [set(r['skills']) if r.get('skills') else extract_skills(text)
                     for r, text in zip(resumes, rtexts)]

    ranked = rank_candidates(
        vacancy_text=vacancy_text(vac),
        candidate_texts=rtexts,
        candidate_ids=rids,
        weights=weights,
        min_score=min_score,
        critical_skills=critical_skills,
        vacancy_skills=v_skills,  # Передаем готовые навыки вакансии
        resume_skills_list=r_skills_list  # Передаем готовые навыки резюме
    )

    by_id = {str(r["_id"]): r for r in resumes}
    years_by_id = {str(r["_id"]): experience_years(r) for r in resumes}
    manifest = algorithm_manifest()
    for r in ranked:
        r["algorithm_fingerprint"] = manifest["fingerprint"]
        r["weights"] = weights or manifest["weights"]
        r["resume_id"] = r["candidate_id"]
        rdoc = by_id.get(r["candidate_id"], {})
        r["url"] = rdoc.get("url")
        r["position"] = rdoc.get("title")
        r["experience_years"] = years_by_id.get(r["candidate_id"])

    # Тай-брейк: при одинаковом Score выше ставит кандидата с большим опытом.
    # Само значение Score не меняется — оно остаётся абсолютной мерой навыков.
    # ``experience_years`` равный None уходит в конец.
    ranked.sort(
        key=lambda r: (-r["score"], r.get('experience_years') is None,
                       -(r.get("experience_years") or 0), r['resume_id']),
    )

    if save:
        if explicit_critical:
            mongo.update_critical_skills(vacancy_id, sorted(critical_skills))
            vac['critical_skills'] = sorted(critical_skills)
        mongo.save_scores(vacancy_id, ranked)
    return {"vacancy": vac, "results": ranked}


def _print_top(vacancy: Dict, results: List[Dict], top: int) -> None:
    """Печатает топ результатов в читаемом виде."""
    title = vacancy.get("title") or "(без названия)"
    print(f"\nВакансия: {title}  [{vacancy['_id']}]")
    print(f"Оценено резюме: {len(results)}")
    print(f"Топ-{min(top, len(results))}:\n")
    for i, r in enumerate(results[:top], 1):
        matched = ", ".join(r.get("matched_skills", [])) or "—"
        missing_crit = ", ".join(r.get("missing_critical", [])) or "—"
        years = r.get("experience_years")
        years_str = f"{years} лет" if years is not None else "—"
        print(
            f"  #{i:<2} Score {r['score']:>3}  "
            f"(kw {r['keyword_score']:.2f} | cos {r['cosine_sim']:.2f})  "
            f"опыт {years_str}  {r.get('position') or '(резюме)'}"
        )
        print(f"      навыки: {matched}")
        if r.get("missing_critical"):
            print(f"      критические пробелы: {missing_crit}")


def main(argv: Optional[List[str]] = None) -> int:
    """Точка входа CLI."""
    p = argparse.ArgumentParser(
        description="Считает скоры резюме вакансии через MongoDB.")
    p.add_argument("vacancy_id", nargs="?",
                   help="vacancy _id (по умолчанию — первая вакансия)")
    p.add_argument("--top", type=int, default=10,
                   help="сколько лучших результатов показать")
    p.add_argument("--limit-resumes", type=int, default=None,
                   help="ограничение размера пула")
    p.add_argument("--no-save", action="store_true", help="не сохранять скоры")
    p.add_argument("--json", action="store_true",
                   help="вывести результаты в JSON")
    p.add_argument("--critical-skills", nargs="*", default=None,
                   help="must-have навыки (через пробел)")

    args = p.parse_args(argv)

    vid = args.vacancy_id
    if not vid:
        vacs = mongo.list_vacancies(limit=1)
        if not vacs:
            print("No vacancies in DB. Run: python -m db.seed", file=sys.stderr)
            return 1
        vid = vacs[0]["_id"]

    out = score_vacancy(
        vid,
        limit_resumes=args.limit_resumes,
        save=not args.no_save,
        critical_skills=set(
            args.critical_skills) if args.critical_skills else None,
    )
    if args.json:
        import json
        print(json.dumps(out["results"], ensure_ascii=False, indent=2))
    else:
        _print_top(out["vacancy"], out["results"], args.top)
        if not args.no_save:
            print(
                f"\nResults saved to collection 'hh_scores' "
                f"in db '{mongo.MONGO_DB}' (vacancy {vid})."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
