import spacy
from spacy.matcher import PhraseMatcher
import re

nlp = spacy.load("ru_core_news_sm")

IT_ONTOLOGY = [
    "ооп", "solid", "микросервисы", "базы данных", "машинное обучение",
    "искусственный интеллект", "дискретная математика", "математическая логика",
    "математический анализ", "алгоритмы", "структуры данных", "асинхронность",
    "многопоточность", "devops", "аналитика", "бэкенд", "фронтенд", "1с", "1с-битрикс"
]


SYNONYMS_MAP = {
    "js": "javascript",
    "postgre": "postgresql",
    "postgres": "postgresql",
    "react.js": "react",
    "vue.js": "vue",
    "node": "node.js",
    "k8s": "kubernetes",
    "c++": "cpp",
    "c#": "csharp",
    "ии": "искусственный интеллект",
    "ml": "машинное обучение",
    "bd": "базы данных",
    "бд": "базы данных"
}

STOP_WORDS = {
    "and", "or", "for", "with", "the", "api", "backend", "frontend",
    "middle", "junior", "senior", "developer", "engineer", "framework",
    "team", "project", "work", "fast", "code", "merge", "pull", "push",
    "requests", "review", "b2b", "btl", "bpc", "pr", "cv", "hr",
    "2b", "app", "web"
}

matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
patterns = [nlp.make_doc(text) for text in IT_ONTOLOGY]
matcher.add("IT_SKILLS", patterns)


def extract_smart_skills(text: str) -> list:
    text_lower = text.lower()
    skills_set = set()

    # Предварительная очистка текста
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

    # 1. Извлечение через Spacy
    doc = nlp(text_lower)

    # Добавляем слова из онтологии
    matches = matcher(doc)
    for match_id, start, end in matches:
        skills_set.add(doc[start:end].text)

    valid_pos = {"NOUN", "PROPN", "ADJ", "X"}

    for token in doc:
        lemma = token.lemma_
        if len(lemma) > 1 and lemma not in STOP_WORDS and token.pos_ in valid_pos:
            # Дополнительно фильтруем технический английский, который Spacy часто размечает как X или PROPN
            if re.search(r'[a-z]', lemma):
                skills_set.add(lemma)

    # Ручные фиксы
    if re.search(r'\b[cс]\b', text_lower):
        skills_set.add("c")
    if re.search(r'\b1[cс]\b', text_lower):
        skills_set.add("1c")

    # 2. Нормализация синонимов и очистка
    normalized_skills = set()
    for skill in skills_set:
        clean_skill = skill.strip('-./')
        # Если есть в маппинге синонимов - заменяем
        mapped_skill = SYNONYMS_MAP.get(clean_skill, clean_skill)

        if len(mapped_skill) > 1 and not any(domain in mapped_skill for domain in ['.ru', '.com', 'www', 'http']):
            normalized_skills.add(mapped_skill)


    return sorted(list(normalized_skills))