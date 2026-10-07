import os
import re
from pathlib import Path
from typing import Set, List, Tuple
import pandas as pd
import pypdf

BASE_DIR = Path(__file__).resolve().parent
VACANCIES_GT_PATH = BASE_DIR.parent / "data" / "ground_truth_vacancies.csv"
PDF_DIR = BASE_DIR.parent / "data" / "vacancies"

df_gt = pd.read_csv(VACANCIES_GT_PATH)
ALL_SKILLS = [c for c in df_gt.columns if c != "id"]

BLACKLIST = {
    "разработка", "обучение", "внедрение", "аналитика", "позиции",
    "требования", "обязанности", "условия", "https", "сети",
    "документация", "медицина", "архитектура", "протоколы", "компас",
    "кросс-функциональная команда", "информационные технологии", "ТЗ"
}

STRICT_UPPERCASE = {"ПК", "ИИ", "AI", "QA"}

INLINE_ALIASES = {
    "PostgreSQL": r"(?:postgresql|postgres|psql|постгрес)",
    "Postgres": r"(?:postgresql|postgres|psql|постгрес)",
    "JavaScript": r"(?:javascript|js(?![a-z])|яваскрипт)",
    "TypeScript": r"(?:typescript|ts(?![a-z])|тайпскрипт)",
    "ClickHouse": r"(?:clickhouse|кликхаус)",
    "PySpark": r"(?:pyspark|py-spark)",
    "HTML": r"(?:html|html5)",
    "CSS": r"(?:css|css3)",
    "iOS": r"(?:ios|айос)",
    "PowerShell": r"(?:powershell|power\s*shell|ps1)",
    "1С": r"1\s*[сc]",
    "1С: КА": r"1\s*[сc]\s*[:/]?\s*ка\b",
    "1С: ERP": r"1\s*[сc]\s*[:/]?\s*erp\b",
    "1С: УХ": r"1\s*[сc]\s*[:/]?\s*ух\b",
    "1С: Бухгалтерия": r"1\s*[сc]\s*[:/]?\s*бухгалтер[а-яё]*",
    "ЛВС": r"(?:лвс|локальн\w+\s+вычислительн\w+\s+сет\w*)",
    "ЛКС": r"(?:лкс|локальн\w+\s+кабельн\w+\s+сет\w*)"
}


def build_skill_pattern(skill: str) -> Tuple[str, re.Pattern]:
    if skill in INLINE_ALIASES:
        raw_pat = INLINE_ALIASES[skill]
        return skill, re.compile(rf"(?<![a-zа-яё0-9]){raw_pat}(?![a-zа-яё0-9])", re.IGNORECASE)

    if skill in STRICT_UPPERCASE:
        return skill, re.compile(rf"(?<![a-zA-Zа-яА-ЯёЁ0-9]){re.escape(skill)}(?![a-zA-Zа-яА-ЯёЁ0-9])")

    if re.match(r"^[a-zA-Z0-9\+\#\.\-_]+$", skill) and len(skill) <= 4:
        return skill, re.compile(rf"\b{re.escape(skill)}\b", re.IGNORECASE)

    words = skill.split()
    if len(words) == 1:
        if re.match(r"^[а-яёА-ЯЁ\-]+$", skill) and len(skill) >= 5:
            stem = skill[:-2] if len(skill) >= 6 else skill[:-1]
            return skill, re.compile(rf"(?<![a-zа-яё0-9]){re.escape(stem)}[а-яё]{{0,3}}(?![a-zа-яё0-9])", re.IGNORECASE)
        return skill, re.compile(rf"(?<![a-zа-яё0-9]){re.escape(skill)}(?![a-zа-яё0-9])", re.IGNORECASE)

    parts = []
    for w in words:
        if re.match(r"^[а-яёА-ЯЁ\-]+$", w) and len(w) >= 5:
            stem = w[:-2] if len(w) >= 6 else w[:-1]
            parts.append(rf"{re.escape(stem)}[а-яё]{{0,3}}")
        else:
            parts.append(re.escape(w))

    pattern_str = r"\s*[:/]?\s*".join(parts)
    return skill, re.compile(rf"(?<![a-zа-яё0-9]){pattern_str}(?![a-zа-яё0-9])", re.IGNORECASE)


COMPILED_PATTERNS = [
    build_skill_pattern(s)
    for s in sorted(ALL_SKILLS, key=len, reverse=True)
    if s.lower() not in BLACKLIST and s not in BLACKLIST
]


def extract_target_sections(text: str) -> str:
    """Извлекает ТОЛЬКО секции 'Требования' и 'Профессиональные навыки'."""
    text = re.sub(r"([a-zа-яё0-9])([A-ZА-ЯЁ])", r"\1 \2", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\S+\.html\S*", " ", text, flags=re.I)
    text = re.sub(r"\b(forceprinting|printing|vacancy|resume)=\w*\b", " ", text, flags=re.I)
    text = re.sub(r"\bsuper\s*job\b|\bheadhunter\b|\bhh\.ru\b", " ", text, flags=re.I)

    # Ищем блок требований
    req_match = re.search(r"(?i)\bтребования\b[\s\S]*?(?=(?:\b(?:условия|мы\s+предлагаем|контакты|профессиональные\s+навыки)\b|\Z))", text)
    # Ищем блок навыков
    skills_match = re.search(r"(?i)\b(?:профессиональные\s+навыки|ключевые\s+навыки)\b[\s\S]*", text)

    target_text = ""
    if req_match:
        target_text += " " + req_match.group(0)
    if skills_match:
        target_text += " " + skills_match.group(0)

    # Если структура нестандартная (нет явных заголовков), берем весь текст без блока условий
    if not target_text.strip():
        target_text = re.sub(
            r"(?i)\b(?:условия(?:\s+работы)?|мы\s+предлагаем|социальный\s+пакет|компенсационный\s+пакет)\b[\s\S]*",
            " ",
            text
        )

    return target_text


def extract_id_from_pdf(text: str, filename: str) -> int:
    for m in re.findall(r"\b\d{7,9}\b", filename) + re.findall(r"\b\d{7,9}\b", text[:600]):
        val = int(m)
        if val in df_gt["id"].values:
            return val
    for m in re.findall(r"\b\d{7,9}\b", text):
        val = int(m)
        if val in df_gt["id"].values:
            return val
    return 0


def parse_skills_scoped(raw_text: str) -> Set[str]:
    scoped_text = extract_target_sections(raw_text)
    matched_skills = set()
    occupied_spans = []

    for skill_name, pattern in COMPILED_PATTERNS:
        for match in pattern.finditer(scoped_text):
            start, end = match.span()
            if not any(s <= start and end <= e for s, e in occupied_spans):
                matched_skills.add(skill_name)
                occupied_spans.append((start, end))

    return matched_skills


def evaluate_dataset():
    pdf_files = sorted(list(PDF_DIR.glob("*.pdf")))
    total_tp, total_fp, total_fn = 0, 0, 0
    processed_count = 0

    for pdf_path in pdf_files:
        try:
            reader = pypdf.PdfReader(str(pdf_path))
            raw_text = "\n".join([page.extract_text() or "" for page in reader.pages])
        except Exception:
            continue

        doc_id = extract_id_from_pdf(raw_text, pdf_path.name)
        if not doc_id:
            continue

        gt_row = df_gt[df_gt["id"] == doc_id]
        if gt_row.empty:
            continue

        true_skills = set(col for col in ALL_SKILLS if gt_row[col].values[0] == 1)
        predicted_skills = parse_skills_scoped(raw_text)

        true_norm = {s.lower(): s for s in true_skills}
        pred_norm = {s.lower(): s for s in predicted_skills}

        tp_keys = set(true_norm.keys()) & set(pred_norm.keys())
        fp_keys = set(pred_norm.keys()) - set(true_norm.keys())
        fn_keys = set(true_norm.keys()) - set(pred_norm.keys())

        total_tp += len(tp_keys)
        total_fp += len(fp_keys)
        total_fn += len(fn_keys)
        processed_count += 1

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    print("=" * 55)
    print(f"ИТОГОВЫЕ МЕТРИКИ (Scoped Section Parser | {processed_count} вакансий):")
    print(f"Precision (Точность): {precision:.2%}")
    print(f"Recall (Полнота):    {recall:.2%}")
    print(f"F1-Score:            {f1:.2%}")
    print("=" * 55)


if __name__ == "__main__":
    evaluate_dataset()
