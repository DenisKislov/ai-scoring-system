import spacy
import re

# Загружаем языковую модель
try:
    nlp = spacy.load("ru_core_news_sm")
except OSError:
    import subprocess

    subprocess.run(["python", "-m", "spacy", "download", "ru_core_news_sm"])
    nlp = spacy.load("ru_core_news_sm")


def extract_smart_skills(text: str, top_n: int = 20) -> list:
    doc = nlp(text.lower())
    skills_set = set()

    # Максимально жесткий стоп-лист для отсева одиночного мусора
    stop_words = {
        "опыт", "работа", "год", "требование", "команда", "разработка",
        "проект", "знание", "понимание", "задача", "плюс", "решение",
        "уровень", "кандидат", "формат", "место", "модуль", "сервис",
        "система", "основа", "участие", "middle", "junior", "senior",
        "developer", "engineer", "backend", "frontend", "бэкенд", "фронтенд",
        "разработчик", "написание", "производительность", "обработка", "настройка",
        "данные", "принцип", "умение", "график", "практика", "оплата",
        "владение", "возможность", "интеграция", "дмс", "код", "база",
        "создание", "использование", "условие", "обязанность", "конференция",
        "компенсация", "спорт", "профессионал", "удаленка", "упаковка",
        "оптимизация", "узкий", "максимальный", "базовый", "реляционный",
        "уверенный", "дружный", "частичный", "профильный", "гибкий",
        # Специфичный мусор от разорванных биграмм
        "микро", "pull", "push", "requests", "review", "merge", "code"
    }

    for token in doc:
        # Пропускаем знаки препинания, пробелы и базовые стоп-слова
        if token.is_punct or token.is_space or token.is_stop:
            continue

        word = token.text.strip('-./')
        lemma = token.lemma_.strip('-./')

        if not word or not lemma:
            continue

        # 1. АНГЛИЙСКИЕ ТЕРМИНЫ (Латиница + спецсимволы вроде C++, C#)
        if re.match(r'^[a-z0-9\+#]+$', word):
            if word not in stop_words and not word.isdigit():
                # Простой хардкод для самых частых разорванных терминов
                if word in ['ci', 'cd']:
                    skills_set.add('ci/cd')
                else:
                    skills_set.add(word)

        # 2. РУССКИЕ ТЕРМИНЫ (Только чистые существительные длиннее 3 букв)
        elif re.match(r'^[а-яё]+$', lemma):
            if token.pos_ in ["NOUN", "PROPN"] and lemma not in stop_words and len(lemma) > 3:
                skills_set.add(lemma)

    # 3. ПОСТ-ОБРАБОТКА И ФОРМАТИРОВАНИЕ
    final_skills = sorted(list(skills_set))

    # Защита от дубликатов, если ci/cd добавился, удаляем возможные ошметки
    if 'ci/cd' in final_skills:
        final_skills = [s for s in final_skills if s not in ('ci', 'cd')]

    return final_skills[:top_n]