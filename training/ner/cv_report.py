"""Render the evidence without presenting training-set scores as holdout scores."""
import argparse
import json
from pathlib import Path


def number(value):
    return "—" if value is None else f"{value:.4f}"


def render(directory):
    report = json.loads((directory / "cross_validation.json").read_text())
    legacy_path = directory / "legacy_reference.json"
    legacy = json.loads(legacy_path.read_text()) if legacy_path.exists() else {"metrics": {}}
    oof = report["out_of_fold"]
    final = report["final_model"]["in_sample_evaluation"]
    names = {"ndcg_at_10": "NDCG@10", "precision_at_5": "Precision@5",
             "precision_at_10": "Precision@10", "recall_at_10": "Recall@10",
             "spearman_score": "Spearman"}
    rows = ["# Обучение spaCy на корпусе SuperJob и проверка по пяти частям", "",
            "| Условие | Результат |", "|---|---|",
            "| Корпус | Те же 10 вакансий и 194 резюме из опубликованных JSON презентации. Тексты, expected_skills и состав не изменены |",
            "| Целостность | SHA-256 обоих JSON совпали до и после обучения; manifest.json |",
            "| Внешние части | Пять групп: по 2 вакансии и 38–39 резюме. Каждый документ имеет ровно один прогноз модели, которая не использовала его ни для обучения, ни для выбора эпохи |",
            "| Подбор эпох | Внутренняя проверка только внутри четырёх обучающих частей. Внешние метки не определяют число эпох |",
            "| Базовая модель | ru_core_news_sm 3.8.0; новый класс Skill; spaCy 3.8.16; CPU |",
            "| Разметка сущностей | Автоматическое сопоставление expected_skills с упоминаниями и алиасами. Навыки, не найденные в тексте, не дописывались в текст и не создавались как фиктивные сущности |",
            "| Полные PDF | Не использовались. Исходные папки data/resumes и data/vacancies не читались |",
            "| Ограничение независимости | Исторический продуктивный словарь ранее настраивался по этому корпусу. Здесь по пяти частям проверяется новое обучение NER, а не независимость всей истории разработки |",
            "| Повторы | Группировка по нормализованному тексту и сходству 5-грамм. Публичные JSON не позволяют доказать отсутствие всех версий одного человека по идентификаторам |",
            "| Финальная модель | После проверки обучена на всех 204 документах. Число эпох — медиана лучших эпох внутренней проверки, без выбора по внешним метрикам |",
            "", "| Метрика | Порог из ПМИ | Историческая модель | OOF, пять моделей | Финальная модель: обучающие данные |",
            "|---|---:|---:|---:|---:|"]
    for key, label in names.items():
        rows.append(f"| {label} | {oof['numeric_thresholds'][key]['minimum']} | "
                    f"{number(legacy['metrics'].get(key))} | {number(oof['ranking']['mean'][key])} | "
                    f"{number(final['ranking']['mean'][key])} |")
    passed = sum(c["passed"] for c in oof["numeric_thresholds"].values())
    rows += ["", "| Как читать результаты | Граница вывода |", "|---|---|",
             f"| Численные пороги | В OOF-диагностике выполнено {passed} из 5. Это не акт приёмки по ПМИ |",
             "| Историческая модель | Её обучение пересекалось с частью корпуса; это справочная точка, а не независимый контроль |",
             "| OOF на полном пуле | Показатели рассчитаны для всех 1940 пар. Навыки каждого документа предсказаны вне его обучающей части. В рейтинге соединены прогнозы пяти разных моделей; эти числа нельзя приписывать одной развёрнутой модели |",
             "| Финальная модель | Видела все 204 документа. Её показатели на том же корпусе являются обучающими и не подтверждают обобщение |",
             "| Строгая проверка одним экземпляром модели | Дополнительно каждый fold проверен на своих 2 вакансиях и 38–39 резюме. Оба документа пары исключены из обучения одного экземпляра модели, но пул меньше 194. Подробности в strict_same_model_fold_pools |",
             "| Формулы | Сохранены формулы исходного JSON-бенчмарка, включая scipy Spearman, и порог бинарной релевантности 0.1. Метки пар — proxy покрытия навыков, не экспертная пригодность человека |",
             "", "| Извлечение навыков | Precision | Recall | F1 |", "|---|---:|---:|---:|"]
    for scope, data in [("OOF: словарь + новая NER", oof),
                        ("OOF: только новая NER", report["ner_only_out_of_fold"]),
                        ("Финальная модель, обучающие данные", final)]:
        for kind, label in [("resumes", "резюме"), ("vacancies", "вакансии")]:
            metrics = data["extraction"][kind]["micro"]
            rows.append(f"| {scope}, {label} | {metrics['precision']:.4f} | {metrics['recall']:.4f} | {metrics['f1']:.4f} |")
    rows += ["", "| Часть | Обучение | Внутренняя проверка | Внешний тест | Лучшая эпоха | F1 сущностей на внешнем тесте |",
             "|---|---:|---:|---:|---:|---:|"]
    for k, fold in report["folds"].items():
        rows.append(f"| {int(k)+1} | {len(fold['fit_keys'])} | {len(fold['monitor_keys'])} | "
                    f"{len(fold['test_keys'])} | {fold['best_epoch']} | {fold['test_span_metrics']['ents_f']:.4f} |")
    coverage = {key: sum(f['coverage']['test'].get(key, 0) for f in report['folds'].values())
                for key in ['matched_skills', 'unmatched_skills', 'skipped_misaligned']}
    rows += ["", "| Артефакт | Содержание |", "|---|---|",
             f"| Покрытие автоматической разметки | Меток с найденной текстовой формой: {coverage['matched_skills']}; "
             f"без найденной формы: {coverage['unmatched_skills']}; невыровненных спанов: {coverage['skipped_misaligned']}. "
             "Шаблонное совпадение не заменяет экспертную разметку |",
             f"| Рабочий артефакт | `{report['final_model']['path']}`; эпох: {report['final_model']['epochs']} |",
             "| Основной сайт | Модель автоматически не заменялась; обучение и отчёт не равны развёртыванию |",
             "| cross_validation.json | Полные метрики, категории навыков, разбиения, истории обучения, прогнозы каждого документа и SHA-256 файлов моделей |",
             "| manifest.json | Хэши исходных JSON, версия базовой модели, seed и настройки обучения |",
             "| Защита словаря модели | Контактные и секретоподобные строки удалены из сериализованного словаря; совпадение сущностей до/после проверено |",
             "| Установка базы для повторения | `python -m pip install -r requirements.lock -r training/ner/requirements-training.txt` |",
             "| Повторение | `PYTHONHASHSEED=20261118 python -m training.ner.superjob_cv --output-dir training/ner/out/superjob_cv_repeat --report-dir reports/superjob_cv_repeat --workers 2 --epochs 24` |",
             "| Тесты разбиения | `python -m pytest -q tests/test_superjob_cv.py` |"]
    (directory / "README.md").write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    render(parser.parse_args().directory)
