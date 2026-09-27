import os
import re
import json
from collections import Counter
from pathlib import Path
import pypdf

# Пути к данным
VACANCIES_DIR = Path("data/vacancies")  # Укажи свою папку с PDF, если отличается
OUTPUT_FILE = Path("api/mined_skills.json")

# Полный стоп-лист от служебного мусора площадок, соцпакета и метаданных
STOP_WORDS = {
    # Веб-мусор, URL, платформы
    "html", "google", "yandex", "mail", "superjob", "headhunter", "hh", "ru",
    "com", "net", "org", "https", "http", "www", "forceprinting", "print",
    "printing", "vacancy", "resume", "edtech", "b2b", "b2c", "e-commerce",

    # Документы, юрлица, бытовой контекст
    "тк рф", "дмс", "рф", "ооо", "зао", "пао", "руб", "рублей", "руб/месяц",
    "по", "пк", "ит", "it", "ms", "data", "developer", "tanks", "blitz",

    # Служебные слова описаний вакансий
    "обновлена", "вакансия", "резюме", "опыт", "работы", "требования",
    "обязанности", "условия", "график", "отпуск", "больничный", "оклад",
    "заработная", "плата", "месяц", "год", "года", "лет", "день", "дни",
    "москва", "россия", "офис", "компания", "клиент", "сотрудник", "работа",
    "полный", "рабочий", "время", "период", "рамках", "умение", "знание",
    "навык", "понимание", "наличие", "соответствии", "результатам", "участие"
}


def clean_noise(text: str) -> str:
    """Очищает текст от веб-ссылок, параметров печати, почт и колонтитулов."""
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"www\.\S+", " ", text)
    text = re.sub(r"\S+\.html\S*", " ", text, flags=re.I)
    text = re.sub(r"\b(forceprinting|printing|vacancy|resume)=\w*\b", " ", text, flags=re.I)
    text = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", " ", text)
    text = re.sub(r"\b\d+/\d+\b", " ", text)
    text = re.sub(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b", " ", text)
    text = re.sub(r"\bsuper\s*job\b|\bheadhunter\b|\bhh\.ru\b", " ", text, flags=re.I)
    return text


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Извлекает весь текст из страниц PDF-документа."""
    text_content = []
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text_content.append(extracted)
    except Exception as e:
        print(f"Ошибка чтения {pdf_path.name}: {e}")
    return "\n".join(text_content)


def mine_candidates_from_text(raw_text: str) -> Counter:
    """Извлекает латинские стеки, аббревиатуры и термины из очищенного текста."""
    text = clean_noise(raw_text)
    counts = Counter()

    # 1. Латинские технологии, фреймворки, языки (Python, Docker, React, SQL, CI/CD)
    latin_tokens = re.findall(r"\b[A-Za-z][A-Za-z0-9\+#\.\-_]{1,25}\b", text)
    for token in latin_tokens:
        clean_tok = token.strip("._-").lower()
        if len(clean_tok) > 1 and clean_tok not in STOP_WORDS:
            counts[clean_tok] += 1

    # 2. Русские аббревиатуры и технические термины (АСУ ТП, БПЛА, СКУД, РСБУ, КИПиА)
    acronyms = re.findall(r"\b[А-ЯЁ]{2,6}(?:\s+[А-ЯЁ]{2,6})?\b", text)
    for acr in acronyms:
        clean_acr = acr.strip().lower()
        if clean_acr not in STOP_WORDS and len(clean_acr) >= 2:
            counts[clean_acr] += 1

    # 3. 1С в различных вариациях
    if re.search(r"(?<![a-zа-яё0-9])1[сc](?![a-zа-яё0-9])", text, re.I):
        counts["1с"] += 1

    return counts


def main():
    if not VACANCIES_DIR.exists():
        print(f"Директория {VACANCIES_DIR} не найдена. Проверь путь к папке с PDF.")
        return

    pdf_files = list(VACANCIES_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"В папке {VACANCIES_DIR} нет файлов .pdf")
        return

    print(f"Найдено PDF-файлов для анализа: {len(pdf_files)}")
    total_counter = Counter()

    for file_path in pdf_files:
        raw_text = extract_text_from_pdf(file_path)
        counts = mine_candidates_from_text(raw_text)
        total_counter.update(counts)

    # Сохраняем в структурированный словарь терминов с регулярными паттернами
    structured_taxonomy = {}
    for term, freq in total_counter.most_common():
        # Оставляем только повторяющиеся сущности (встретились хотя бы 2 раза)
        if freq >= 2:
            structured_taxonomy[term] = {
                "frequency": freq,
                "pattern": rf"(?<![a-zа-яё0-9]){re.escape(term)}(?![a-zа-яё0-9])"
            }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(structured_taxonomy, f, ensure_ascii=False, indent=2)

    print(f"\nМайнинг успешно завершен! Собрано навыков: {len(structured_taxonomy)}")
    print(f"Файл сохранен: {OUTPUT_FILE}")

    print("\nТоп-30 технических навыков выборки:")
    top_items = [item for item in total_counter.most_common(50) if item[0] in structured_taxonomy][:30]
    for term, freq in top_items:
        print(f"  • {term}: {freq} раз")


if __name__ == "__main__":
    main()