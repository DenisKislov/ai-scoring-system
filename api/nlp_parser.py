import spacy
from spacy.matcher import PhraseMatcher
import re

try:
    nlp = spacy.load("ru_core_news_sm")
except OSError:
    import subprocess
    subprocess.run(["python", "-m", "spacy", "download", "ru_core_news_sm"])
    nlp = spacy.load("ru_core_news_sm")

matcher = PhraseMatcher(nlp.vocab, attr="LOWER")

IT_ONTOLOGY = [
    "ооп", "solid", "микросервисы", "базы данных", "машинное обучение",
    "искусственный интеллект", "дискретная математика", "математическая логика",
    "математический анализ", "алгоритмы", "структуры данных", "асинхронность",
    "многопоточность", "devops", "аналитика", "бэкенд", "фронтенд", "1с", "1с-битрикс"
]
patterns = [nlp.make_doc(text) for text in IT_ONTOLOGY]
matcher.add("IT_SKILLS", patterns)

STOP_WORDS = {
    "and", "or", "for", "with", "the", "api", "backend", "frontend",
    "middle", "junior", "senior", "developer", "engineer", "framework",
    "team", "project", "work", "fast", "code", "merge", "pull", "push",
    "requests", "review", "b2b", "btl", "bpc", "pr", "cv", "hr",
    "2b", "app", "web"
}

def extract_smart_skills(text: str, top_n: int = 20) -> list:
    text_lower = text.lower()
    skills_set = set()

    fixes = {
        r'\bfast\s*api\b': 'fastapi',
        r'\bpostgre\s*sql\b': 'postgresql',
        r'\bjava\s*script\b': 'javascript',
        r'\bj\s*query\b': 'jquery',
        r'\bms\s*sql\b': 'mssql',
        r'\bci\s*/\s*cd\b': 'ci/cd',
        r'\brest\s*api\b': 'rest',
        r'\basp\.\s*net\b': 'asp.net',
        r'\bnode\.?\s*js\b': 'node.js',
        r'c#/\.net': 'c# .net',
    }
    for pattern, replacement in fixes.items():
        text_lower = re.sub(pattern, replacement, text_lower)

    raw_words = re.findall(r'[a-z0-9\+\#\-\.\/]+', text_lower)
    for w in raw_words:
        clean_w = w.strip('-./')

        if len(clean_w) < 2 and clean_w not in ['c', 'r']:
            continue

        if not re.search(r'[a-z]', clean_w):
            continue

        if any(domain in clean_w for domain in ['.ru', '.com', 'www', 'http']):
            continue

        if clean_w in STOP_WORDS:
            continue

        skills_set.add(clean_w)

    if re.search(r'\b[cс]\b', text_lower):
        skills_set.add("c")
    if re.search(r'\b1[cс]\b', text_lower):
        skills_set.add("1c")

    doc = nlp(text_lower)
    matches = matcher(doc)
    for match_id, start, end in matches:
        span = doc[start:end]
        skills_set.add(span.text)

    final_skills = sorted(list(skills_set))
    return final_skills[:top_n]