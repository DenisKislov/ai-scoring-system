# Утилиты сопровождения

Запускаются как модули из корня проекта. Не являются обязательной частью запуска сайта.

| Модуль | Назначение |
|---|---|
| `tools.clean_profession_skills` | Проверка и очистка `data/skills_by_profession.json` |
| `tools.build_ontology` | Генерация `scorer/skills_auto.json` и `skills_auto_raw.json` |
| `tools.build_reference_corpus` | Генерация фиксированного `scorer/reference_corpus.py` |
| `tools.vacancy_skills` | Просмотр навыков, найденных рабочим экстрактором в доступном описании вакансии |

Зависимости и порядок регенерации:

```bash
python -m pip install -r requirements.lock
python -m tools.clean_profession_skills
python -m tools.build_ontology
python -m tools.build_reference_corpus
```

Эти команды изменяют словарь и референс-корпус. После изменения артефактов прежний fingerprint и frozen-протокол не подтверждают новую конфигурацию; нужен новый замер.

Для доступной страницы вакансии:

```bash
python -m tools.vacancy_skills 'https://hh.ru/vacancy/ID'
```

Обработка навыков использует общий `scorer.extract_skills`: словарь, нормализацию и spaCy NER. Инструмент не запускается автоматически при работе сайта и не обходит ограничения сайта.

Текущее качество измеряется командами `python -m pmi quality` и `python -m pmi live` с явным путём [синтетического набора](../data/pmi_acceptance_release_2026-11-18/). [Методика](../docs/ACCEPTANCE_DATASET.md). Для прежнего JSON-набора остаётся `scripts/benchmark_real_data.py`; `annotated` и `extracted` — отдельные режимы.
