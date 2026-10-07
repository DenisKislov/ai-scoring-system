#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Собирает data/skills_vocab.json из источника.

Режимы:
    # 1) Из GT-колонок (для тестов/сравнения; не для прода!)
    python scripts/build_skills_vocab.py --from-gt \
        --resumes-gt data/ground_truth_resumes.csv \
        --vacancies-gt data/ground_truth_vacancies.csv

    # 2) Из внешнего списка (продакшен)
    python scripts/build_skills_vocab.py --from-list data/skills_source.txt
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from typing import Dict, List, Set

import pandas as pd

try:
    import pymorphy3
    _MORPH = pymorphy3.MorphAnalyzer()
except ImportError:
    _MORPH = None


# Общие алиасы (совпадает с тем, что у тебя было в build_vocab.py)
ALIASES: Dict[str, List[str]] = {
    "javascript": ["js"],
    "typescript": ["ts"],
    "postgresql": ["postgres", "postgre", "psql"],
    "kubernetes": ["k8s"],
    "cpp": ["c++"],
    "csharp": ["c#", "c sharp"],
    "1с": ["1c"],
    "machine learning": ["ml", "машинное обучение"],
    "nlp": ["natural language processing"],
    "искусственный интеллект": ["ai", "ии"],
    "базы данных": ["бд", "database"],
    "ооп": ["oop"],
    "ci/cd": ["cicd", "ci cd", "ci-cd"],
    "node.js": ["nodejs", "node js"],
    ".net": ["dotnet", ".net core", "net core"],
    "asp.net": ["asp net"],
    "rest api": ["rest", "restful"],
    "go": ["golang"],
}

_TOKEN_RE = re.compile(r"[А-Яа-яЁёA-Za-z]+")


def _lemma_ru_only(text: str) -> str:
    if _MORPH is None:
        return text

    def _repl(m):
        w = m.group(0)
        if not re.search(r"[А-Яа-яЁё]", w):
            return w.lower()
        if len(w) < 2 or any(c.isdigit() for c in w):
            return w.lower()
        return _MORPH.parse(w.lower())[0].normal_form
    return _TOKEN_RE.sub(_repl, text)


def _norm(s: str, lemmatize: bool) -> str:
    s = s.strip().lower().replace("ё", "е")
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    return _lemma_ru_only(s) if lemmatize else s


def build_from_gt(resumes_csv: str, vacancies_csv: str, lemmatize: bool) -> Dict[str, List[str]]:
    cols: Set[str] = set()
    for p in (resumes_csv, vacancies_csv):
        head = pd.read_csv(p, index_col=0, nrows=0)
        cols.update((c or "").strip() for c in head.columns if (c or "").strip())
    vocab: Dict[str, List[str]] = {}
    for c in sorted(cols):
        key = _norm(c, lemmatize)
        if not key or key in vocab:
            continue
        variants = [_norm(c, lemmatize)]
        for a in ALIASES.get(key, []):
            variants.append(_norm(a, lemmatize))
        vocab[key] = [v for v in dict.fromkeys(variants) if len(v) >= 2]
    return {k: v for k, v in vocab.items() if v}


def build_from_list(path: str, lemmatize: bool) -> Dict[str, List[str]]:
    """Каждая строка файла = один навык. Комментарии через #."""
    vocab: Dict[str, List[str]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key = _norm(line, lemmatize)
            if not key or key in vocab or len(key) < 2:
                continue
            variants = [key] + [_norm(a, lemmatize) for a in ALIASES.get(key, [])]
            vocab[key] = [v for v in dict.fromkeys(variants) if len(v) >= 2]
    return vocab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-gt", action="store_true")
    ap.add_argument("--from-list", default=None,
                    help="файл с навыками построчно")
    ap.add_argument("--resumes-gt", default="data/ground_truth_resumes.csv")
    ap.add_argument("--vacancies-gt", default="data/ground_truth_vacancies.csv")
    ap.add_argument("--no-lemmatize", action="store_true",
                    help="не лемматизировать (рекомендуется)")
    ap.add_argument("--out", default="data/skills_vocab.json")
    args = ap.parse_args()

    lemmatize = not args.no_lemmatize

    if args.from_gt:
        vocab = build_from_gt(args.resumes_gt, args.vacancies_gt, lemmatize)
        src = f"GT: {args.resumes_gt} + {args.vacancies_gt}"
    elif args.from_list:
        vocab = build_from_list(args.from_list, lemmatize)
        src = f"list: {args.from_list}"
    else:
        ap.error("Укажи --from-gt или --from-list PATH")

    doc = {
        "version": "1.0",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "config": {"lemmatized": lemmatize, "source": src},
        "skills": vocab,
    }
    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    print(f"✓ Словарь сохранён в {args.out}")
    print(f"   навыков: {len(vocab)}")
    print(f"   паттернов: {sum(len(v) for v in vocab.values())}")
    print(f"   лемматизация: {'ON' if lemmatize else 'OFF'}")


if __name__ == "__main__":
    main()