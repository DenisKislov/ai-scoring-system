import re
from typing import Set, List, Tuple

BLACKLIST = {
    # Корпоративный и структурный шум
    "разработка", "обучение", "внедрение", "аналитика", "позиции",
    "требования", "обязанности", "условия", "https", "сети",
    "документация", "медицина", "архитектура", "протоколы", "компас",
    "кросс-функциональная команда", "кросс-функциональные команды",
    "информационные технологии", "ТЗ", "автоматизация", "интеграции",
    "инструмент", "сборка", "инфраструктура", "мониторинг", "тестирование",
    "планирование", "стратегия", "серверы", "исследования", "контент",
    "отчеты", "c", "пк", "ии", "ai", "программирование", "администрирование",
    "метрики", "инструкции", "маркетинг", "фреймворки", "рефакторинг",
    "архитектурные решения", "техническая документация",
    # Шум из резюме и роли
    "английский язык", "английский", "frontend", "backend", "ui",
    "верстка", "вёрстка", "spa", "алгоритмы", "ооп", "excel", "crm",
    "api", "django framework", "rest", "data science"
}

INLINE_ALIASES = {
    "C++": r"(?:c\+\+|си\s*\+\+)",
    "C#": r"(?:c\#|си\s*\#)",
    ".NET": r"(?:\.net|dotnet)",
    "PostgreSQL": r"(?:postgresql|postgres|psql|постгрес)",
    "Postgres": r"(?:postgresql|postgres|psql|постгрес)",
    "JavaScript": r"(?:javascript|js(?![a-z])|яваскрипт)",
    "TypeScript": r"(?:typescript|ts(?![a-z])|тайпскрипт)",
    "FastAPI": r"(?:fastapi|fast\s*api)",
    "Fast API": r"(?:fastapi|fast\s*api)",
    "MySQL": r"(?:mysql|my\s*sql)",
    "MongoDB": r"(?:mongodb|mongo\s*db|mongo\b)",
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
    "REST API": r"(?:rest\s*api|restful\s*api|restful\b)",
    "GitHub Actions": r"(?:github\s*actions|gh\s*actions)",
    "GitLab CI/CD": r"(?:gitlab\s*ci(?:/cd)?|gitlab\s*ci)",
    "jQuery": r"(?:jquery|j\s*query)",
    "PyTorch": r"(?:pytorch|py\s*torch)",
    "NumPy": r"(?:numpy|num\s*py)",
    "scikit-learn": r"(?:scikit\-learn|scikit\s*learn|sklearn)",
    "WebSocket": r"(?:websocket|web\s*socket|ws\b)",
    "pyTelegramBotAPI": r"(?:pytelegrambotapi|telebot)",
    "Telegram Bot API": r"(?:telegram\s*bot\s*api)",
    "Java": r"(?<![a-zа-яё0-9])java(?![a-zа-яё0-9]|script)"
}

STRICT_UPPERCASE = {"QA", "СВТ", "БД", "ВНА", "НДС", "ТМЦ", "РСБУ", "CI/CD"}


class SkillExtractor:
    def __init__(self, taxonomy: List[str]):
        self.patterns: List[Tuple[str, re.Pattern]] = []
        sorted_skills = sorted(set(taxonomy), key=len, reverse=True)
        for skill in sorted_skills:
            if skill.lower() in BLACKLIST or skill in BLACKLIST:
                continue
            self.patterns.append(self._compile_pattern(skill))

    def _compile_pattern(self, skill: str) -> Tuple[str, re.Pattern]:
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

    @staticmethod
    def clean_text(text: str) -> str:
        # Разлепляем только кириллицу (не ломая латинский стек)
        text = re.sub(r"([а-яё0-9])([А-ЯЁ])", r"\1 \2", text)

        # Срезаем блок иностранных языков
        text = re.sub(
            r"(?i)\b(?:знание\s+языков|иностранные\s+языки|владение\s+языками)\b[\s\S]*?(?=(?:\b(?:навыки|ключевые\s+навыки|опыт\s+работы|образование|обо\s+мне|курсы)\b|\Z))",
            " ",
            text
        )

        # Срезаем соцпакет и условия (для вакансий)
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

    def extract(self, raw_text: str) -> Set[str]:
        cleaned = self.clean_text(raw_text)
        matched_skills = set()
        occupied_spans = []

        for skill_name, pattern in self.patterns:
            for match in pattern.finditer(cleaned):
                start, end = match.span()
                if not any(s <= start and end <= e for s, e in occupied_spans):
                    # Приводим варианты написания к канонической форме
                    canonical_name = "FastAPI" if skill_name in {"Fast API", "fastapi"} else skill_name
                    matched_skills.add(canonical_name)
                    occupied_spans.append((start, end))

        return matched_skills