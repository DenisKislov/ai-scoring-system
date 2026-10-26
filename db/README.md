# db/ — слой доступа к MongoDB + мост «парсер → скорер»

Связывает данные в формате hh.ru (от Scrapy-паука или синтетического сидера) со скорером: читает вакансии/резюме, собирает из них текст для скоринга, считает и **сохраняет результаты**. Чистая интеграция — сама алгоритмика живёт в [`scorer/`](../scorer/README.md).

## Файлы

| Файл | Роль |
|---|---|
| [`mongo.py`](mongo.py) | Доступ к MongoDB: соединение (lazy, pooled), CRUD вакансий/резюме, upsert скорингов и фидбека |
| [`builders.py`](builders.py) | Превращение hh-item → текст для скорера + извлечение лет опыта |
| [`seed.py`](seed.py) | Заливка синтетики в hh-формате (CLI `python -m db.seed`) |

## mongo.py

Соединение настраивается переменными окружения (с дефолтами парсера):

| Переменная | По умолчанию | Что |
|---|---|---|
| `MONGO_URI` | `mongodb://mongo:27017` | URI подключения; для локального API задайте `mongodb://localhost:27017` |
| `MONGO_DB` | `gb_parse` | Имя базы |

Коллекции (константы `COLL_*`): `hh` (вакансии), `hh_resumes` (резюме), `hh_scores` (скоринги), `hh_feedback` (решения HR).

Ключевые функции:
- `list_vacancies` / `get_vacancy`, `list_resumes` / `get_resume` — чтение; `_id` отдаётся строкой (JSON-friendly).
- `save_scores(vacancy_id, ranked)` — вводится по ключу `(vacancy_id, resume_id)`: чтобы при перезапуске система подсчета заменяла, а не дублировала предыдущие подсчеты. Поля: `score`, `raw_score`, `keyword_score`, `cosine_sim`, `matched_skills[]`, `missing_skills[]`, `rank_percentile`, `experience_years`, `created_at`, `updated_at`.
- `get_scores(vacancy_id, top)` — результаты вакансии, сортирует по `score` ↓.
- `save_feedback` / `get_feedback` — решение HR (`"yes"`/`"no"`) по паре (вакансия, резюме), upsert.

> `get_scores` сортирует только по `score`. Тайм-брейк по годам опыта применяется в слое сервиса (`scorer/service.py`) при формировании выдачи — сам по себе `get_scores` порядок внутри одинаковых скоров не гарантирует.

## builders.py

- `vacancy_text(item)` — `title + description + skills + tags`.
- `resume_text(item)` — `title + specialization + experience + skills + tags`. Поля могут быть `str`/`list`/`None` — безопасно нормализуются.
- `experience_years(item)` — числовое поле, затем парсер текстового опыта и `_raw_text`. Поддерживаются годы, месяцы, дробные формулировки и пересекающиеся периоды работы. Опыт используется для упорядочивания при равном Score.
- `parse_raw_text_to_resume(text)` — навыки из единого `scorer.extract_skills` и опыт из `api.nlp_parser.extract_experience_years`.

> **Anti-bias:** `resume_text` намеренно **не включает** `age`, `gender`, `address` — они изолированы от признаков на уровне сборки.

## seed.py

Заливает синтетику (`data.synthetic.generate_dataset`) в коллекции `hh`/`hh_resumes` в формате hh.ru item, с служебными полями `_synthetic`, `_target_vacancy_url`, `_true_relevance` (для eval/интеграции). Поле `skills` извлекается из видимого текста; скрытые навыки генератора не передаются рабочему скореру. `--clear` удаляет синтетику и все скоринги.

```bash
python -m db.seed [--vacancies 6] [--resumes 20] [--seed 42] [--clear]
```

## Зависимости

`pymongo>=4.0`. Без собственного `requirements.txt` — ставится на уровне проекта (см. корневой README: `pip install -r requirements.txt`).
