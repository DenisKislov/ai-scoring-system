# Сборщик открытых страниц hh.ru

Отдельный Scrapy-проект для получения вакансий, компаний и доступных полей резюме. Для запуска сайта и текущего синтетического бенчмарка этот сборщик не нужен. Он не выполняет рабочее NLP-извлечение навыков: в веб-сервисе за него отвечают spaCy и словарные правила модуля `scorer`.

## Структура

| Файл | Назначение |
|---|---|
| `main.py`, `gb_parse/main.py` | Точки запуска |
| `config/config.json` | Поисковые URL и флаги типов документов |
| `gb_parse/spiders/hh.py` | Обход страниц |
| `gb_parse/items.py`, `gb_parse/loaders.py` | Поля и обработка элементов |
| `gb_parse/pipelines.py` | Запись в MongoDB |
| `gb_parse/settings.py` | Настройки Scrapy и БД |

## Запуск

Из корня проекта в отдельном Python-окружении:

```bash
python -m pip install -r Parser/requirements.txt
cd Parser
scrapy crawl hh -s ROBOTSTXT_OBEY=True
```

Перед запуском выберите разрешённые URL в `config/config.json`. Доступность отдельных полей зависит от сайта и авторизации. Сборщик не обходит ограничения доступа.

`MONGO_URI` и `MONGO_DB` читаются из окружения, по умолчанию `mongodb://localhost:27017` и `gb_parse`. Параметры проекта: `DOWNLOAD_DELAY=1.5`, `CONCURRENT_REQUESTS=32`; настройки конкретного запуска можно переопределить флагами Scrapy. Для исследования следует использовать отдельную БД.

Вспомогательные утилиты `scripts/print_from_mongodb.py` и `scripts/extract_years_of_experience.py` находятся в корневом каталоге `scripts/`. В рабочем сервисе стаж извлекается при загрузке через `api.nlp_parser.extract_experience_years` и используется только для равных Score.

Исходные пользовательские PDF не входят в поставку. Для воспроизводимой проверки используйте [синтетический PDF-набор](../data/pmi_acceptance_release_2026-11-18/) и [инструкцию](../docs/ACCEPTANCE_DATASET.md).
