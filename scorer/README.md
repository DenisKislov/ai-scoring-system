# scorer/ — гибридный скорер резюме

Алгоритмическое ядро проекта: оценивает, насколько резюме соответствует вакансии, и возвращает ранжированный список кандидатов. **Без нейросетей с нуля** — согласно ТЗ это поиск ключевых навыков, их взвешивание и TF-IDF + косинусное сходство текстов.

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
| `pymorphy3` + `pymorphy3-dicts-ru` | лемматизация русских слов (`разработке → разработка`) |
| `razdel` | токенизация с учётом правил русского языка |
| `scikit-learn` | TF-IDF-векторы + косинусное сходство |
| `numpy`, `scipy` | метрики качества ранжирования (nDCG, Spearman) |
| `pymongo` *(опц.)* | только для CLI `python -m scorer.service` и интеграции с MongoDB |

Стоп-слова встроены (`stopwords_ru.py`), онтология навыков и референс-корпус уже лежат в репо.

---

## Как это работает

Для каждой пары (вакансия, резюме) считается гибридный скор:

```
raw = 0.6 · keyword_score + 0.4 · cosine_sim
Score(%) = round(raw · 100)
```

1. **Нормализация** (`normalize.py`) — `razdel` токенизация → лемматизация `pymorphy3` (с `lru_cache`) → удаление стоп-слов. Английские токены проходят lowercase без лемматизации (pymorphy3 — только русский).
2. **Онтология навыков** (`skills_dict.py` + `skills_auto*.json`) — курируемый словарь IT-навыков с RU/EN-алиасами, авто-расширенный из корпуса профессий до покрытия ~97%.
3. **Сопоставление навыков** (`skills.py`) — `matched_skills = skills(vacancy) ∩ skills(resume)`. Два матчера: по леммам (буквенные алиасы, в т.ч. биграммы) и raw-substring (символьные: `C++`, `.NET`, `CI/CD`). Отсюда столбец «Найденные ключевые навыки».
4. **Сходство текстов** (`similarity.py`) — TF-IDF (uni+bi-grams, `sublinear_tf`) по лемматизированным текстам → `cosine ∈ [0, 1]`. **Векторизатор обучается один раз** на фиксированном референс-корпусе (`reference_corpus.py`) — поэтому косинус пары не зависит от состава пула, а `Score` остаётся **абсолютной мерой**.
5. **Итог** (`scoring.py`) — `Score` 0–100% (абсолютный), плюс `rank_percentile` (позиция в пачке — отдельное поле).

> **Тайм-брейк по опыту.** При равном `Score` кандидаты доупорядочиваются по годам опыта (больше → выше). Годы извлекаются в слое интеграции (`db.builders.experience_years`), сам `Score` при этом не меняется. См. корневой README.

---

## API

```python
from scorer import calculate_score, rank_candidates, DEFAULT_WEIGHTS

# одна пара
calculate_score(resume_text, vacancy_text)
# {"score": 73, "keyword_score": 0.8, "cosine_sim": 0.6,
#  "matched_skills": ["Python", "PostgreSQL", ...], "missing_skills": [...], ...}

# пачка резюме под одну вакансию — отсортировано по score + rank_percentile
rank_candidates(vacancy_text, [resume1, resume2, resume3])
```

Свои веса: `rank_candidates(vac_text, resumes, weights={"keyword": 0.5, "cosine": 0.5})`.

### Метрики (`metrics.py`)

```python
from scorer.metrics import ndcg, precision_at_k, spearman
ndcg(relevances_in_predicted_order, k=10)   # graded linear-gain nDCG@10
precision_at_k(relevances, k=5, threshold=0.5)
spearman(predicted_scores, true_relevances)
```

---

## CLI (через слой БД)

```bash
python -m scorer.service [VACANCY_ID] [--top N] [--limit-resumes N] [--no-save] [--json]
```

Тянет вакансию и резюме из MongoDB, скорит, сохраняет в коллекцию `hh_scores` (БД `gb_parse`) и печатает топ-N. Нужен запущенный `mongo` и `pymongo`.

---

## Модули

| Файл | Роль |
|---|---|
| `__init__.py` | публичный API: `calculate_score`, `rank_candidates`, `normalize`, `extract_skills`, `match_skills`, `DEFAULT_WEIGHTS` |
| `normalize.py` | razdel + pymorphy3, стоп-слова, кэш лемм |
| `stopwords_ru.py` | встроенный русский стоп-список |
| `skills_dict.py` | курируемая онтология + автозагрузка `skills_auto*.json` |
| `skills_auto.json` | авто-онтология из корпуса (gen: `tools/build_ontology.py`) |
| `skills_auto_raw.json` | символьные навыки (`C++`, `.NET`, …) |
| `skills.py` | извлечение/сопоставление навыков (леммы + raw-substring) |
| `reference_corpus.py` | референс-корпус для стабильного IDF (gen: `tools/build_reference_corpus.py`) — **не править руками** |
| `similarity.py` | TF-IDF (фикс. IDF) + cosine |
| `scoring.py` | `calculate_score` + `rank_candidates` |
| `metrics.py` | nDCG / precision@k / spearman |
| `service.py` | интеграция с MongoDB + CLI |

---

## Качество

На синтетике с ground-truth (`tests/eval_synthetic.py`):

```
Mean nDCG@10 = 0.996    Spearman = 0.972
Корреляция с true relevance: keyword +0.985, cosine +0.915, combined +0.985
```

> ⚠️ Это **контролируемые синтетические данные**: высокие цифры доказывают корректность алгоритма и пайплайна оценки, но не продакшен-точность. Реальных лейблов нет (152-ФЗ).

---

## Регенерация артефактов

`skills_auto*.json` и `reference_corpus.py` уже в репо. Перегенерируются, если правите корпус профессий (запускать из корня проекта):

```bash
python -m tools.clean_profession_skills && python -m tools.build_ontology && python -m tools.build_reference_corpus
```
