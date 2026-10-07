# Проверки и бенчмарки

Запуск из корня проекта:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python tests/eval_synthetic.py
.venv/bin/python scripts/benchmark_synthetic.py
```

`tests/eval_synthetic.py` проверяет порог ТЗ NDCG@10 ≥ 0,80 на том же
многосидовом расчёте, который используется в
`scripts/benchmark_synthetic.py`. Бенчмарк сохраняет агрегированные
результаты в `reports/synthetic_benchmark.md` и `.json` и выводит
Precision@10, Recall@10, MAP, MRR, NDCG@10 и Spearman. Порог бинарной
релевантности — 0,65; NDCG использует непрерывную метку.

`test_synthetic_realism.py` проверяет шесть направлений, связность стека,
воспроизводимость генерации и вычисление метки из скрытого профиля.
`test_metrics.py` проверяет расчёт метрик извлечения навыков по категориям.

`integration_demo.py` демонстрирует путь MongoDB → скорер → MongoDB и требует
запущенной MongoDB. Его следует запускать отдельно. Синтетические метрики
показывают качество только на контролируемом наборе, а не на реальных наймах.
