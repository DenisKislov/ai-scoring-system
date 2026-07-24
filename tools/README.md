# tools/ — утилиты сопровождения

Скрипты для обслуживания онтологии навыков, корпуса профессий, референс-корпуса TF-IDF и живой проверки того, какие навыки видит скорер. Не входят в рантайм скоринга — запускаются вручную при правке корпуса/онтологии.

Все запускаются как модуль из корня проекта:

```bash
python -m tools.<name>
```

## Файлы

| Файл | Что делает | Пишет/читает |
|---|---|---|
| [`clean_profession_skills.py`](clean_profession_skills.py) | Чистит и валидирует корпус профессий (in place, идемпотентно) | `data/skills_by_profession.json` |
| [`build_ontology.py`](build_ontology.py) | Строит авто-онтологию из корпуса | `scorer/skills_auto.json`, `scorer/skills_auto_raw.json` |
| [`build_reference_corpus.py`](build_reference_corpus.py) | Генерирует референс-корпус для стабильного IDF | `scorer/reference_corpus.py` |
| [`vacancy_skills.py`](vacancy_skills.py) | Live: какие навыки онтология находит в вакансии/поиске hh.ru | (только печать) |

## clean_profession_skills.py

Решает две проблемы hand-made корпуса: (1) он мог быть сохранён как **Python-literal** (одинарные кавычки) вместо валидного JSON — `json.load` падал и валил весь пайплайн; (2) списки навыков содержат точные дубли (case/whitespace-варианты) и немного мусорных тегов чужой профессии (visual-design внутри Data Scientist). Идемпотентен: принимает и JSON, и literal, пишет канонический UTF-8 JSON. Для Data Scientist удаляет кураруемый набор design-тегов (`_DS_DESIGN_NOISE`), остальные профессии не трогает (без субъективной обрезки).

## build_ontology.py

Курируемый `scorer/skills_dict.py` (~60 навыков) покрывает лишь ~43% реальных тегов hh.ru. Этот инструмент превращает корпус профессий в **авто-онтологию** и поднимает покрытие до ~97%:

- теги-с-запятыми (`"vue2, vue3, vuex"`) разбиваются;
- сурфейс-формы схлопываются по нормализованному ключу, nicest-cased становится каноном, остальные — алиасы;
- `MERGE` складывает дубли в двух написаниях (`Airflow`/`Apache Airflow`, `Kafka`/`Apache Kafka`);
- уже покрытое курируемым словарём пропускается (RU/translit-алиасы куратора всегда выигрывают);
- символ-содержащие ключи → `skills_auto_raw.json` (substring-матч), чисто буквенные → `skills_auto.json` (lemma-матч) — ровно как `scorer/skills.py` делит две стратегии. Идемпотентен.

## build_reference_corpus.py

Раньше TF-IDF обучался **на каждый вызов** по двум документам или по `[vacancy]+pool` — косинус фиксированной пары зависел от состава пула, и заявка README «Score — абсолютная мера» не выполнялась. Фикс: векторизатор обучается **один раз** (at import) на фиксированном реалистичном русском корпусе. Этот скрипт его и генерит — из того же рендерера профессий, нормализованного тем же пайплайном, что и скорер. На выходе чистый Python-лист, чтобы у `scorer` не было рантайм-зависимости от `data`/`Faker`.

## vacancy_skills.py

**URL вакансии** (одна позиция) или **URL поиск** (`/vacancies/…`, `/search/vacancy`) — покажет, какие навыки скорер извлекает, а для поиска — ещё частоту навыков по первым N вакансиям. Навыки берутся из свободного текста описания (`data-qa="vacancy-description"`), т.к. теги `key_skills` у hh.ru часто пусты, а публичный API возвращает 403 без токена.

```bash
python -m tools.vacancy_skills https://hh.ru/vacancy/132709791
python -m tools.vacancy_skills https://hh.ru/search/vacancy?text=python --max 12 --top 30
```

## Порядок регенерации артефактов

Если правите корпус профессий (`data/skills_by_profession.json`), перегенерируйте зависимые артефакты строго в этом порядке:

```bash
python -m tools.clean_profession_skills   # 1. почистить корпус
python -m tools.build_ontology            # 2. пересобрать авто-онтологию
python -m tools.build_reference_corpus    # 3. пересобрать референс-корпус TF-IDF
```

## Зависимости

`requests` (только `vacancy_skills.py`). Остальное — пакеты проекта (`scorer`, `data`).
