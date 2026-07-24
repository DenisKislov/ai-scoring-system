# AI-система для скоринга кандидатов при приёме на работу

Веб-сервис, который принимает описание вакансии и базу резюме и возвращает список кандидатов, **отсортированных по степени соответствия (Score 0–100%)**, с подсветкой найденных ключевых навыков. Учебный проект (2-й семестр, ОП «Прикладной искусственный интеллект»).

> **Подход к «AI»:** алгоритмический — поиск ключевых навыков, их взвешивание и TF-IDF + косинусное сходство текстов. Без обучения нейросетей с нуля (согласно ТЗ и ответам заказчика). 

> **Недостатки подхода:** Алгоритм не учитывает семантику слов. Есть более продвинутые алгоритмы для мешка слов чем  TF-IDF. 

---

## Быстрый старт (пошагово)

Все команды — из корня проекта, в окружении `candidate_scoring` (Python 3.10). Шаги 0–4 и 7 — разовые (выполнились и завершились). **Шаги 5 и 6 (API и UI) — это серверы: их запускают в отдельных терминалах, и они работают, пока не остановишь `Ctrl+C`.**

### Шаг 0. Создать окружение `candidate_scoring` и поставить зависимости (один раз)

Предусловие: установлен **conda** (Miniconda/Anaconda) и **Docker** (для MongoDB).


# 0.1. Создать conda-окружение с Python 3.10
conda create -n candidate_scoring python=3.10 -y

conda activate candidate_scoring           # повторять в каждом новом терминале!

# 0.2. Зависимости проекта (из корня репозитория)

pip install -r requirements.txt             # для всех пользователей

pip install -r scorer/requirements.txt      # для скоринга: pymorphy3 (+ RU-словари), razdel, scikit-learn, numpy, scipy

pip install -r api/requirements.txt         # для backend-а: fastapi, uvicorn

pip install -r Parser/requirements.txt      # для парсера: scrapy, pymongo, itemloaders (для живого сбора с hh.ru)

pip install -r tests/requirements.txt       # для тестировщиков: для проведения тестов

# 0.3. Проверка, что всё импортируется
python -c "import fastapi, sklearn, pymorphy3, razdel; print('ok')"


<details><summary>Если conda нет / хочется через venv</summary>


python3.10 -m venv .venv && source .venv/bin/activate

pip install -r scorer/requirements.txt -r api/requirements.txt -r Parser/requirements.txt

pip install pymongo faker streamlit pytest httpx

</details>

### Шаг 1. Поднять MongoDB


docker start mongo                         # контейнер уже создан

# первый раз на новой машине:  docker run -d --name mongo -p 27017:27017 mongo:8

docker exec mongo mongosh gb_parse --quiet --eval 'db.hh.countDocuments()'   # проверка: > 0


### Шаг 2. Наполнить БД данными

**Что делает:** наполняет MongoDB данными, которые будет ранжировать скорер (Шаг 3). Два источника — синтетический генератор (основной) и живой парсер hh.ru.

**Почему синтетика — основной путь:** реальные резюме недоступны (152-ФЗ + employer-логин hh.ru прячет их за входом), а генератор зашивает в каждое резюме `_true_relevance` — ground-truth, без которого метрики качества (Шаг 4) не посчитать.

| Источник | Команда | Куда пишет | Что даёт |
|---|---|---|---|
| Синтетика | `python -m db.seed …` | `hh`, `hh_resumes` (`_synthetic: True`) | вакансии + резюме с ground-truth (`_true_relevance`, `_target_vacancy_url`) |
| Парсер hh.ru | `cd Parser && python main.py` | `hh`, `hh_resumes`, `hh_companies` | реальные **вакансии** (резюме за логином → 0) |


python -m db.seed --clear                  # синтетика с нуля: стирает старую синтетику + все scores, генерит заново

python -m db.seed --vacancies 10 --resumes 40   # своя пропорция (без --clear — добавит к существующим)

# живой сбор с hh.ru (опционально). Резюме за employer-логином, поэтому пул берём из синтетики:
cd Parser && pip install -r requirements.txt && python main.py && cd ..
# быстрый тест парсера без записи в Mongo (8 страниц → out.json):
cd Parser && scrapy crawl hh -s CLOSESPIDER_PAGECOUNT=8 -s ITEM_PIPELINES={} -O out.json && cd ..


Флаги `db.seed`:

| Флаг | Назначение |
|---|---|
| `--vacancies N` | сколько вакансий сгенерировать (по умолчанию 6) |
| `--resumes M` | сколько резюме на каждую вакансию (по умолчанию 20) |
| `--seed 42` | seed ГПСЧ — фиксирует датасет для воспроизводимости |
| `--clear` | удалить старую синтетику (`_synthetic: True`) и **все** скоринги `hh_scores`, затем сгенерить заново |

> 💡 Коллекции БД `gb_parse`: `hh` (вакансии), `hh_resumes` (резюме), `hh_companies` (только парсер), `hh_scores` (результаты скоринга — Шаг 3). Синтетические и живые документы имеют одинаковую hh.ru-структуру, поэтому скорер не различает источник.

### Шаг 3. Скоринг (CLI)

**Что делает:** берёт вакансию из БД, сравнивает её с пулом резюме (по умолчанию — все из `hh_resumes`) и сохраняет ранжированный список в коллекцию `hh_scores`. Именно эти результаты затем показывает UI (Шаг 6) и отдаёт API (`GET /results`, Шаг 5).

**Формула Score:** `0.6·совпадение навыков (keyword, kw) + 0.4·косинус(TF-IDF)` — Ранг, абсолютная шкала **0–100%** (полное совпадение ~100, нерелевантное ~0, не зависит от состава пула). При равном Score выше встаёт кандидат с бóльшим опытом (сам Score при этом **не меняется**).


python -m scorer.service                          # первая вакансия из БД → топ-10, сохранение в hh_scores

python -m scorer.service <VACANCY_ID> --top 5 --limit-resumes 60

python -m scorer.service <VACANCY_ID> --json       # вывод JSON

python -m scorer.service <VACANCY_ID> --no-save    # посчитать без записи в БД

python -m tools.vacancy_skills <VACANCY_ID>        # какие навыки скорер видит в вакансии (диагностика)

# <VACANCY_ID> берём из вывода db.seed или:  docker exec mongo mongosh gb_parse --eval 'db.hh.find({},{title:1}).limit(3).toArray()'


Флаги CLI:

| Флаг | Назначение |
|---|---|
| `[VACANCY_ID]` | позиционный; без него скорится первая вакансия из БД |
| `--top N` | сколько верхних строк напечатать |
| `--limit-resumes N` | ограничить размер пула резюме (ускоряет на больших БД) |
| `--json` | вывод в JSON (для скриптов / парсинга) |
| `--no-save` | посчитать и показать, но не писать в `hh_scores` |

Пример вывода (`scorer.service <ID> --top 5 --limit-resumes 60`):
```
Вакансия: DevOps-инженер  [6a3caf75dc89bba2080b8cee]
Оценено резюме: 60

  #1  Score  54  (kw 0.79 | cos 0.18)  опыт 8 лет  DevOps-инженер
      навыки: Ansible, Apache Kafka, CI/CD, Docker, Kubernetes, PostgreSQL, ...
  #2  Score  50  (kw 0.75 | cos 0.13)  опыт 8 лет  DevOps-инженер
      ...
Results saved to collection 'hh_scores' in db 'gb_parse'.
```

### Шаг 4. Тесты и метрики качества

**Что проверяют:** четыре уровня проверки — от корректности самого алгоритма до сквозного пайплайна и HTTP-слоя. Первые три опираются на **синтетику с известным ground-truth** (релевантность кандидата задаётся процедурой генерации скилов), четвёртый — герметичный тест API без БД.


python tests/test_smoke.py        # корректность скорера (релевантный ~78, нерелевантный 0)

python tests/eval_synthetic.py    # nDCG/Spearman (бар качества 0.8)

python tests/integration_demo.py  # end-to-end: БД → скорер → БД + реальная вакансия hh.ru

pytest tests/test_api.py -q       # герметичный тест FastAPI (без MongoDB)

pytest                            # всё сразу


| Команда | Что проверяет | Ожидаемый результат |
|---|---|---|
| `test_smoke.py` | корректность скорера на ручных фикстурах: релевантное ~78, бухгалтер 0, порядок в пуле | `ALL SMOKE TESTS PASSED` |
| `eval_synthetic.py` | качество ранжирования vs ground-truth: nDCG@10, Spearman, корреляция компонент | nDCG@10 ≈ **0.996**, `PASS` (бар 0.8) |
| `integration_demo.py` | сквозной прогон БД→скорер→БД + скоринг реальной вакансии hh.ru | Spearman **+0.998**, `PASSED` |
| `test_api.py` | FastAPI: статус-коды, валидация запросов, маппинг эндпоинтов (без Mongo) | **12 passed** |
| `pytest` (всё) | запускает все тесты разом | **16 passed** |

> ⚠️ **Оговорка для защиты:** высокие метрики получены на **контролируемой синтетике** (ground-truth задаётся генерацией, текст резюме — зашумлённое наблюдение), а не на реальных наймах. Они доказывают корректность алгоритма и работоспособность пайплайна оценки, но **не** продакшен-точность — на боевых hh.ru данных цифры будут скромнее. Полное обоснование — в разделе «Синтетические данные + метрики качества».

### Шаг 5. FastAPI backend — отдельный терминал (работает постоянно)

> 🖥️ **Откройте НОВЫЙ терминал**, активируйте окружение и запустите сервер:

conda activate candidate_scoring

python -m api                    # → http://127.0.0.1:8000  (Swagger-доки: /docs)

# эквивалент:  uvicorn api.main:app --reload

Проверка в любом терминале, пока сервер работает:

curl -s localhost:8000/health

VID=$(curl -s 'localhost:8000/vacancies?limit=1' | python -c 'import sys,json;print(json.load(sys.stdin)[0]["_id"])')

curl -s -XPOST localhost:8000/score -H 'Content-Type: application/json' -d "{\"vacancy_id\":\"$VID\",\"limit_resumes\":20}"

curl -s "localhost:8000/results/$VID?top=5"


### Шаг 6. Streamlit UI — отдельный терминал (работает постоянно)

> 🖥️ **Откройте ЕЩЁ ОДИН новый терминал**, активируйте окружение и запустите UI:

conda activate candidate_scoring

streamlit run ui/app.py          # → http://localhost:8501

В браузере: выбор вакансии → «Рассчитать скоринг» → таблица (Score / Опыт / навыки / ранг) → клик по кандидату → подсветка навыков + фидбек **Релевантен / Нерелевантен**.

### Шаг 7. (опционально) Перегенерация онтологии и референс-корпуса

**Когда нужно:** только если вы правите исходный корпус навыков `data/skills_by_profession.json` (источник и синтетики, и метрик). По умолчанию оба артефакта уже лежат в репо — шаг можно пропустить.

**Что пересобирается** (два артефакта, от которых зависит скорер):

| Артефакт | Файлы | Зачем нужен |
|---|---|---|
| Авто-онтология навыков | `scorer/skills_auto.json`, `scorer/skills_auto_raw.json` | Скорер ищет «найденные навыки» по словарю. Ручной словарь (`skills_dict.py`, ~60 навыков) узнаёт лишь ~43% реальных тегов hh.ru; этот артефакт автоматически расширяет словарь из корпуса до покрытия **~97%**. |
| Референс-корпус TF-IDF | `scorer/reference_corpus.py` | IDF (редкость термина) обучается **один раз** на фикс. наборе текстов, поэтому косинус/Score пары (вакансия, резюме) **не зависит от состава пула** — именно это делает Score «абсолютной мерой», а не пересчётом под каждый пул. |

**Три команды по порядку** (чистка → онтология → корпус):


python -m tools.clean_profession_skills    # 1) почистить исходный корпус: дедуп тегов, убрать «чужие» навыки, нормализовать JSON (идемпотентно, писать в data/skills_by_profession.json)

python -m tools.build_ontology             # 2) собрать из корпуса авто-словарь навыков → scorer/skills_auto*.json

python -m tools.build_reference_corpus     # 3) пересобрать фикс. корпус для стабильного IDF → scorer/reference_corpus.py


После пересборки имеет смысл прогнать метрику и убедиться, что качество не упало:

python tests/eval_synthetic.py             # ждём nDCG@10 ≈ 0.99, иначе корпус/онтология правятся некорректно


> ⚠️ Все три файла (`skills_auto*.json`, `reference_corpus.py`) — **автогенерируемые**: не правьте их руками, только пересобирайте этими командами.

### Раскладка по терминалам

| Терминал | Команда | Что делает |
|---|---|---|
| #1 (разовый) | `docker start mongo` | поднимает MongoDB, после чего терминал свободен |
| #2 (сервер) | `python -m api` | держит FastAPI на `:8000` |
| #3 (сервер) | `streamlit run ui/app.py` | держит UI на `:8501` |
| рабочий | `db.seed`, `scorer.service`, тесты, `tools.*` | разовые команды |

**Останов:** серверы — `Ctrl+C` в их терминалах; БД — `docker stop mongo`.

**TL;DR (минимум для демо):** если **Шаг 0** (окружение + зависимости) уже выполнен, этих четырёх команд в одном терминале достаточно, чтобы поднять рабочее демо от нуля.

docker start mongo && python -m db.seed      # 1) поднять MongoDB и наполнить её синтетикой (вакансии + резюме)

python -m scorer.service --top 10            # 2) скоринг первой вакансии → результаты в коллекции hh_scores

python -m api &                              # 3) FastAPI в фоне  →  http://127.0.0.1:8000  (Swagger: /docs)

streamlit run ui/app.py                      # 4) интерфейс       →  http://localhost:8501

Откройте **http://localhost:8501** → выберите вакансию → «Рассчитать скоринг» → таблица с подсветкой навыков и кнопками фидбека. FastAPI параллельно отвечает на `:8000`.

**Останов этого варианта (один терминал):** `Ctrl+C` (остановит Streamlit) → `kill %1` (фоновой API) → `docker stop mongo` (БД).

---

## Статус реализации

| Компонент | Статус                                     |
|---|--------------------------------------------|
| Парсер hh.ru → MongoDB (Scrapy) | ✅ Реализован                               |
| Гибридный скорер `calculate_score` / `rank_candidates` | ✅ Реализован                               |
| Слой БД + интеграция парсер→скорер (`scorer/service.py`) | ✅ Реализован                               |
| Генератор синтетики с разметкой + метрики (nDCG/precision/spearman) | ✅ Реализован                               |
| Схема БД (вакансии / резюме / скоринги) | ✅ Реализована                              |
| Streamlit UI (таблица + подсветка навыков + фидбек) | ✅ Реализован                               |
| FastAPI backend | ✅ Реализован                               |
| "Тонкий" агент-оркестратор (явные интенты) | 📋 Запланировано согласование с Заказчиком |


---

## О проекте

Ручной просмотр сотен резюме — трудоёмкий процесс. Сервис автоматизирует первичный отбор: «читает» текст резюме, выделяет ключевые навыки и сравнивает их с требованиями вакансии, выдавая ранжированный список кандидатов. Бизнес-ценность — экономия времени рекрутера.

**Форма выполнения:** групповая (3–4 человека). **Срок:** 15 недель.

---

## Архитектура

```text
[ Пользователь — UI Streamlit: таблица «ФИО | Score | навыки» + подсветка ]
        │  (явные действия/интенты, без хрупкого NL-парсера)
        ▼
┌─────────────────────────────────────────────────────────────┐
│                 "Тонкий" агент-оркестратор                    │   [Запланировано согласование с Заказчиком]
│   детерминированно вызывает инструменты по выбранному действию │
└─────────────────────────────────────────────────────────────┘
        │
        ├──► [ Tool: Parser (Scrapy) ]   ✅ асинхронно (DOWNLOAD_DELAY=1.5)
        ├──► [ Tool: Scorer ]             ✅ синхронно (TF-IDF быстрый)
        ├──► [ Tool: Database (MongoDB) ] ✅ vacancies / resumes / scores
        └──► [ Tool: Feedback store ]     📋 Да/Нет

[ FastAPI ]  ✅  POST эндпоинты: загрузка вакансии/резюме, запуск скоринга, результаты, фидбек
[ MongoDB ]  ✅  коллекции hh / hh_resumes / hh_scores (db gb_parse)
```

**Ключевые архитектурные решения**:

1. **NLP** Все тексты русские; используется нативный русский NLP (`pymorphy3` + `razdel` + встроенный русский стоп-список). Перевод вредит точности и добавляет латентность.
2. **Гибридный скорер** (а не чистый cosine) — нужен, чтобы в таблице появился столбец «Найденные ключевые навыки».
3. **Score — абсолютная мера**, а не percentile-rank: полностью совпадающее резюме набирает ~100%, нерелевантное ~0% — даже как единственный кандидат в пуле. `rank_percentile` (позиция в пачке) — отдельное поле для бейджа «топ-10%». Это снимает проблему «100% за разные тексты» (требование «Показа 3»). Чтобы score действительно не зависел от состава пула, TF-IDF обучается один раз на фиксированном референс-корпусе (`scorer/reference_corpus.py`), а не пересчитывается под каждый пул — поэтому косинус одной и той же пары (вакансия, резюме) одинаков в `calculate_score` и `rank_candidates`.
4. **Celery — только под краулер** (roadmap). Скоринг синхронный (TF-IDF укладывается в секунды при лимите «30 мин / 100 резюме»).
5. **Явные интенты в UI**, а не rule-based распознавание свободного текста — надёжность на демо и защите.

---

## Стек

- **Парсинг:** Scrapy ≥ 2.8
- **БД:** MongoDB 8.x (`pymongo` ≥ 4.0), Docker
- **NLP/скоринг:** `scikit-learn` (TF-IDF + cosine), `pymorphy3` (лемматизация RU), `razdel` (токенизация), встроенный русский стоп-список (`scorer/stopwords_ru.py`)
- **Онтология навыков:** курируемый словарь (`scorer/skills_dict.py`, ~60 навыков с RU/EN-алиасами) + авто-расширение из корпуса профессий (`scorer/skills_auto*.json`, генерируется `tools/build_ontology.py`) — покрытие ~97%
- **Данные:** `Faker` (ru_RU) — синтетика с зашумлением
- **UI:** Streamlit (`ui/`) — таблица + подсветка навыков + фидбек
- **Backend:** FastAPI (`api/`) — тонкий HTTP-слой над `db.mongo` и `scorer.service` (uvicorn)

---

## Структура репозитория

```text
AI_CANDIDATE_SCORING_SYSTEM/
├── Parser/                  # [Реализовано] Scrapy-парсер hh.ru
│   ├── config/config.json   # что парсить + start_urls
│   ├── gb_parse/            # spider, items, loaders, pipelines, settings
│   └── main.py
├── scorer/                  # [Реализовано] гибридный скорер
│   ├── normalize.py         # razdel + pymorphy3, стоп-слова
│   ├── skills.py            # извлечение/сопоставление навыков (онтология)
│   ├── skills_dict.py       # курируемая онтология + автозагрузка skills_auto*.json
│   ├── skills_auto.json     # авто-онтология из корпуса (gen: tools/build_ontology.py)
│   ├── skills_auto_raw.json # символьные навыки (C++/.NET/…)
│   ├── similarity.py        # TF-IDF (фикс. референс-IDF) + cosine
│   ├── reference_corpus.py  # референс-корпус для стабильного IDF (gen: tools/build_reference_corpus.py)
│   ├── scoring.py           # calculate_score + rank_candidates
│   ├── service.py           # связка с MongoDB + CLI (python -m scorer.service)
│   ├── metrics.py           # nDCG / precision@k / spearman
│   ├── stopwords_ru.py      # встроенный русский стоп-список
│   └── requirements.txt
├── data/                    # [Реализовано] синтетика с ground-truth
│   ├── profiles.py          # 5 ролей (стеки + шаблоны)
│   └── synthetic.py         # контролируемое внедрение навыков → relevance
├── db/                      # [Реализовано] слой MongoDB
│   ├── mongo.py             # CRUD: вакансии/резюме/scores (upsert)
│   ├── builders.py          # hh item → текст для скорера
│   └── seed.py              # синтетика в hh-формате + CLI (python -m db.seed)
├── tests/                   # [Реализовано]
│   ├── test_smoke.py        # smoke скорера
│   ├── eval_synthetic.py    # метрика качества (nDCG)
│   └── integration_demo.py  # end-to-end БД → скорер → БД
├── ui/                      # [Реализовано] Streamlit
│   ├── app.py               # выбор вакансии → таблица → детали + фидбек
│   └── highlight.py         # безопасная подсветка навыков (HTML-escape)
├── tools/                   # [Реализовано] утилиты сопровождения
│   ├── clean_profession_skills.py  # валидация/чистка корпуса профессий
│   ├── build_ontology.py    # авто-генерация онтологии из корпуса
│   ├── build_reference_corpus.py  # референс-корпус для стабильного TF-IDF
│   └── vacancy_skills.py    # CLI: какие навыки скорер видит в вакансии hh.ru
├── agent/                   # [Запланировано] тонкий оркестратор
├── api/                     # [Реализовано] FastAPI — HTTP-слой над db.mongo и scorer.service
│   ├── schemas.py           # pydantic-модели запросов (VacancyIn/ResumeIn/ScoreRequest/FeedbackIn)
│   ├── routes.py            # эндпоинты-обёртки (health, vacancies, candidates, score, results, feedback)
│   ├── main.py              # FastAPI-приложение (CORS, pymongo→503, /docs)
│   ├── __main__.py          # python -m api → uvicorn
│   └── requirements.txt     # fastapi, uvicorn
├── README.md
├── T1_1_…_скоринга_кандидатов….docx   # ТЗ
└── Кейсы для НГУ.docx                 # вопросы/ответы заказчика
```

---

## [Реализовано] Сбор данных — парсер hh.ru

Scrapy-паук собирает **вакансии**, **компании** и **резюме** с [hh.ru](https://hh.ru) и сохраняет их в MongoDB.

### Возможности
- Вакансии: `title`, `salary`, `description`, `skills`, `author_url`, `author_name`, `tags`
- Компании: `title`, `description`, `site`, `external_id`
- Резюме: `title`, `salary`, `specialization`, `age`, `gender`, `address`, `experience`, `skills`, `languages`, `relocation`, `tags`
- Авто-пагинация по результатам поиска; тип поиска определяется по URL (`/search/resume` → резюме, иначе → вакансии)

### Запуск

cd Parser && pip install -r requirements.txt

docker start mongo                                   # MongoDB

python Parser/main.py                                       # или: scrapy crawl hh

# быстрый тест без Mongo:

scrapy crawl hh -s CLOSESPIDER_PAGECOUNT=8 -s ITEM_PIPELINES={} -O out.json


### Конфигурация — `Parser/config/config.json`
| Поле | По умолчанию | Описание |
|---|---|---|
| `vacancy_parsing` | `true` | ходить на страницы вакансий |
| `company_parsing` | `true` | собирать компании |
| `resume_parsing` | `true` | собирать резюме |
| `start_urls` | — | список поисковых URL hh.ru |

Настройки Scrapy — `Parser/gb_parse/settings.py`: `MONGO_URI=mongodb://localhost:27017`, `MONGO_DB=gb_parse`, `DOWNLOAD_DELAY=1.5`, `CONCURRENT_REQUESTS=32`.

### Важное ограничение парсера
hh.ru **скрывает резюме** (имя и теги навыков) за входом работодателя. На момент написания в БД: **19 реальных вакансий** из hh.ru и **0 резюме** (за логином). Поэтому для скоринга резюме сидируются синтетикой (см. ниже), а скоринг опирается на поля `experience`/`description`. Живой краулер резюме пишется в ту же коллекцию `hh_resumes` — при появлении employer-логина ничего менять не нужно.

---

## [Реализовано] Скорер

Гибридный алгоритм `calculate_score` / `rank_candidates` (`scorer/`).

1. **Нормализация текста** (`normalize.py`). Lowercase → токенизация `razdel` → лемматизация `pymorphy3` (с `lru_cache`) → удаление русских стоп-слов (встроенный список).
2. **Онтология навыков** (`skills_dict.py` + `skills_auto*.json`). Курируемый словарь IT-навыков с алиасами RU/EN (например `Python↔питон`, `Machine Learning↔машинное обучение`) + symbol-skills (`C++`, `.NET`, `CI/CD`), автоматически расширенный из корпуса профессий (`tools/build_ontology.py`) до покрытия ~97% реальных тегов hh.ru. Словарей заказчик не предоставляет — онтология собирается нами.
3. **Сопоставление навыков** (`skills.py`). `matched_skills = skills(vacancy) ∩ skills(resume)` (матч по леммам + raw-substring для символов) → столбец «Найденные ключевые навыки».
4. **Сходство текстов** (`similarity.py`). TF-IDF (uni+bi-grams, `sublinear_tf`) по лемматизированным текстам → `cosine ∈ [0, 1]`.
5. **Итоговый Score (0–100%)** (`scoring.py`):
   - `raw = 0.6·keyword_score + 0.4·cosine_sim`
   - `Score(%) = round(raw · 100)` — **абсолютная** мера; `rank_percentile` — позиция в пачке (отдельное поле).
6. **Тайм-брейк по опыту** (`scorer/service.py`). При равном `Score` кандидаты доупорядочиваются по **годам опыта**: больше опыта → выше в выдаче. Годы извлекает `db.builders.experience_years` (regex `Опыт работы: N лет|год|года` из поля `experience`; обобщение `Parser/extract_years_of_experience.py` на живой MongoDB-пайплайн). **Сам `Score` не меняется** — он остаётся абсолютной мерой по п. 3; меняется лишь порядок внутри группы одинакового скора. Резюме без распознанных лет идут последними в своей группе.
   - Направление по умолчанию — «больше опыта впереди». Для вакансий, где важнее младшие, направление переворачивается одним полем в сортировке `scorer/service.py`.
   - ⚠️ Годы извлекаются регуляркой из текста по ключу `experience` (так пишет синтетика `data/profiles.py` и поле hh.ru). Структурный `experience` hh.ru (список периодов должностей) в суммарные годы пока не сворачивается — при появлении таких данных экстрактор надо будет усилить.

### Использование
```python
from scorer import calculate_score, rank_candidates
calculate_score(resume_text, vacancy_text)
# {"score": 73, "matched_skills": ["Python", "PostgreSQL", ...], "missing_skills": [...], ...}
rank_candidates(vacancy_text, [r1, r2, r3])   # отсортировано по score, с rank_percentile
```

### Smoke-тест (`tests/test_smoke.py`)
Релевантный Python-разработчик → **73**, frontend-частичный → **13**, бухгалтер → **0** (нерелевантным не даётся ~100%).

### Explainability
Подсветка `matched_skills` в тексте резюме — единственный требуемый уровень интерпретируемости (LLM-объяснения и детализация решения заказчику **не нужны**).

### Anti-bias
Собираемый для скоринга текст (`db/builders.py`) **не включает** поля `age`, `gender`, `address` — они изолированы от признаков на уровне сборки. Заказчик зачистку персональных данных не требует (учебный проект). Ограничение, которое стоит держать в уме: имя кандидата и упоминания в свободном тексте опыта (ВУЗ и т.п.) всё же попадают в TF-IDF-вектор косинус-канала; на синтетике это с релевантностью не коррелирует, но как продуктовый риск (прокси-bias по полу/возрасту) он не закрыт полностью.

---

## [Реализовано] Синтетические данные + метрики качества

Заказчик реальные резюме предоставить не может (152-ФЗ) — датасет генерируется сам (`data/`). Метод: **контролируемое внедрение навыков** — для вакансии создаются резюме с заданной долей совпадения `overlap ∈ [0,1]`, которая и становится graded ground-truth relevance (что кандидат *знает*); в текст резюме навыки попадают с реалистичным шумом (часть пропускается, добавляются посторонние) — скорер должен восстановить ранг из зашумлённого наблюдения. 4 роли (Python-разработчик, Data Scientist, Frontend, DevOps) с реалистичным перекрытием стека.

Метрики (`scorer/metrics.py`): `ndcg` (graded linear gain), `precision_at_k`, `spearman`. Оценка (`tests/eval_synthetic.py`):

```
Mean nDCG@10 = 0.996    Spearman = 0.972
Корреляция компонент с true relevance: keyword +0.985, cosine +0.915, combined +0.985
Интеграционный прогон (БД → скорер → БД, tests/integration_demo.py): Spearman = +0.998
```

> ⚠️ **Оговорка для защиты.** Это **контролируемые синтетические данные**, а не реальные наймы: ground-truth relevance задаётся процедурой генерации, а текст резюме — зашумлённое наблюдение (часть известных навыков не написана, добавлены посторонние). Высокие цифры означают, что скорер уверенно восстанавливает истинный ранг из шумного текста, и доказывают корректность алгоритма + работоспособность пайплайна оценки — но **не** продакшен-точность. Реальных лейблов нет (152-ФЗ), на боевых hh.ru данных цифры будут скромнее; для защиты проговаривать именно это.

---

## [Реализовано] Интеграция: БД + сервис скоринга

`scorer/service.py` связывает парсер и скорер через MongoDB:

```python
from scorer.service import score_vacancy
out = score_vacancy(vacancy_id)          # тянет вакансию + резюме из Mongo, скорит, сохраняет
for r in out["results"]: print(r["score"], r["matched_skills"])
```

CLI:

python -m scorer.service [VACANCY_ID] [--top N] [--limit-resumes N] [--no-save] [--json]

python -m db.seed [--vacancies N] [--resumes M] [--clear]


### Коллекции MongoDB (db `gb_parse`)
- `hh` — вакансии (формат hh.ru item)
- `hh_resumes` — резюме (формат hh.ru item; синтетические помечены `_synthetic`, `_target_vacancy_url`, `_true_relevance`)
- `hh_scores` — результаты: `vacancy_id, resume_id, score, raw_score, keyword_score, cosine_sim, matched_skills[], missing_skills[], rank_percentile, experience_years, created_at, updated_at` (upsert по `vacancy_id+resume_id`)

> ⚠️ **Где искать `hh_scores`.** `hh_scores` — это **коллекция внутри БД `gb_parse`**, а не отдельная база и не файл. Поэтому команда `show dbs` её не покажет (там только `admin`, `config`, `gb_parse`, `local`) — нужно зайти внутрь `gb_parse`. Коллекций там четыре: `hh`, `hh_resumes`, `hh_companies`, `hh_scores`.

#### Как посмотреть сохранённые результаты

# 1) mongosh из контейнера (docker start mongo) — топ-10 по конкретной вакансии:
docker exec -it mongo mongosh gb_parse \
  --eval 'db.hh_scores.find({vacancy_id: "6a3caf75dc89bba2080b8cee"}).sort({score:-1}).limit(10).pretty()'

# интерактивно: показать все коллекции и посчитать результаты
docker exec -it mongo mongosh gb_parse
> show collections
> db.hh_scores.countDocuments()
> db.hh_scores.distinct("vacancy_id")          # по каким вакансиям есть скоринги
> db.hh_scores.find().sort({score:-1}).limit(5)

```python
# 2) через слой доступа проекта:
from db import mongo
for r in mongo.get_scores("6a3caf75dc89bba2080b8cee", top=10):
    print(r["score"], r["keyword_score"], r["matched_skills"][:5])
```
```
# 3) MongoDB Compass: подключиться к mongodb://localhost:27017 → БД gb_parse → коллекция hh_scores
```

### Демо (`tests/integration_demo.py`)
End-to-end на реальных данных: скоринг синтетической вакансии (ground-truth пул, Spearman ≈ 0.98, scores сохранены) + скоринг **реальной вакансии hh.ru** против пула.

---

## [Реализовано] FastAPI backend

Тонкий HTTP-слой (`api/`) над готовыми функциями `db.mongo` и `scorer.service.score_vacancy` — без дублирования логики скоринга/БД.


pip install -r api/requirements.txt          # fastapi, uvicorn

python -m api                                 # http://127.0.0.1:8000  (OpenAPI-доки: /docs)

# или:  uvicorn api.main:app --reload


| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/health` | пинг БД → `{status, db}`; если Mongo недоступна — `503` |
| `GET` | `/vacancies?limit=N` | список вакансий |
| `GET` | `/vacancies/{id}` | одна вакансия (`404`, если нет / неверный ObjectId) |
| `POST` | `/vacancies` | загрузить вакансию (hh-shape) → `201 {_id, …}` |
| `GET` | `/resumes/{id}` | резюме (текст для подсветки навыков в UI) |
| `POST` | `/candidates` | загрузить резюме → `201` |
| `POST` | `/score` | запуск скоринга `{vacancy_id, resume_ids?, limit_resumes?, weights?}` → `{count, results[]}` |
| `GET` | `/results/{vacancy_id}?top=N` | ранжированные результаты из `hh_scores` |
| `POST` | `/feedback` | решение HR `{vacancy_id, resume_id, decision: yes\|no}` |


VID=$(curl -s 'localhost:8000/vacancies?limit=1' | python -c 'import sys,json;print(json.load(sys.stdin)[0]["_id"])')

curl -s -XPOST localhost:8000/score -H 'Content-Type: application/json' \
 -d "{\"vacancy_id\":\"$VID\",\"limit_resumes\":20}"

curl -s "localhost:8000/results/$VID?top=5"


**Решения слоя:**
- **Тонкая обёртка:** эндпоинты только маппят HTTP↔функции; скоринг и доступ к БД не дублируются.
- **Обработка ошибок:** not-found / неверный ObjectId → `404`; упавшая БД (pymongo) → `503` (глобальный хендлер, без «голых» `500`); валидация тела — pydantic (`422`).
- **CORS** через env `API_CORS_ORIGINS` (по умолчанию `*`): Streamlit (:8501) и API (:8000) на разных портах.
- **Поле идентификатора:** `/score` возвращает `candidate_id` (вывод скорера), `/results` — документы `hh_scores` с полем `resume_id`; оба равны `_id` резюме.
- **Герметичный тест без БД:** `pytest tests/test_api.py` (TestClient + заглушки `db.mongo`/`score_vacancy`).

> **Streamlit UI** (`ui/`) уже реализован (см. таблицу статуса) и ходит в БД напрямую — это осознанный MVP. Перевод UI на обращения к FastAPI — отдельная задача (агент-оркестратор, roadmap).

---

## [Запланировано] Тонкий агент-оркестратор (СОГЛАСОВАТЬ С ЗАКАЗЧИКОМ)

Поверх FastAPI — детерминированный оркестратор: по выбранному в UI действию (явный интент) вызывает нужный инструмент (parser / scorer / DB / feedback). Без хрупкого NL-парсера свободного текста — надёжность на демо важнее «вау-эффекта» чат-бота.

---

## Соответствие ТЗ (Milestones)

| Показ | Срок | Требование | Покрытие |
|---|---|---|---|
| 1 | Нед. 3 | Концепция, схема БД, синтетика 50–100 шт. | 🔨 (схема ✅, синтетика ✅) |
| 2 | Нед. 6 | Парсинг + БД (загрузка, извлечение текста) | ✅ |
| 3 | Нед. 9 | Алгоритм скоринга (демо сходства) | ✅ |
| 4 | Нед. 12 | MVP: UI + алгоритм | ✅ (алгоритм ✅, UI ✅) |

---

## Ключевые ограничения (из ответов заказчика)

| Параметр | Значение |
|---|---|
| Объём | 10 вакансий / 200 резюме в час |
| Время | ≤ 2 мин на резюме, ≤ 30 мин на пачку из 100 |
| Типы вакансий | ≤ 20 |
| Обратная связь | Да/Нет по решению системы |
| OCR | не требуется (выгрузка hh.ru машиночитаема) |
| Интеграция с HR-системами | нет (учебный проект) |
| Очистка персональных данных | не требуется |
| Uptime | 95 % |

---

## Дорожная карта

1. ~~Парсер hh.ru → MongoDB~~ ✅
2. ~~Схема MongoDB + слой доступа (`db/`)~~ ✅
3. ~~Генератор синтетики с разметкой + метрики (nDCG)~~ ✅
4. ~~Гибридный `calculate_score` (keyword + TF-IDF)~~ ✅
5. ~~Интеграция парсер → скорер (`scorer/service.py`)~~ ✅
6. ~~Streamlit UI: таблица + подсветка + фидбек~~ ✅
7. ~~Расширение онтологии из корпуса профессий (покрытие ~97%)~~ ✅
8. ~~FastAPI-эндпоинты~~ ✅
9. "Тонкий" агент-оркестратор (явные интенты) - СОГЛАСОВАТЬ С ЗАКАЗЧИКОМ
10. Тестирование на разных вакансиях, финальная презентация

---

# TO DO:
## Команда

- **Data Engineer/Analyst** — синтетические данные, критерии/веса навыков
- **Backend Developer** — API, БД, логика сравнения текстов
- **Fullstack/Frontend** — Streamlit-интерфейс
- **Team Lead** — планирование спринтов, сроки, документация
