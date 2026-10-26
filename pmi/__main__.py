from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
from .dataset import generate, freeze, verify, restore_missing


def main():
    parser = argparse.ArgumentParser(description='Испытания по ПМИ Т1-1')
    parser.add_argument('command',choices=['build','freeze','verify','quality','performance','audit','live','run','report'])
    parser.add_argument('--dataset',type=Path,default=Path('data/pmi'))
    parser.add_argument('--output',type=Path,default=Path('reports/pmi'))
    parser.add_argument('--live',action='store_true',help='Run an isolated Docker acceptance environment')
    parser.add_argument('--keep',action='store_true',help='Keep only the newly created test stack for manual UI checks')
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    if args.command == 'build':
        if (args.dataset/'manifest.json').exists():
            restored=restore_missing(args.dataset)
            if restored:
                print(json.dumps({'restored_files':len(restored)})); return 0
            parser.error('Frozen dataset exists. Use a new --dataset path for a new protocol.')
        data = generate(args.dataset); freeze(args.dataset)
        print(json.dumps({'vacancies':len(data['vacancies']),'resumes':len(data['resumes']),'pairs':len(data['pairs'])}))
        return 0
    if args.command == 'freeze':
        if (args.dataset/'manifest.json').exists():
            parser.error('Refusing to overwrite a frozen manifest. Start a new protocol directory.')
        freeze(args.dataset); return 0
    if args.command == 'verify':
        result=verify(args.dataset); print(json.dumps(result)); return 0 if result['ok'] else 1
    if args.command in ['quality','performance','live','run'] and (args.dataset/'manifest.json').exists():
        restored=restore_missing(args.dataset)
        if restored:
            print(json.dumps({'restored_files':len(restored)}),flush=True)
    if args.command in ['quality','run']:
        if not (args.dataset/'manifest.json').exists():
            generate(args.dataset); freeze(args.dataset)
        from .quality import evaluate
        quality=evaluate(args.dataset,args.output)
        print(json.dumps({'quality':quality['metrics'],'passed':quality['passed']}))
        if args.command == 'quality': return 0 if quality['passed'] else 1
    if args.command in ['performance','run']:
        from .performance import measure
        performance=measure(args.dataset,args.output)
        print(json.dumps({'performance':performance['seconds'],'passed':performance['passed']}))
        if args.command == 'performance': return 0 if performance['passed'] else 1
    if args.command in ['audit','run']:
        from .audit import scan
        audit=scan(Path.cwd(),args.output)
        print(json.dumps({'secret_findings':audit['secret_findings'],'contact_candidates':audit['contact_candidates']}))
        if args.command == 'audit': return 0 if audit['automated_passed'] else 1
    if args.command == 'run':
        unit = subprocess.run([sys.executable,'-m','pytest','-q','--tb=short',f'--junitxml={args.output / "unit.xml"}'])
        (args.output/'unit_exit_code.json').write_text(json.dumps({'exit_code':unit.returncode}))
    if args.command == 'live' or (args.command == 'run' and args.live):
        from .live import run_live
        live=run_live(args.dataset,args.output,keep=args.keep)
        print(json.dumps({'live_status':live['status'],'reason':live.get('reason')}))
    if args.command in ['report','run','live']:
        from .protocol import protocol
        result=protocol(args.output)
        print(json.dumps({'protocol':str(args.output/'protocol.md'),'accepted':result['accepted']}))
        return 0 if result['accepted'] else 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
