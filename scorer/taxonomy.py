from __future__ import annotations

import json
from pathlib import Path
from typing import Set
import pandas as pd


def get_project_root() -> Path:
    # Ищет корень проекта (где лежат data, scripts, api)
    current = Path(__file__).resolve().parent
    for parent in [current, current.parent, current.parent.parent]:
        if (parent / "data").exists() or (parent / "scripts").exists():
            return parent
    return current.parent


def load_unified_taxonomy() -> list[str]:
    """
    Загружает единый словарь всех навыков из разметки коллеги и датасетов.
    Новые размеченные колонки подхватываются автоматически.
    """
    root = get_project_root()
    skills: Set[str] = set()

    # 1. Загрузка из ground truth файлов разметки (CSV от коллеги)
    gt_paths = [
        root / "scripts" / "exel" / "ground_truth_vacancies.csv",
        root / "scripts" / "exel" / "ground_truth_resumes.csv",
        root / "data" / "ground_truth_vacancies.csv",
        root / "data" / "ground_truth_resumes.csv",
    ]

    for p in gt_paths:
        if p.exists():
            try:
                df = pd.read_csv(p, nrows=1)
                # Все колонки, кроме id и служебных полей — это навыки
                cols = [c.strip() for c in df.columns if c.lower() not in {"id", "url", "title", "text"}]
                skills.update(cols)
            except Exception:
                pass

    # 2. Загрузка из датасетов JSON
    json_paths = [
        root / "data" / "superjob_dataset.json",
        root / "data" / "dataset_resume.json",
    ]
    for jp in json_paths:
        if jp.exists():
            try:
                with open(jp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        for s in item.get("expected_skills", []):
                            if isinstance(s, str) and s.strip():
                                skills.add(s.strip())
            except Exception:
                pass

    # 3. Базовая таксономия скорера (на случай отсутствия файлов)
    try:
        from scorer.skills import _indices
        lemma_idx, raw_idx = _indices()
        for v in lemma_idx.values():
            skills.update(v)
        for v in raw_idx.values():
            skills.add(v)
    except Exception:
        pass

    return sorted(list(skills))