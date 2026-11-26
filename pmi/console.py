"""Compact human-readable results; no filesystem writes."""
from __future__ import annotations


def status(passed):
    return 'ПРОЙДЕНО' if passed else 'НЕ ПРОЙДЕНО'


def number(value):
    return '—' if value is None else f'{value:.4f}'


def show_quality(report, *, scope):
    dataset = report['dataset']
    print(f'Синтетический набор: {dataset["vacancies"]} вакансий, {dataset["resumes"]} резюме, {dataset["pairs"]} пар.')
    print(scope)
    print('Средние метрики по вакансиям:')
    print(f'{"Метрика":<28} {"Значение":>9} {"Минимум":>9}  Результат')
    labels = {'ndcg_at_10': 'NDCG@10', 'precision_at_5': 'Precision@5',
              'precision_at_10': 'Precision@10', 'recall_at_10': 'Recall@10',
              'spearman': 'Spearman (ПМИ)'}
    for name, label in labels.items():
        criterion = report['criteria'][name]
        print(f'{label:<28} {number(criterion["value"]):>9} {number(criterion["minimum"]):>9}  {status(criterion["passed"])}')
    a10 = report['a10']
    print(f'А-10: {status(a10["passed"])}; нарушений: {len(a10["failures"])}.')


def show_performance(report):
    print(f'{"Производительность":<28} {"Секунды":>9} {"Лимит":>9}  Результат')
    for name, seconds in report['seconds'].items():
        limit = report['limits_seconds'][name]
        print(f'{name:<28} {seconds:>9.3f} {limit:>9.0f}  {status(seconds <= limit)}')


def show_audit(report):
    print(f'Аудит: секретов — {report["secret_findings"]}; контактов для проверки — {report["contact_candidates"]}.')
    if report.get('history_error'):
        print(f'Проверка истории: {report["history_error"]}')
    print(f'Автоматическая проверка аудита: {status(report["automated_passed"])}')


def show_live(report):
    if 'quality_api' in report:
        show_quality(report['quality_api'], scope='PDF → HTTP → парсер → MongoDB → скорер → сохранённый рейтинг')
    print(f'Docker: {status(report["status"] == "passed")}')
    if report.get('reason'):
        print(f'Причина: {report["reason"]}')
    if report.get('cleanup_error'):
        print(f'Ошибка очистки стенда: {report["cleanup_error"]}')
    if report.get('kept'):
        print(f'Стенд оставлен: {report["project"]}; http://localhost:13000')


def show_protocol(report):
    for row in report['cases']:
        print(f'{row["case"]}: {row["status"]}')
    print('Формальная приёмка: ' + ('ОФОРМЛЕНА' if report['accepted'] else 'НЕ ОФОРМЛЕНА'))
