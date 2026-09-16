# tests/ — проверки и оценка качества

Три независимых скрипта: smoke-тест скорера, количественная оценка ранжирования на синтетике и end-to-end демо через БД. Все запускаются как обычный Python из корня проекта (`sys.path` правится внутри), `test_smoke.py` дополнительно работает под `pytest`.

| Файл | Что проверяет | Нужна MongoDB? |
|---|---|---|
| [`test_smoke.py`](test_smoke.py) | Поведение скорера на hand-made русских фикстурах | нет |
| [`test_metrics.py`](test_metrics.py) | Precision/Recall/F1 извлечения навыков, целиком и по категориям | нет |
| [`eval_synthetic.py`](eval_synthetic.py) | Качество ранжирования (nDCG/Spearman) + категорийный Precision/Recall/F1 извлечения навыков на синтетике с разметкой | нет |
| [`integration_demo.py`](integration_demo.py) | End-to-end: БД -> скорер -> БД (качество + реальная вакансия) | да |

---

## Запуск

```bash
# из корня проекта (conda env candidate_scoring)

# 1) smoke-тесты — двумя способами
python tests/test_smoke.py        # standalone: печатает RELEVANT/IRRELEVANT/RANKED + PASS
pytest tests/test_smoke.py -q     # или через pytest

# 2) unit-тесты метрик извлечения навыков (Precision/Recall/F1 по категориям)
python tests/test_metrics.py      # standalone
pytest tests/test_metrics.py -q   # или через pytest

# 3) оценка качества ранжирования + категорийный Precision/Recall/F1
python tests/eval_synthetic.py    # таблица nDCG@10/nDCG/P@5/Spearman по вакансиям + отчёт по категориям

# 4) интеграционное демо (нужен запущенный Mongo + данные)
docker start mongo
python tests/integration_demo.py
```

---

## test_smoke.py — smoke скорера

Hand-made русские вакансии/резюме, проверяющие ключевые поведения для защиты:

- **Релевантное** резюме набирает высокий скор и корректно listing-ует найденные навыки (`Python`, `PostgreSQL`, `Docker`, `FastAPI`).
- **Нерелевантное** (бухгалтер) набирает **низкий** скор — guard «Показа 3»: совершенно чужой текст никогда не получает ~100%.
- `rank_candidates` ставит релевантное первым, нерелевантное последним; у топа `rank_percentile == 100`.

Не требует БД — работает с чистым API скорера. Под `pytest` и standalone.

## eval_synthetic.py — метрики качества

Генерирует размеченный датасет (4 вакансии × 20 резюме, `seed=42`, через `data.synthetic.generate_dataset`), прогоняет `rank_candidates` и считает метрики по каждой вакансии: `nDCG@10`, `nDCG`, `precision@5`, `Spearman(score, true_relevance)`. В конце — корреляция компонент (`keyword` / `cosine` / `combined`) с истинной релевантностью. Это количественное обоснование для «Показа 3».

Дополнительно выводится **отчёт по извлечению навыков** (`extract_skills(text)` против навыков, реально написанных в тексте, `text_skills`): Precision/Recall/F1 целиком (`OVERALL`), по каждой категории и агрегаты `MICRO`/`MACRO`.

Заголовок прохода: `Mean nDCG@10`, порог (`QUALITY_BAR = 0.80`). Скрипт `assert`-ит проход порога — падает с ненулевым кодом, если качество просело.

> **Оговорка для защиты.** Это **контролируемые синтетические данные**, а не реальные наймы: ground-truth relevance задаётся процедурой генерации, а текст резюме — зашумлённое наблюдение. Высокие цифры доказывают корректность алгоритма и работоспособность пайплайна оценки, но **не** продакшен-точность (реальных лейблов нет — 152-ФЗ).

## integration_demo.py — БД -> скорер -> БД

Две части:

1. **Quality** — скорит синтетическую вакансию (чей пул резюме несёт `_true_relevance`), проверяет сохранение в `hh_scores` (длина совпадает) и качество `Spearman(score, ground-truth) ≥ QUALITY_BAR (0.80)`.
2. **Real hh.ru** — скорит **реальную** вакансию из парсера (с тегами навыков) против пула; ground truth нет, ранжирование показано для осмотра. Сохранение отключено (`save=False`), чтобы не мешать cross-vacancy шумам.

Если резюме в БД нет — автоматически сидирует синтетику (`seed(n_vacancies=5, n_resumes=15)`), сохраняя реальные вакансии.

---

## Зависимости

Отдельного `requirements.txt` нет — используются пакеты всего проекта: `numpy`/`scipy` (метрики, через `scorer.metrics`), `pymongo` (только `integration_demo.py`). См. корневой README и `scorer/requirements.txt`.

## Замечания

- Все скрипты правят `sys.path` родительской директорией — запускать из корня проекта (`python tests/<file>.py`).
- Это не классический unit-test-набор под CI: `eval_synthetic` и `integration_demo` — оценочные/демо-скрипты с `assert`-проверкой порога, а `test_smoke` — единственный, формально совместимый с `pytest`.
