import os
import re
from pathlib import Path
from collections import Counter
import pandas as pd
import pypdf

BASE_DIR = Path(__file__).resolve().parent
EXEL_DIR = BASE_DIR / "exel"
RESUMES_GT_PATH = EXEL_DIR / "ground_truth_resumes.csv"
PDF_DIR = EXEL_DIR / "Резюме в pdf"

if not RESUMES_GT_PATH.exists():
    raise FileNotFoundError(f"Файл не найден: {RESUMES_GT_PATH}")

df_gt = pd.read_csv(RESUMES_GT_PATH)
ALL_SKILLS = [c for c in df_gt.columns if c != "id"]

# Базовый стоп-лист, который мы использовали ранее
BLACKLIST = {
    "разработка", "обучение", "внедрение", "аналитика", "позиции",
    "требования", "обязанности", "условия", "https", "сети",
    "документация", "медицина", "архитектура", "протоколы", "компас",
    "кросс-функциональная команда", "кросс-функциональные команды",
    "информационные технологии", "ТЗ", "автоматизация", "интеграции",
    "инструмент", "сборка", "инфраструктура", "мониторинг", "тестирование",
    "планирование", "стратегия", "серверы", "исследования", "контент",
    "отчеты", "c", "пк", "ии", "ai",
    "программирование", "администрирование", "метрики", "инструкции",
    "маркетинг", "фреймворки", "рефакторинг", "архитектурные решения",
    "техническая документация"
}

INLINE_ALIASES = {
    "C++": r"(?:c\+\+|си\s*\+\+)",
    "C#": r"(?:c\#|си\s*\#)",
    ".NET": r"(?:\.net|dotnet)",
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
    "ЛКС": r"(?:лкс|локальн\w+\s+кабельн\w+\s+сет\w*)",
    "AutoCAD": r"(?:autocad|автокад)",
    "RabbitMQ": r"(?:rabbitmq|rabbit\s*mq)",
    "gRPC": r"(?:grpc\s*api|grpc)",
    "СКУД": r"(?:скуд|систем\w+\s+контрол\w+\s+доступ\w*)"
}

STRICT_UPPERCASE = {"QA", "СВТ", "БД", "ВНА", "НДС", "ТМЦ", "РСБУ"}


def build_skill_pattern(skill: str):
    if skill in INLINE_ALIASES:
        return skill, re.compile(rf"(?<![a-zа-яё0-9]){INLINE_ALIASES[skill]}(?![a-zа-яё0-9])", re.IGNORECASE)

    if skill in STRICT_UPPERCASE:
        return skill, re.compile(rf"(?<![a-zA-Zа-яА-ЯёЁ0-9]){re.escape(skill)}(?![a-zA-Zа-яА-ЯёЁ0-9])")

    if re.match(r"^[a-zA-Z0-9\+\#\.\-_]+$", skill) and len(skill) <= 4:
        escaped = re.escape(skill)
        return skill, re.compile(rf"(?<![a-zа-яё0-9]){escaped}(?![a-zа-яё0-9])", re.IGNORECASE)

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


def clean_pdf_text(text: str) -> str:
    text = re.sub(r"([a-zа-яё0-9])([A-ZА-ЯЁ])", r"\1 \2", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\S+\.html\S*", " ", text, flags=re.I)
    text = re.sub(r"\b(forceprinting|printing|vacancy|resume)=\w*\b", " ", text, flags=re.I)
    text = re.sub(r"\bsuper\s*job\b|\bheadhunter\b|\bhh\.ru\b", " ", text, flags=re.I)
    return text


def extract_id(text: str, filename: str) -> int:
    for m in re.findall(r"\b\d{7,9}\b", filename) + re.findall(r"\b\d{7,9}\b", text[:600]):
        val = int(m)
        if val in df_gt["id"].values:
            return val
    for m in re.findall(r"\b\d{7,9}\b", text):
        val = int(m)
        if val in df_gt["id"].values:
            return val
    return 0


def parse_skills(raw_text: str) -> set:
    cleaned = clean_pdf_text(raw_text)
    matched = set()
    occupied = []
    for skill_name, pattern in COMPILED_PATTERNS:
        for m in pattern.finditer(cleaned):
            s, e = m.span()
            if not any(os <= s and e <= oe for os, oe in occupied):
                matched.add(skill_name)
                occupied.append((s, e))
    return matched


fp_counter = Counter()
fn_counter = Counter()
processed = 0

print("Сбор статистики по ошибкам в резюме...")

for pdf_path in sorted(list(PDF_DIR.glob("*.pdf"))):
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        raw = "\n".join([p.extract_text() or "" for p in reader.pages])
    except Exception:
        continue

    doc_id = extract_id(raw, pdf_path.name)
    if not doc_id:
        continue

    gt_row = df_gt[df_gt["id"] == doc_id]
    if gt_row.empty:
        continue

    true_skills = {c.lower() for c in ALL_SKILLS if gt_row[c].values[0] == 1}
    pred_skills = {s.lower() for s in parse_skills(raw)}

    fp_counter.update(pred_skills - true_skills)
    fn_counter.update(true_skills - pred_skills)
    processed += 1

print(f"\nУспешно обработано: {processed} резюме")
print("\n--- ТОП-20 ЛОЖНЫХ СРАБАТЫВАНИЙ В РЕЗЮМЕ (FP) ---")
for k, v in fp_counter.most_common(20):
    print(f"  • {k}: {v}")

print("\n--- ТОП-20 ПРОПУСКОВ В РЕЗЮМЕ (FN) ---")
for k, v in fn_counter.most_common(20):
    print(f"  • {k}: {v}")

