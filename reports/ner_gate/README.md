# Гейт включения NER-навыков (union со словарём)

Исторический отчёт из переданного архива. Его таблицы и JSON относятся к версии до интеграции; некоторые округления исходного текста неточны. Актуальные измерения, проверка пересечений обучения и границы выводов: [отчёт от 18.11.2026](../spacy_integration_2026-11-18/README.md).

Дата: 2026-11-16 · Датасет: `data/benchmark` (10 вакансий, 194 резюме, режим `--ranking-inputs extracted`)
Команды: см. `docs/superpowers/plans/2026-11-16-ner-skill-extraction.md`, Task 7.

## Раунд 2: русская модель (2026-11-17)

Обучена на PDF-корпусе с разметкой (distant supervision, каскадный матчинг
`training/ner/span_match.py`): 193 резюме + 51 вакансия, 196/24/24 сплит,
покрытие меток 96.3% / 92.6%, оценка шума разметки 4.5%. Модель:
`ru_core_news_sm`-инициализация → tok2vec+ner, CPU, только лейбл Skill.
На отложенном test-сплите: P=0.819, R=0.905, F1=0.860 (span-level).
Обучающий корпус и гейт-корпус — **разные** (PDF hh-выгрузки vs SuperJob
JSON): гейт проверяет перенос, а не подгонку.

| Метрика | baseline (словарь) | en-union (round 1) | **ru-union** | Гейт vs baseline |
|---|---:|---:|---:|---|
| Extraction F1 (resumes, micro) | 0.544 | 0.428 | **0.612** | +0.068 ✅ |
| Extraction precision (resumes) | 0.662 | 0.337 | **0.652** | −0.010 (сохранён) |
| Extraction recall (resumes) | 0.462 | 0.588 | **0.576** | +0.114 ✅ |
| Extraction F1 (vacancies, micro) | 0.408 | 0.644 | **0.699** | +0.292 ✅ |
| NDCG@10 | 0.682 | 0.724 | **0.764** | +0.082 ✅ |
| Precision@10 | 0.760 | 0.830 | **0.850** | +0.090 ✅ |
| Spearman(Score, proxy) | 0.586 | 0.657 | **0.658** | +0.073 ✅ |

Правило: F1 не падает (обе стороны) и NDCG@10 проседает не более 0.005.

**Решение: гейт пройден — RU-модель скопирована в `scorer/models/resume_ner/`,
`ner_skills_enabled: true`.** Побеждает union со словарём: прирост и
извлечения, и ранжирования без потери precision. Требуется новый PMI-прогон
(README: «для повторного прогона изменённого кода нужен новый набор и
протокол»).

## Раунд 1: английская модель (2026-11-16, историческая)

| Метрика | baseline (словарь) | en-union | Δ |
|---|---:|---:|---:|
| Extraction F1 (resumes, micro) | 0.544 | 0.428 | **−0.116** |
| Extraction F1 (vacancies, micro) | 0.408 | 0.644 | +0.236 |
| Extraction precision (resumes) | 0.662 | 0.337 | −0.325 |
| Extraction recall (resumes) | 0.462 | 0.588 | +0.126 |
| NDCG@10 | 0.682 | 0.724 | +0.042 |
| Precision@10 | 0.760 | 0.830 | +0.070 |
| Recall@10 | 0.129 | 0.165 | +0.036 |
| Spearman(Score, proxy) | 0.586 | 0.657 | +0.071 |

Решение раунда 1: **англоязычная модель оставлена за флагом** — F1 резюме
упал (precision 0.662 → 0.337: модель на 60 англ. резюме порождала ложные
Skill-спаны на русском прозе). Это решение закрыто раундом 2.

## Воспроизведение раунда 2

```bash
# датасет (покрытие/шум — в training/ner/data/ru_v1/stats.json)
python training/ner/build_ru_dataset.py
# обучение (CPU; ru_core_news_sm ставится wheel-URL из GitHub releases)
python training/ner/train_ner.py --lang ru --base ru_core_news_sm \
  --train training/ner/data/ru_v1/train.spacy --dev training/ner/data/ru_v1/dev.spacy \
  --out training/ner/out/ru_v1
# гейт
NER_SKILLS_ENABLED=1 NER_SKILLS_MODEL=training/ner/out/ru_v1/model-best \
  python scripts/benchmark_real_data.py --dataset-dir data/benchmark \
  --ranking-inputs extracted --output-dir reports/ner_gate --output-prefix ner_ru
```

Дальнейшие рычаги: алиасы в матчинге датасета (порог покрытия 96.3% → выше),
дообучение на новых аннотациях, асимметричный union только для вакансий.
