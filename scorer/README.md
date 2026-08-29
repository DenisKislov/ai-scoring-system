# scorer/ — гибридный скорер резюме

Алгоритмическое ядро проекта: оценивает, насколько резюме соответствует вакансии, и возвращает ранжированный список кандидатов. **Без нейросетей**: сопоставление ключевых навыков по онтологии (с поддержкой must-have) плюс **TF-IDF + косинусное сходство** текстов.

Работает с **русскими** текстами (hh.ru): нативное русское NLP, без перевода.

---

## Установка

```bash
# из корня проекта (conda env candidate_scoring, Python 3.10+)
pip install -r scorer/requirements.txt
```

Зависимости — см. [`requirements.txt`](requirements.txt). Кратко:

| Пакет | Зачем |
|---|---|
| `pymorphy3` + `pymorphy3-dicts-ru` | лемматизация русских слов (`разработке -> разработка`) |
| `razdel` | токенизация с учётом правил русского языка |
| `scikit-learn` | TF-IDF-векторы + косинусное сходство |
| `numpy` | метрики качества ранжирования (nDCG, precision@k) |
| `scipy` | Spearman в [`metrics.py`](metrics.py) |
| `pymongo` *(опц., ставится на уровне проекта)* | только для CLI `python -m scorer.service` и интеграции с MongoDB |

Стоп-слова встроены ([`stopwords_ru.py`](stopwords_ru.py)), онтология навыков и референс-корпус уже лежат в репо.

---

## Как это работает

Для каждой пары (вакансия, резюме) считается гибридный скор:

```
raw = 0.6 · keyword_score + 0.4 · cosine_sim
Score(%) = round(raw · 100)
```

1. **Нормализация** ([`normalize.py`](normalize.py)) — очистка HTML -> `razdel`-токенизация -> lowercase + раскрытие IT-сокращений (`k8s -> kubernetes`, `js -> javascript`, `mongo -> mongodb`, `ci -> ci/cd`, `ml -> machine learning` …) -> лемматизация `pymorphy3` (с `lru_cache`) -> удаление стоп-слов (до и после лемматизации) и однобуквенных токенов. Английские токены проходят lowercase **без** лемматизации (pymorphy3 — только русский).
2. **Онтология навыков** ([`skills_dict.py`](skills_dict.py) + `skills_auto*.json`) — курируемый словарь IT-навыков с RU/EN-алиасами: буквенные в `SKILLS`, символьные в `RAW_SKILLS`; авто-расширение из корпуса профессий. При коллизии канонических имён курируемая запись выигрывает.
3. **Сопоставление навыков** ([`skills.py`](skills.py)) — `matched_skills = skills(vacancy) ∩ skills(resume)`. Два матчера: lemma-матчер (уни- и биграммы нормализованных алиасов) и raw-substring-матчер (символьные: `C++`, `.NET`, `CI/CD`). **Must-have** (`critical_skills`) весят **×2** относительно обычных при расчёте `keyword_score`.
4. **Сходство текстов** ([`similarity.py`](similarity.py)) — TF-IDF (uni+bi-grams, `sublinear_tf`) по лемматизированным текстам -> `cosine ∈ [0, 1]`. **Векторизатор обучается один раз** при импорте на фиксированном референс-корпусе ([`reference_corpus.py`](reference_corpus.py)) — поэтому косинус пары не зависит от состава пула, а `Score` остаётся **абсолютной мерой**.
5. **Итог** ([`scoring.py`](scoring.py)) — `Score` 0–100% (абсолютный), плюс `rank_percentile` (позиция в пачке — отдельное поле) и разбор `matched` / `missing` / `critical` с вкладом каждого компонента.

> **Тай-брейк по опыту.** При равном `Score` кандидаты доупорядочиваются по годам опыта (больше -> выше). Годы извлекаются в слое интеграции ([`experience_years()`](../db/builders.py:34)), сам `Score` при этом не меняется. См. корневой README.

---

## API

```python
from scorer import calculate_score, rank_candidates, DEFAULT_WEIGHTS

# одна пара
calculate_score(resume_text, vacancy_text)
# {"score": 73, "raw_score": 0.73,
#  "keyword_score": 0.8, "cosine_sim": 0.6,
#  "keyword_contribution": 0.48, "cosine_contribution": 0.24,
#  "matched_skills": ["Python", "PostgreSQL", ...], "missing_skills": [...],
#  "matched_critical": [...], "missing_critical": [...],
#  "vacancy_skills": [...], "critical_skills": [...]}

# пачка резюме под одну вакансию — отсортировано по score, у каждого rank_percentile
rank_candidates(vacancy_text, [resume1, resume2, resume3])
```

Свои веса: `rank_candidates(vac_text, resumes, weights={"keyword": 0.6, "cosine": 0.4})`.

### Must-have и порог

```python
calculate_score(
    resume_text,
    vacancy_text,
    critical_skills={"Python", "PostgreSQL"},  # must-have — вес ×2 в keyword_score
    min_score=60,                                # добавляет passed_threshold
)
```

При передаче `critical_skills` поля `matched_critical` / `missing_critical` показывают покрытие must-have отдельно, а `keyword_score` считается как взвешенная доля покрытия (must-have = `CRITICAL_WEIGHT = 2.0`).

### Метрики ([`metrics.py`](metrics.py))

**Ранжирование** (качество упорядочивания кандидатов):

```python
from scorer.metrics import ndcg, precision_at_k, spearman
ndcg(relevances_in_predicted_order, k=10)   # graded linear-gain nDCG@10
precision_at_k(relevances, k=5, threshold=0.5)
spearman(predicted_scores, true_relevances)
```

**Классификация навыков** — Precision / Recall / F1 целиком и по категориям
(таксономия в [`skills_categories.py`](skills_categories.py)):

```python
from scorer.metrics import precision, recall, f1, classification_report

precision(predicted_skills, true_skills)   # доля предсказанных навыков, которые истинны
recall(predicted_skills, true_skills)      # доля истинных навыков, которые предсказаны
f1(predicted_skills, true_skills)          # гармоническое среднее P и R

report = classification_report(predicted_skills, true_skills)
# report["overall"]            — P/R/F1 + TP/FP/FN по всему множеству
# report["per_category"]       — {"категория": {"tp","fp","fn","precision","recall","f1"}}
# report["micro"] / report["macro"] — агрегаты по категориям
```

Категории заданы в [`skills_categories.py`](skills_categories.py): языки
программирования, базы данных, ML/Data Science, frontend, backend/API,
DevOps/инфраструктура, BI, процессы/soft skills. Курируемые навыки размечены
явно (`SKILL_CATEGORIES`), остальная авто-онтология — детерминированными
keyword-правилами; нераспознанные навыки попадают в «Прочее». Свою разметку
можно передать как `categories={"категория": {навыки...}}`.

---

## CLI (через слой БД)

```bash
python -m scorer.service [VACANCY_ID] [--top N] [--limit-resumes N] [--no-save] [--json] [--critical-skills SKILL ...]
```

Тянет вакансию и резюме из MongoDB, скорит, сохраняет в коллекцию `hh_scores` (БД `gb_parse`) и печатает топ-N. Нужен запущенный `mongo` и `pymongo`.

---

## Модули

| Файл | Роль |
|---|---|
| [`__init__.py`](__init__.py) | публичный API: `calculate_score`, `rank_candidates`, `normalize`, `extract_skills`, `match_skills`, `DEFAULT_WEIGHTS` |
| [`normalize.py`](normalize.py) | razdel + pymorphy3, аббревиатуры, стоп-слова, кэш лемм |
| [`stopwords_ru.py`](stopwords_ru.py) | встроенный русский стоп-список |
| [`skills_dict.py`](skills_dict.py) | курируемая онтология + автозагрузка `skills_auto*.json` |
| [`skills_auto.json`](skills_auto.json) | авто-онтология из корпуса (gen: `tools/build_ontology.py`) |
| [`skills_auto_raw.json`](skills_auto_raw.json) | символьные навыки (`C++`, `.NET`, `CI/CD`, …) |
| [`skills.py`](skills.py) | извлечение/сопоставление навыков, must-have (вес ×2) |
| [`reference_corpus.py`](reference_corpus.py) | референс-корпус для стабильного IDF (gen: `tools/build_reference_corpus.py`) — **не править руками** |
| [`similarity.py`](similarity.py) | TF-IDF (фикс. IDF) + cosine |
| [`scoring.py`](scoring.py) | `calculate_score` + `rank_candidates`, `DEFAULT_WEIGHTS` |
| [`metrics.py`](metrics.py) | nDCG / precision@k / Spearman + Precision/Recall/F1 по категориям навыков |
| [`skills_categories.py`](skills_categories.py) | таксономия категорий навыков для категорийных метрик |
| [`service.py`](service.py) | интеграция с MongoDB + CLI |

---

## Качество

Качество ранжирования проверяется на синтетике с ground-truth ([`tests/eval_synthetic.py`](../tests/eval_synthetic.py)):

- по каждой вакансии считаются `nDCG@10`, `nDCG`, `precision@5`, `Spearman(score, true_relevance)`;
- в конце — корреляция компонент (`keyword` / `cosine` / `combined`) с истинной релевантностью;
- проход по порогу `QUALITY_BAR = 0.80` (скрипт `assert`-ит проход).

```bash
python tests/eval_synthetic.py
```

> Это **контролируемые синтетические данные**: ground-truth задаётся процедурой генерации, а текст резюме — зашумлённое наблюдение. Цифры доказывают корректность алгоритма и пайплайна оценки, но **не** продакшен-точность. Реальных лейблов нет (152-ФЗ).

---

## Регенерация артефактов

`skills_auto*.json` и `reference_corpus.py` уже в репо. Перегенерируются, если правите корпус профессий (запускать из корня проекта):

```bash
python -m tools.clean_profession_skills && python -m tools.build_ontology && python -m tools.build_reference_corpus
```
