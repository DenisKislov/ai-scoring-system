import os
import re
from pathlib import Path
from collections import Counter
import pandas as pd
import pypdf

BASE_DIR = Path(__file__).resolve().parent
EXEL_DIR = BASE_DIR / "exel"
VACANCIES_GT_PATH = EXEL_DIR / "ground_truth_vacancies.csv"
PDF_DIR = EXEL_DIR / "Вакансии в pdf"

df_gt = pd.read_csv(VACANCIES_GT_PATH)
ALL_SKILLS = [c for c in df_gt.columns if c != "id"]

BLACKLIST = {
    "разработка", "обучение", "внедрение", "аналитика", "позиции",
    "требования", "обязанности", "условия", "html", "https", "сети",
    "документация", "медицина", "архитектура", "протоколы", "компас"
}

CASE_SENSITIVE_SHORT = {"ПК", "ИИ", "AI", "QA", "СВТ", "ЛВС", "ЛКС", "ТЗ", "БД", "ВНА", "НДС", "ТМЦ", "РСБУ"}


def build_skill_pattern(skill: str):
    if skill.lower() in {"1с", "1c"}:
        return skill, re.compile(r"(?<![a-zа-яё0-9])1\s*[сc](?![a-zа-яё0-9])", re.IGNORECASE)

    if skill in CASE_SENSITIVE_SHORT or (len(skill) <= 2 and skill not in {"C#", "C++"}):
        return skill, re.compile(rf"(?<![a-zA-Zа-яА-ЯёЁ0-9]){re.escape(skill)}(?![a-zA-Zа-яА-ЯёЁ0-9])")

    words = skill.split()
    if len(words) == 1:
        return skill, re.compile(rf"(?<![a-zа-яё0-9]){re.escape(skill)}(?![a-zа-яё0-9])", re.IGNORECASE)

    parts = []
    for w in words:
        if re.match(r"^[а-яёА-ЯЁ\-]+$", w) and len(w) >= 5:
            stem = w[:-2] if len(w) >= 6 else w[:-1]
            parts.append(rf"{re.escape(stem)}[а-яё]{{0,3}}")
        else:
            parts.append(re.escape(w))

    pattern_str = r"\s+".join(parts)
    return skill, re.compile(rf"(?<![a-zа-яё0-9]){pattern_str}(?![a-zа-яё0-9])", re.IGNORECASE)


COMPILED_PATTERNS = [
    build_skill_pattern(s)
    for s in sorted(ALL_SKILLS, key=len, reverse=True)
    if s.lower() not in BLACKLIST
]


def clean_and_normalize_text(text: str) -> str:
    text = re.sub(r"([a-zа-яё0-9])([A-ZА-ЯЁ])", r"\1 \2", text)
    text = re.sub(
        r"(?i)\b(?:условия(?:\s+работы)?|мы\s+предлагаем|социальный\s+пакет|компенсационный\s+пакет)\b[\s\S]*?(?=(?:\b(?:профессиональные\s+навыки|ключевые\s+навыки)\b|\Z))",
        " ",
        text
    )
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\S+\.html\S*", " ", text, flags=re.I)
    text = re.sub(r"\b(forceprinting|printing|vacancy|resume)=\w*\b", " ", text, flags=re.I)
    text = re.sub(r"\bsuper\s*job\b|\bheadhunter\b|\bhh\.ru\b", " ", text, flags=re.I)
    return text


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


def parse_skills_from_text(text: str):
    cleaned = clean_and_normalize_text(text)
    matched_skills = set()
    occupied_spans = []

    for skill_name, pattern in COMPILED_PATTERNS:
        for match in pattern.finditer(cleaned):
            start, end = match.span()
            if not any(s <= start and end <= e for s, e in occupied_spans):
                matched_skills.add(skill_name)
                occupied_spans.append((start, end))

    return matched_skills


fp_counter = Counter()
fn_counter = Counter()

for pdf_path in PDF_DIR.glob("*.pdf"):
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        raw_text = "\n".join([p.extract_text() or "" for p in reader.pages])
    except Exception:
        continue

    doc_id = extract_id_from_pdf(raw_text, pdf_path.name)
    if not doc_id:
        continue

    gt_row = df_gt[df_gt["id"] == doc_id]
    if gt_row.empty:
        continue

    true_skills = {c.lower() for c in ALL_SKILLS if gt_row[c].values[0] == 1}
    pred_skills = {s.lower() for s in parse_skills_from_text(raw_text)}

    fp_counter.update(pred_skills - true_skills)
    fn_counter.update(true_skills - pred_skills)

print("ТОП-15 ЛОЖНЫХ СРАБАТЫВАНИЙ (FP — парсер нашел лишнее):")
for term, count in fp_counter.most_common(15):
    print(f"  • {term}: {count} раз")

print("\nТОП-15 ПРОПУСКОВ (FN — разметка требует, а парсер не видит):")
for term, count in fn_counter.most_common(15):
    print(f"  • {term}: {count} раз")