import json
import os
import re
from typing import List, Set, Dict
from sentence_transformers import SentenceTransformer

# Трансформер оставляем для семантического скоринга текстов
embedder = SentenceTransformer("cointegrated/rubert-tiny2")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_FILE = os.path.join(BASE_DIR, "esco_skills.json")
MINED_FILE = os.path.join(BASE_DIR, "mined_skills.json")

# 1. Базовый список таксономии
TAXONOMY_SKILLS: List[str] = []
if os.path.exists(SKILLS_FILE):
    with open(SKILLS_FILE, "r", encoding="utf-8") as f:
        TAXONOMY_SKILLS = [s.strip().lower() for s in json.load(f)]

# 2. Загрузка базы терминов автоматического майнинга
MINED_TAXONOMY: Dict[str, dict] = {}
if os.path.exists(MINED_FILE):
    with open(MINED_FILE, "r", encoding="utf-8") as f:
        MINED_TAXONOMY = json.load(f)

# 3. Структурированная карта синонимов и паттернов (Alias Map)
SKILL_ALIASES: Dict[str, List[str]] = {
    "bash": [r"\bbash\b", r"\bsh\b"],
    "powershell": [r"\bpowershell\b", r"\bps1\b"],
    "linux": [r"\blinux\b", r"\bлинукс\b", r"\bastra\s*linux\b", r"\balt\s*linux\b", r"\bubuntu\b", r"\bdebian\b",
              r"\bcentos\b", r"\bredhat\b"],
    "windows server": [r"\bwindows\s*server\b", r"\bmcs[ae]\b", r"\bactive\s*directory\b", r"\bsambadc\b"],
    "zabbix": [r"\bzabbix\b"],
    "vlan": [r"\bvlan\b", r"\b802\.1q\b"],
    "vpn": [r"\bvpn\b", r"\bipsec\b", r"\bopenvpn\b", r"\bwireguard\b"],
    "dhcp": [r"\bdhcp\b"],
    "dns": [r"\bdns\b", r"\bbind9?\b"],
    "itsm": [r"\bitsm\b", r"\bitil\b", r"\binframanager\b"],
    "информационная безопасность": [r"\bинформационн\w+\s+безопасност\w+", r"\bиб\b", r"\bkaspersky\b"],
    "системное администрирование": [r"\bсистемн\w+\s+администрирован\w+", r"\bсетев\w+\s+администратор\w*"],

    # Веб и бэкенд разработка
    "python": [r"\bpython\b", r"\bпитон\b"],
    "java": [r"\bjava\b(?!\s*script)"],
    "swift": [r"\bswift\b"],
    "css": [r"\bcss3?\b"],
    "sass": [r"\bsass\b", r"\bscss\b"],
    "sql": [r"\bsql\b", r"\bpostgresql\b", r"\bmysql\b"],
    "mongodb": [r"\bmongodb\b", r"\bmongo\b"],
    "rest api": [r"\brest\s*api\b", r"\brestful\b", r"\brest\b"],
    "solid": [r"\bsolid\b"],
    "ооп": [r"\bооп\b", r"\boop\b", r"\bобъектно[- ]ориентированн\w+"],
    "unit-тестирование": [r"\bunit[- ]тестирован\w+", r"\bюнит[- ]тест\w*", r"\bpytest\b"],
    "c": [r"\bязык\s+[cс]\b", r"\bпрограммировани[ея]\s+на\s+[cс]\b"],
    "c++": [r"\bc\+\+\b", r"\bси\+\+\b"],
    "1с": [r"(?<![a-zа-яё0-9])1с(?![a-zа-яё0-9])", r"(?<![a-zа-яё0-9])1c(?![a-zа-яё0-9])"],

    # Data Science & AI
    "data science": [r"\bdata\s*science\b", r"\bдата\s*сайнс\b"],
    "nlp": [r"\bnlp\b", r"\bобработк\w+\s+естественного\s+языка\b"],

    # Управление, бизнес, документация
    "техническое задание": [r"\bтехническ\w+\s+задани\w+", r"(?<![a-zа-яё0-9])тз(?![a-zа-яё0-9])"],
    "бизнес-процессы": [r"\bбизнес[- ]процесс\w+"],
    "делегирование": [r"\bделегирован\w+"],
    "оргтехника": [r"\bоргтехник\w+"],
    "seo": [r"\bseo\b"],

    # Инженерные и производственные стеки
    "autocad": [r"\bautocad\b", r"\bавтокад\b"],
    "системы контроля доступа": [r"\bскуд\b", r"\bсистем\w*\s+контроля\s+доступа\b", r"\bсистем\w*\s+допуска\b"],
    "пусконаладочные работы": [r"\bпусконаладочн\w+\s+работ\w+", r"\bпнр\b", r"\bналадк\w+"],
    "проектирование слаботочных систем": [r"\bслаботочн\w+\s+систем\w+"],
    "асу тп": [r"\bасу\s*тп\b"],

    # Профиль HR и бухгалтерии
    "кадровое делопроизводство": [r"\bкадров\w+\s+делопроизводств\w+"],
    "подбор персонала": [r"\bподбор\w*\s+персонала\b", r"\bрекрутинг\w*"],
    "рсбу": [r"(?<![a-zа-яё0-9])рсбу(?![a-zа-яё0-9])"],
    "мсфо": [r"(?<![a-zа-яё0-9])мсфо(?![a-zа-яё0-9])"],
    "управленческий учет": [r"\bуправленческ\w+\s+учет\w*"]
}

STOP_WORDS = {
    "superjob", "headhunter", "hh.ru", "резюме", "вакансия", "обновлена",
    "москва", "россия", "опыт работы", "условия", "требования", "обязанности"
}


def clean_structural_noise(text: str) -> str:
    """Удаляет технический шум, URL-адреса и служебные заголовки."""
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"www\.\S+", " ", text)
    text = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", " ", text)
    text = re.sub(r"\b\d+/\d+\b", " ", text)
    text = re.sub(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b", " ", text)
    text = re.sub(r"\b(forceprinting|printing|vacancy|resume)=\w*\b", " ", text, flags=re.I)
    text = re.sub(r"\bsuper\s*job\b|\bheadhunter\b|\bhh\.ru\b", " ", text, flags=re.I)
    return text


def extract_explicit_section_skills(text: str) -> Set[str]:
    """Извлекает навыки, явно выписанные в блоке профессиональных навыков."""
    found = set()
    pattern = r"(?:Профессиональные навыки|Ключевые навыки)\s*([\s\S]*?)(?:(?:\n\s*(?:Условия|Контакты|О компании|Опыт работы)\b)|\Z)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        raw_section = match.group(1).strip()
        lines = [re.sub(r"\(.*?\)", "", l).strip(" :•-") for l in raw_section.splitlines() if l.strip()]
        for line in lines:
            for part in re.split(r"[,;•\n\t]+", line):
                item = part.strip().lower()
                if len(item) >= 2 and item not in STOP_WORDS:
                    found.add(item)
    return found


def extract_smart_skills(text: str) -> list:
    """Детерминированное извлечение навыков через Alias Map, базу майнинга и явный блок."""
    if not text:
        return []

    cleaned = clean_structural_noise(text)
    text_lower = cleaned.lower()
    extracted_skills: Set[str] = set()

    # 1. Поиск по явной карте алиасов и синонимов
    for skill_name, patterns in SKILL_ALIASES.items():
        for pat in patterns:
            if re.search(pat, text_lower, re.IGNORECASE):
                extracted_skills.add(skill_name)
                break

    # 2. Поиск по автоматически сгенерированной таксономии майнинга
    for skill, data in MINED_TAXONOMY.items():
        pattern = data.get("pattern")
        if pattern and re.search(pattern, text_lower, re.IGNORECASE):
            extracted_skills.add(skill)

    # 3. Прямой подхват из блока «Профессиональные навыки»
    section_items = extract_explicit_section_skills(cleaned)
    for item in section_items:
        if item in TAXONOMY_SKILLS or item in MINED_TAXONOMY:
            extracted_skills.add(item)

    return sorted(list(extracted_skills))