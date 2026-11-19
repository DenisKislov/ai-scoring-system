from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import subprocess
import sys

from .dataset import generate, freeze, verify, restore_missing
from .console import show_quality, show_performance, show_audit, show_live, show_protocol

DEFAULT_DATASET = Path('data/pmi_acceptance_release_2026-11-18')


def main():
    parser = argparse.ArgumentParser(description='Испытания по ПМИ Т1-1; результаты в консоли')
    parser.add_argument('command', choices=['build', 'freeze', 'verify', 'quality', 'performance', 'audit', 'live', 'run', 'report'])
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--output', type=Path,
                        help='Дополнительно сохранить файлы отчёта в указанную папку')
    parser.add_argument('--dataset-style', choices=['legacy', 'hh', 'it', 'acceptance'], default='legacy',
                        help='Generator for a new protocol; frozen datasets retain their original style')
    parser.add_argument('--live', action='store_true', help='Run an isolated Docker acceptance environment')
    parser.add_argument('--keep', action='store_true', help='Keep only the newly created test stack for manual UI checks')
    parser.add_argument('--cached-images', action='store_true',
                        help='Use an already downloaded MongoDB image without contacting the registry')
    args = parser.parse_args()
    if args.command == 'report' and args.output is None:
        parser.error('Для чтения сохранённых проверок укажите --output ПАПКА.')
    previous_level = logging.root.manager.disable
    logging.disable(logging.WARNING)
    try:
        return execute(args, parser)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'Ошибка: {exc}', file=sys.stderr)
        return 1
    finally:
        logging.disable(previous_level)


def execute(args, parser):
    if args.command == 'build':
        if (args.dataset / 'manifest.json').exists():
            restored = restore_missing(args.dataset)
            if restored:
                print(f'Восстановлено файлов: {len(restored)}')
                return 0
            parser.error('Frozen dataset exists. Use a new --dataset path for a new protocol.')
        data = generate(args.dataset, style=args.dataset_style)
        freeze(args.dataset)
        print(f'Набор создан: вакансий {len(data["vacancies"])}, резюме {len(data["resumes"])}, пар {len(data["pairs"])}.')
        return 0
    if args.command == 'freeze':
        if (args.dataset / 'manifest.json').exists():
            parser.error('Refusing to overwrite a frozen manifest. Start a new protocol directory.')
        freeze(args.dataset)
        print('Хэши набора зафиксированы.')
        return 0
    if args.command == 'verify':
        result = verify(args.dataset)
        print('Целостность: ' + ('ПРОЙДЕНО' if result['ok'] else 'НЕ ПРОЙДЕНО'))
        for error in result['errors']:
            print(f'  {error}')
        return 0 if result['ok'] else 1
    if args.command in ['quality', 'performance', 'live', 'run'] and (args.dataset / 'manifest.json').exists():
        restored = restore_missing(args.dataset)
        if restored:
            print(f'Восстановлено файлов: {len(restored)}', flush=True)

    checks = []
    if args.command in ['quality', 'run']:
        if not (args.dataset / 'manifest.json').exists():
            generate(args.dataset, style=args.dataset_style)
            freeze(args.dataset)
        from .quality import evaluate
        quality = evaluate(args.dataset, args.output)
        show_quality(quality, scope='PDF → парсер → скорер → рейтинг')
        checks.append(quality['passed'])
    if args.command in ['performance', 'run']:
        from .performance import measure
        performance = measure(args.dataset, args.output)
        show_performance(performance)
        checks.append(performance['passed'])
    if args.command in ['audit', 'run']:
        from .audit import scan
        audit = scan(Path.cwd(), args.output)
        show_audit(audit)
        checks.append(audit['automated_passed'])
    if args.command == 'run':
        command = [sys.executable, '-m', 'pytest', '-q', '--tb=short']
        if args.output is not None:
            args.output.mkdir(parents=True, exist_ok=True)
            command.append(f'--junitxml={args.output / "unit.xml"}')
        unit = subprocess.run(command, capture_output=True, text=True)
        if unit.returncode:
            print(unit.stdout.strip())
            if unit.stderr.strip():
                print(unit.stderr.strip(), file=sys.stderr)
        else:
            summary = next((line for line in reversed(unit.stdout.splitlines()) if 'passed' in line), 'ПРОЙДЕНО')
            print(f'Тесты: {summary}')
        if args.output is not None:
            (args.output / 'unit_exit_code.json').write_text(json.dumps({'exit_code': unit.returncode}))
        checks.append(unit.returncode == 0)
    if args.command == 'live' or (args.command == 'run' and args.live):
        from .live import run_live
        live = run_live(args.dataset, args.output, keep=args.keep, cached_images=args.cached_images)
        show_live(live)
        checks.append(live['status'] == 'passed' and not live.get('cleanup_error'))
    if args.command in ['report', 'run', 'live'] and args.output is not None:
        from .protocol import protocol
        result = protocol(args.output)
        if args.command == 'report':
            show_protocol(result)
            return 0 if result['accepted'] else 1
    if args.output is not None:
        print(f'Файлы отчёта: {args.output}')
    passed = all(checks)
    print('Итог технических проверок: ' + ('ПРОЙДЕНО' if passed else 'НЕ ПРОЙДЕНО'))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
