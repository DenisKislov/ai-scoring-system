"""Fetch and aggregate skills from hh.ru vacancies.

Give it a **vacancy URL** (one position) or a **search/listing URL**
(``/vacancies/...``) and it reports which skills the scorer ontology detects,
and — for a listing — how often each appears across the first N vacancies.

Skills come from the free-text *description* (``data-qa="vacancy-description"``),
because hh.ru's tagged ``key_skills`` are frequently empty and the public API
returns 403 without a token.

CLI::

    python -m tools.vacancy_skills <URL> [--max N] [--top K]

Examples::

    python -m tools.vacancy_skills https://hh.ru/vacancies/python-razrabotchik --max 12
    python -m tools.vacancy_skills https://novosibirsk.hh.ru/vacancy/132709791
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter
from typing import Dict, List

import requests

from scorer.skills import extract_skills

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.6",
}


def _fetch(url: str, timeout: int = 20) -> str:
    return requests.get(url, headers=_UA, timeout=timeout).text


def _clean(chunk: str) -> str:
    chunk = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", chunk, flags=re.S | re.I)
    chunk = re.sub(r"<[^>]+>", " ", chunk)
    chunk = re.sub(r"&[a-z#0-9]+;", " ", chunk)
    return re.sub(r"\s+", " ", chunk).strip()


def _description_text(html: str) -> str:
    """Text of the vacancy description block (where the real skills live)."""
    i = html.find('data-qa="vacancy-description"')
    if i < 0:
        return ""
    return _clean(html[i:i + 15000])


def _vacancy_name(html: str) -> str:
    m = re.search(r'<h1[^>]*data-qa="vacancy-title"[^>]*>(.*?)</h1>', html, re.S)
    return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""


def vacancy_skills(url: str) -> Dict:
    html = _fetch(url)
    return {
        "url": url,
        "name": _vacancy_name(html),
        "skills": sorted(extract_skills(_description_text(html))),
    }


def search_skills(search_url: str, max_vacancies: int = 10, delay: float = 0.8) -> Dict:
    """Crawl the first *max_vacancies* vacancies linked from a search page."""
    html = _fetch(search_url)
    ids = list(dict.fromkeys(re.findall(r"/vacancy/(\d+)", html)))  # unique, ordered
    ids = ids[:max_vacancies]

    per_vacancy: List[Dict] = []
    counter: Counter = Counter()
    for vid in ids:
        url = f"https://hh.ru/vacancy/{vid}"
        try:
            vhtml = _fetch(url)
            name, skills = _vacancy_name(vhtml), sorted(extract_skills(_description_text(vhtml)))
        except Exception as exc:  # noqa: BLE001
            name, skills = f"(fetch error: {exc})", []
        per_vacancy.append({"id": vid, "url": url, "name": name, "skills": skills})
        counter.update(skills)
        time.sleep(delay)
    return {"search_url": search_url, "n": len(ids), "per_vacancy": per_vacancy, "counter": counter}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("url", help="hh.ru vacancy URL or search/listing URL")
    p.add_argument("--max", type=int, default=10, help="max vacancies to crawl (listing mode)")
    p.add_argument("--top", type=int, default=30, help="how many top skills to print")
    args = p.parse_args(argv)

    is_listing = "/vacancies/" in args.url or "/search/vacancy" in args.url
    if is_listing:
        res = search_skills(args.url, args.max)
        print(f"Crawled {res['n']} vacancies from {args.url}\n")
        for v in res["per_vacancy"]:
            print(f"  · {v['name'][:55]:<55} | {', '.join(v['skills']) or '—'}")
        print(f"\nAggregated skill frequency (top {args.top}):")
        for skill, cnt in res["counter"].most_common(args.top):
            print(f"  {cnt:>3}  {skill}")
    else:
        v = vacancy_skills(args.url)
        print(f"{v['name']}\n  skills: {', '.join(v['skills']) or '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
