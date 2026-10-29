# RUNBOOK — работа с репозиторием в терминале

Карманный справочник: как поднять окружение, прогнать тесты и бенчмарк,
запустить API с MongoDB и посчитать скоринг. Все команды выполняются из
корня репозитория, если не сказано иное.

```
ai-scoring-system-main/
├── api/        FastAPI-сервис + NLP-парсер (nlp_parser.py: навыки, опыт)
├── scorer/     ядро скоринга: извлечение навыков, семьи, матчинг, метрики
├── db/         MongoDB-доступ, сборка текстов вакансий/резюме
├── data/       РЕАЛЬНЫЕ данные: superjob_dataset.json (101 вакансия),
│               dataset_resume.json (100 резюме), ground_truth_*.csv
├── scripts/    бенчмарки и аудит (benchmark_real_data.py — основной)
├── tests/      pytest-тесты + eval_synthetic.py (регрессия ранжирования)
└── frontend/   React UI
```

---

## 1. Окружение (один раз)

```bash
# Python 3.10+
conda create -n candidate_scoring python=3.10 -y
conda activate candidate_scoring

# зависимости (порядок важен: корневой файл частично дублирует остальные)
pip install -r requirements.txt
pip install -r scorer/requirements.txt   # + scipy для метрик (spearman)
pip install -r api/requirements.txt
pip install -r tests/requirements.txt
```

Быстрая проверка, что всё встало:

```bash
python -c "from scorer import rank_candidates; print('scorer OK')"
python -c "from api.nlp_parser import extract_experience_years; print('parser OK')"
```

> `sentence-transformers`/`spacy` тянут тяжёлые веса — ставятся долго.
> Для скоринга и парсинга опыта они НЕ нужны (эмбеддер в nlp_parser.py
> загружается лениво и сейчас не используется).

---

## 2. Тесты

```bash
pytest                                            # весь набор (~89 тестов, ~2 c)
pytest tests/test_experience.py -q                # только парсинг опыта
pytest tests/test_matching_families.py -q         # семьи навыков
pytest tests/test_similarity.py -q                # косинус
pytest tests/test_smoke.py -q                     # сквозной smoke скорера

python tests/test_smoke.py                        # те же тесты standalone
python tests/eval_synthetic.py                    # регрессия ранжирования
                                                  # (nDCG@10 >= 0.8 = PASS)
```

`tests/integration_demo.py` требует запущенной MongoDB с данными — п. 4–5.

---

## 3. Бенчмарк на реальных данных (без синтетики и Parser/)

```bash
python scripts/benchmark_real_data.py --limit 10   # быстро: первые 10 вакансий
python scripts/benchmark_real_data.py --limit 0    # все вакансии (~70 c)
python scripts/benchmark_real_data.py --threshold 0.3   # другой порог релевантности P@k/R@k
```

Печатает 4 блока: извлечение навыков (P/R/F1, с разбивкой rich-json /
pdf_assembled), ранжирование (nDCG@10, P@5/P@10, R@10/R@50, Spearman),
распределение Score, покрытие парсинга опыта. R@k и «P@10 по тем же»
считаются только по вакансиям, у которых в пуле есть хоть один релевантный
кандидат; R@50 — полнота с широким окном (при низких порогах R@10 упирается
в потолок 10/n_rel). Это основной инструмент проверки «не сломал ли я скорер».

> Старые `scripts/benchmark.py`, `benchmark_resumes.py`, `audit_resumes.py`,
> `error_analysis.py` смотрят на несуществующие пути `scripts/exel/*/pdf` —
> не используйте их, пока пути не поправлены (см. CODE_REVIEW.md §3).

---

## 4. Запуск стека

### Вариант A — всё в Docker (проще всего)

```bash
docker compose up --build -d        # mongo + backend + frontend
docker compose logs -f backend      # логи API
curl http://localhost:8000/health   # {"status":"ok", ...}
# UI:      http://localhost:3000
# Swagger: http://localhost:8000/docs
docker compose down --remove-orphans        # остановить (данные в volume останутся)
docker compose down -v                      # остановить И стереть базу
```

### Вариант B — локальный API + MongoDB из Docker

```bash
docker compose up -d mongo                    # только база
export MONGO_URI=mongodb://localhost:27017   # ВАЖНО: без этого код
                                              # смотрит на mongodb://mongo:27017
uvicorn api.main:app --reload --port 8000    # из корня репозитория
```

> Без `MONGO_URI` локальный процесс ищет хост `mongo` (docker-имя сервиса) и
> падает по таймауту подключения.

### Фронтенд отдельно (режим разработки)

```bash
cd frontend && npm install && npm start      # React dev-сервер, порт 3000  - bug!
fix bug:
rm -rf node_modules          # drop the half-extracted packages
  npm install                  # npm ci refused: lockfile out of sync → npm install reconciles it
  npm run build                # verification: full webpack build ✅
  npm start                    # verification: dev server up in ~5s, serves «Скоринг резюме» ✅


If this ever recurs after an interrupted install, the recipe is the same: rm -rf node_modules && npm install.
```

---

## 5. Данные и скоринг

### Импорт реального датасета SuperJob в базу (после запуска API)

```bash
curl -X POST http://localhost:8000/import_superjob_vacancies
curl -X POST http://localhost:8000/import_superjob_resumes
```

Эндпоинты читают `data/superjob_dataset.json` и `data/dataset_resume.json`
относительно cwd — запускайте uvicorn из корня репозитория.

### Обновление корпуса (новые assembled-данные от команды разметки)

```bash
cp data/ground_truth_resumes_assembled.csv data/ground_truth_resumes.csv
cp data/ground_truth_vacancies_assembled.csv data/ground_truth_vacancies.csv
python scripts/extend_datasets_from_assembled.py --dry-run  # отчёт о изменениях
python scripts/extend_datasets_from_assembled.py            # применить
```

Скрипт дедуплицирует JSON-датасеты (ревизии разметки) и добавляет записи для
новых id: текст из PDF + `expected_skills` из CSV. Идемпотентен.

### Скоринг через CLI (без API)

```bash
python -m scorer.service                       # первая вакансия в базе, топ-10
python -m scorer.service <vacancy_id> --top 20 --json
python -m scorer.service <vacancy_id> --critical-skills "SQL" "Python"
python -m scorer.service <vacancy_id> --no-save    # не писать в hh_scores
```

### Скоринг через API

```bash
curl -X POST http://localhost:8000/score \
     -H 'Content-Type: application/json' \
     -d '{"vacancy_id": "<id>"}'

curl http://localhost:8000/results/<vacancy_id>       # сохранённый рейтинг
```

### Загрузка своих файлов (PDF/TXT)

```bash
curl -F "file=@resume.pdf" http://localhost:8000/upload_resume
curl -F "file=@vacancy.pdf" http://localhost:8000/upload_vacancy
```

### Полезные операции с базой

```bash
curl -X DELETE http://localhost:8000/resumes/clear    # очистить резюме + скоры
curl -X DELETE http://localhost:8000/vacancies/clear  # очистить вакансии
curl http://localhost:8000/vacancies                  # список вакансий
```

---

## 6. Частые проблемы

| Симптом | Причина и решение |
|---|---|
| `ModuleNotFoundError: fitz` | Не поставлен PyMuPDF: `pip install pymupdf` |
| `ModuleNotFoundError: faker` при `import api...` | `pip install faker` (нужен `data/synthetic.py`) |
| API виснет, `ServerSelectionTimeoutError` | Локальный запуск без `MONGO_URI=mongodb://localhost:27017` |
| `scorer` падает на `scipy` | `pip install scipy` |
| Бенчмарк/тесты медленные (>минуты) | Проверьте, что не запустили старые `scripts/benchmark*.py` с битыми путями; актуальный — `benchmark_real_data.py` |
| В контейнере нет `data/*.json` | Запускайте uvicorn/композицию из корня репозитория |
| Разные имена навыков между запусками | Так было до фикса дедупликации регистра; обновитесь на текущий `scorer/skill_extractor.py` |

---

## 7. Минимальный чек-лист «я ничего не сломал»

```bash
pytest                                              # 89 passed
python tests/eval_synthetic.py                      # nDCG@10 >= 0.8, PASS
python scripts/benchmark_real_data.py --limit 0     # метрики на реальных данных
```

Ожидаемые ориентиры на расширенном корпусе (194 резюме / 111 вакансий,
см. CODE_REVIEW.md и data/README.md): nDCG@10 ≈ 0.83, Spearman ≈ 0.67,
R@10 ≈ 0.63 / R@50 ≈ 0.91 (порог 0.3), извлечение F1 ≈ 0.69 (вакансии) /
0.54 (резюме; в выдаче — разбивка по источникам rich-json / pdf_assembled),
опыт распознан у ~99% резюме, ~0.5 с на вакансию.
