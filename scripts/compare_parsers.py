#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сравнительный бенчмарк парсеров на реальных PDF вакансий и резюме."""
import os
import re
import sys
import time
from pathlib import Path

# Добавляем корень проекта в sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import pandas as pd
import pypdf

# 1. Решение куратора (api/nlp_parser.py)
from api.nlp_parser import extract_smart_skills as curator_extract

# 2. Наш парсер (scorer/skill_extractor.py)
from scorer.skill_extractor import SkillExtractor

VACANCIES_GT = BASE_DIR / "data" / "ground_truth_vacancies.csv"
VACANCIES_PDF = BASE_DIR / "data" / "vacancies"

RESUMES_GT = BASE_DIR / "data" / "ground_truth_resumes.csv"
RESUMES_PDF = BASE_DIR / "data" / "resumes"


def extract_id(text: str, filename: str, valid_ids: set) -> int:
    for m in re.findall(r"\b\d{7,9}\b", filename) + re.findall(r"\b\d{7,9}\b", text[:600]):
        val = int(m)
        if val in valid_ids:
            return val
    return 0


def run_benchmark(pdf_dir: Path, gt_path: Path, dataset_name: str):
    if not gt_path.exists() or not pdf_dir.exists():
        print(f"[-] Пропуск {dataset_name}: файлы не найдены по путям {gt_path} или {pdf_dir}")
        return

    df_gt = pd.read_csv(gt_path)
    all_skills = [c.strip() for c in df_gt.columns if c.lower() not in {"id", "url", "title", "text"}]
    valid_ids = set(df_gt["id"].values)

    our_extractor = SkillExtractor(taxonomy=all_skills)
    pdf_files = sorted(list(pdf_dir.glob("*.pdf")))

    stats = {
        "our": {"tp": 0, "fp": 0, "fn": 0, "time": 0.0},
        "curator": {"tp": 0, "fp": 0, "fn": 0, "time": 0.0},
    }

    processed = 0

    for pdf_path in pdf_files:
        try:
            reader = pypdf.PdfReader(str(pdf_path))
            raw = "\n".join([p.extract_text() or "" for p in reader.pages])
        except Exception:
            continue

        doc_id = extract_id(raw, pdf_path.name, valid_ids)
        if not doc_id:
            continue

        gt_row = df_gt[df_gt["id"] == doc_id]
        if gt_row.empty:
            continue

        true_skills = {c.lower() for c in all_skills if gt_row[c].values[0] == 1}
        processed += 1

        # Прогон нашего парсера
        t0 = time.perf_counter()
        our_pred = {s.lower() for s in our_extractor.extract(raw)}
        stats["our"]["time"] += time.perf_counter() - t0

        stats["our"]["tp"] += len(true_skills & our_pred)
        stats["our"]["fp"] += len(our_pred - true_skills)
        stats["our"]["fn"] += len(true_skills - our_pred)

        # Прогон парсера куратора
        t0 = time.perf_counter()
        curator_pred = {s.lower() for s in curator_extract(raw)}
        stats["curator"]["time"] += time.perf_counter() - t0

        stats["curator"]["tp"] += len(true_skills & curator_pred)
        stats["curator"]["fp"] += len(curator_pred - true_skills)
        stats["curator"]["fn"] += len(true_skills - curator_pred)

    def calc_metrics(m):
        tp, fp, fn = m["tp"], m["fp"], m["fn"]
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        return p, r, f1, m["time"]

    p_our, r_our, f1_our, t_our = calc_metrics(stats["our"])
    p_cur, r_cur, f1_cur, t_cur = calc_metrics(stats["curator"])

    print(f"\n{'='*75}")
    print(f"ДАТАСЕТ: {dataset_name} (проанализировано {processed} документов)")
    print(f"{'='*75}")
    print(f"{'Парсер':<24} | {'Precision':<10} | {'Recall':<10} | {'F1-Score':<10} | {'Время (сек)':<10}")
    print(f"{'-'*75}")
    print(f"{'Наш (SkillExtractor)':<24} | {p_our:<10.2%} | {r_our:<10.2%} | {f1_our:<10.2%} | {t_our:<10.2f}")
    print(f"{'Куратора (NLP-Vocab)':<24} | {p_cur:<10.2%} | {r_cur:<10.2%} | {f1_cur:<10.2%} | {t_cur:<10.2f}")
    print(f"{'='*75}")


if __name__ == "__main__":
    run_benchmark(VACANCIES_PDF, VACANCIES_GT, "РЕАЛЬНЫЕ ВАКАНСИИ")
    run_benchmark(RESUMES_PDF, RESUMES_GT, "РЕАЛЬНЫЕ РЕЗЮМЕ")
