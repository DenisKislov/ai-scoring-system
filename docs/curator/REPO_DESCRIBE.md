# REPO_DESCRIBE — описание репозитория

**AI-система для скоринга кандидатов при приёме на работу**: веб-приложение,
которое принимает вакансии и резюме (файлы PDF/TXT или JSON-импорт),
извлекает из них навыки и опыт, ранжирует кандидатов под вакансию и
показывает HR рейтинг с детализацией — какие требования закрыты, каких
навыков не хватает, какой у кандидата стаж.

Проект выполнен по кейсу НГУ (см. `T1_1_«AI_система_для_скоринга_кандидатов…».docx`,
`Кейсы для НГУ.docx`); рабочие документы команды — в `data/DATA_ENGINEER.md`.

---

## 1. Как устроена система

```
                 ┌───────────────────────────── Docker Compose ─────────────────────────────┐
                 │                                                                          │
  HR ──браузер──▶│  frontend (React+Nginx, :3000)                                            │
                 │        │ REST                                                            │
                 │        ▼                                                                 │
                 │  backend = api/ (FastAPI, :8000, Swagger /docs)                           │
                 │        │                        ▲                                         │
                 │        │ читает/пишет          │ scorer.service (CLI: python -m …)        │
                 │        ▼                        │                                         │
                 │  MongoDB 8 (db: gb_parse)      │                                          │
                 │    hh · hh_resumes · hh_scores · hh_feedback                              │
                 └────────────────────────────────┼──────────────────────────────────────────┘
                                                  │
                     scorer/ — ядро скоринга ◀────┘
                     (навыки, семьи, матчинг, косинус, метрики)
```

Поток данных: загрузка документа → `db/builders.py` собирает текст и
раскладывает его на поля (должность, навыки, опыт — парсеры `api/nlp_parser.py`
и `scorer/skills.py`) → документ кладётся в MongoDB → по запросу
`scorer.service.score_vacancy` достаёт пул резюме, считает гибридный скор
через `scorer/scoring.py`, сохраняет рейтинг в `hh_scores` и отдаёт в UI.
Решение рекрутера («релевантен/нерелевантен») пишется в `hh_feedback`.

---

## 2. Алгоритм скоринга

**Score = 100 × (0.85 × keyword + 0.15 × cosine)**, где:

* **keyword** — доля требований вакансии, закрытых навыками резюме.
  Навыки обеих сторон нормализуются к каноническим именям онтологии;
  совпадение засчитывается напрямую **или через семью навыков**
  (`scorer/skill_families.py`: MySQL/PostgreSQL/SQLite/ClickHouse закрывают
  «SQL», scikit-learn/Pytorch — «Machine Learning», Tableau/Power BI —
  «Аналитика данных», и т.д. — 15 семей). Критические (must-have) навыки,
  отмеченные в UI, весят ×2; их отсутствие видно отдельно в
  `missing_critical`.
* **cosine** — TF-IDF-косинус лемматизированных текстов вакансии и резюме
  (`scorer/similarity.py`; лемматизация pymorphy3+razdel в `scorer/normalize.py`).

**Опыт работы** (`api/nlp_parser.extract_experience_years`) — робастный парсер
русских формулировок («Опыт работы: 5 лет», «2 года и 1 месяц», «полгода»,
периоды «апрель 2021 — настоящее время» с суммированием и фильтрацией
учебных строк). В сам Score опыт не входит — используется как тай-брейк
при равном балле (решение зафиксировано в `scorer/service.py`).

**Извлечение навыков** (`scorer/skill_extractor.py`) — детерминированные
regex-паттерны по единой онтологии (~1800 имён), которая собирается из
курируемого словаря `scorer/skills_dict.py`, колонок ground-truth CSV и
`expected_skills` датасетов (`scorer/skills.py::_load_unified_taxonomy`).
Чёрный список шумовых слов + эмпирически защищённые ярлыки
(`PROTECTED_SKILLS`), дедупликация регистра — детали и обоснование в
`CODE_REVIEW.md`.

---

## 3. Каталоги и файлы

| Путь | Назначение |
|---|---|
| `api/` | FastAPI-сервис: роуты (`routes.py`), схемы (`schemas.py`), PDF/TXT-извлечение текста (`file_parser.py`, PyMuPDF), NLP-парсер навыков и опыта (`nlp_parser.py`) |
| `scorer/` | Ядро: `scoring.py` (формула, ранжирование, перцентили), `skills.py` (нормализация, матчинг), `skill_families.py` (семьи), `skill_extractor.py` (regex-экстрактор), `similarity.py` (TF-IDF-косинус), `metrics.py` (P/R/F1, nDCG, Spearman), `skills_categories.py` (категории для метрик), `skills_dict.py`/`skills_auto.json` (онтологии), `service.py` (мост API↔скорер, CLI) |
| `db/` | `mongo.py` (клиент, коллекции), `builders.py` (тексты документов, парсинг полей при загрузке, `experience_years`), `seed.py` (синтетический сидер) |
| `data/` | **Реальные данные**: `superjob_dataset.json` (101 вакансия SuperJob с `expected_skills`), `dataset_resume.json` (100 резюме), `ground_truth_{vacancies,resumes}.csv` (матрицы «документ × навык», 747 колонок), `skills_by_profession.json` + `profiles.py` + `synthetic.py` (генератор синтетики — только для демо/регрессии) |
| `AI-система для скоринга/` | Исходники разметки: PDF вакансий/резюме и копии ground-truth CSV |
| `scripts/` | Оценка: `benchmark_real_data.py` — **основной бенчмарк на реальных данных**; `benchmark.py`/`benchmark_resumes.py`/`audit_resumes.py`/`error_analysis.py` — старые скрипты с битыми путями (см. CODE_REVIEW §3); `detailed_audit.py` |
| `tests/` | pytest-набор (89 тестов: smoke, ranking, metrics, api, опыт, семьи, косинус) + `eval_synthetic.py` (регрессия ранжирования, nDCG ≥ 0.8) + `integration_demo.py` |
| `tools/` | Обслуживание онтологии: чистка корпуса профессий, авто-онтология (~97% покрытия тегов hh.ru), референс-корпус, live-проверка парсера |
| `Parser/` | Scrapy-парсер hh.ru (вакансии/компании/резюме → MongoDB). В основном пайплайне не используется (по решению команды оценка идёт на данных `data/`) |
| `frontend/` | React UI: загрузка файлов, выбор вакансии и критических навыков, рейтинг кандидатов, карточка с исходным текстом, HR-фидбек |
| корень | `docker-compose.yml` (mongo/backend/frontend), `backend.Dockerfile` (python:3.10-slim + spacy `ru_core_news_sm`), `collect_superjob.py` (экспериментальный SuperJob-парсер, **не работает** — датасет собран вручную), `build_esco_index.py` (ESCO-эмбеддинги для `api/esco_*.json`), требования по компонентам |

Документация: `README.md` (запуск в Docker, инструкция UI),
`RUNBOOK.md` (терминальные workflow), `CODE_REVIEW.md` (ревью + история
исправлений и метрики до/после), `data/README.md` и `data/DATA_ENGINEER.md`
(генератор синтетики), `tools/README.md`, `Parser/README.md`.

---

## 4. Технологии

* **Backend**: Python 3.10, FastAPI, uvicorn, pydantic; PyMuPDF (PDF), pymongo.
* **NLP/ML**: pymorphy3 + razdel (лемматизация/токенизация), scikit-learn,
  numpy, scipy (Spearman), rank-bm25; spacy `ru_core_news_sm` и
  sentence-transformers `rubert-tiny2` — опционально (эмбеддер ленивый).
* **Frontend**: React (create-react-app), Nginx в контейнере.
* **Инфраструктура**: Docker Compose — `mongo:8`, backend, frontend;
  MongoDB-база `gb_parse`, коллекции `hh` / `hh_resumes` / `hh_scores` / `hh_feedback`.

---

## 5. Качество: чем измеряется

* **Реальные данные** (`scripts/benchmark_real_data.py`, 101 вакансия ×
  100 резюме): nDCG@10 ≈ 0.74, Spearman ≈ 0.58, извлечение навыков
  P/R/F1 ≈ 0.78/0.63/0.69 (вакансии) и 0.62/0.53/0.58 (резюме), опыт
  распознаётся у 100/100 резюме, ~0.1 с на вакансию.
* **Регрессия ранжирования** (`tests/eval_synthetic.py`): nDCG@10 ≈ 0.99
  на синтетике с известной релевантностью (порог 0.8).
* Ground truth для извлечения — `expected_skills` JSON и CSV-матрицы;
  методика и известные ограничения разметки — в `CODE_REVIEW.md`.

## 6. Известные ограничения

1. Пул кандидатов на реальном датасете перекошен в data/IT-профиль — для
   нишевых вакансий (1С, сетевое оборудование) релевантных резюме в базе
   просто нет, скор честно низкий.
2. Требования вакансий к опыту («от 2 лет») не участвуют в скоринге —
   только тай-брейк (осознанный дизайн, см. `scorer/service.py`).
3. `metrics_by_category` в результатах — это покрытие требований вакансии
   навыками резюме, а не качество извлечения.
4. Старые скрипты `scripts/benchmark*.py`/`error_analysis.py`/`audit_resumes.py`
   ссылаются на несуществующие пути `scripts/exel/…` — не использовать.
5. `collect_superjob.py` помечен как нерабочий; `Parser/` (hh.ru) не входит
   в оцениваемый пайплайн.
