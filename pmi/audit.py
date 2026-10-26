"""A-18: scan working sources and Git history without printing secret values."""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

PATTERNS = {
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'provider_key': re.compile(r'\b(?:AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{32,})\b'),
    'embedded_credentials': re.compile(r'(?:mongodb(?:\+srv)?|https?)://[^\s/"\']+:[^\s/@"\']+@'),
    'password_literal': re.compile(r'(?i)\b(?:password|passwd|api_key|secret_key)\s*[=:]\s*["\'](?!\$|<|example|test|change|your|os\.environ)[^"\'\s]{8,}["\']'),
    'contact_email': re.compile(r'\b[\w.+-]+@(?!example\.(?:com|org)|test\.invalid)[\w.-]+\.[a-z]{2,}\b',re.I),
    'contact_phone': re.compile(r'(?<!\w)(?:\+7|8)[ (.-]*\d{3}[) .-]*\d{3}[ .-]*\d{2}[ .-]*\d{2}(?!\d)'),
}
EXCLUDED = {'.git','.venv','.idea','node_modules','build','__pycache__','.pytest_cache','logs'}
TEXT_SUFFIXES = {'.py','.js','.ts','.tsx','.json','.csv','.md','.txt','.yml','.yaml','.toml','.ini','.env','.lock'}


def matches(content: bytes) -> list:
    text = content.decode('utf-8',errors='ignore')
    # Values are never included in the report, including for old Git blobs.
    return [{'kind':name,'line':text[:m.start()].count('\n')+1}
            for name,pattern in PATTERNS.items() for m in pattern.finditer(text)]


def scan(root: Path, out: Path, history=True) -> dict:
    findings, files = [], 0
    candidates=[p for p in root.rglob('*') if p.is_file() and not any(part in EXCLUDED for part in p.relative_to(root).parts)]
    ignored_result=subprocess.run(['git','check-ignore','--stdin'],cwd=root,input='\n'.join(str(p.relative_to(root)) for p in candidates)+'\n',capture_output=True,text=True)
    ignored=set(ignored_result.stdout.splitlines())
    for path in sorted(candidates):
        rel = path.relative_to(root)
        if any(part in EXCLUDED for part in rel.parts) or not path.is_file():
            continue
        if str(rel) in ignored:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 10_000_000:
            continue
        # The scanner source contains patterns, not actual credentials.
        files += 1
        for match in matches(path.read_bytes()):
            findings.append({'scope':'working_tree','file':str(rel),**match})
    blobs = 0
    history_error = None
    if history:
        try:
            output = subprocess.check_output(['git','rev-list','--objects','--all'],cwd=root,text=True)
            objects=[]
            for row in output.splitlines():
                oid, _, name=row.partition(' ')
                if Path(name).suffix.lower() in TEXT_SUFFIXES:
                    objects.append((oid,name))
            metadata=subprocess.check_output(['git','cat-file','--batch-check=%(objectname) %(objecttype) %(objectsize)'],cwd=root,
                                            input=''.join(oid+'\n' for oid,_ in objects),text=True)
            selected=[]
            for (oid,name),info in zip(objects,metadata.splitlines()):
                parts=info.split()
                if len(parts)==3 and parts[1]=='blob' and int(parts[2])<=10_000_000:
                    selected.append((oid,name))
            # Read one blob at a time from one Git process, including vendored history.
            process=subprocess.Popen(['git','cat-file','--batch'],cwd=root,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
            try:
                for oid,name in selected:
                    process.stdin.write((oid+'\n').encode()); process.stdin.flush()
                    header=process.stdout.readline().decode().split()
                    if len(header)!=3 or header[1]!='blob':
                        raise ValueError('Unexpected Git object')
                    content=process.stdout.read(int(header[2]));process.stdout.read(1)
                    blobs+=1
                    for match in matches(content):
                        findings.append({'scope':'history','file':name,'blob':oid,
                                         'vendor': 'node_modules/' in name, **match})
            finally:
                process.stdin.close();process.wait(timeout=30)
        except (subprocess.SubprocessError,ValueError) as exc:
            history_error = type(exc).__name__
    secrets = [r for r in findings if not r['kind'].startswith('contact_') and not r.get('vendor')]
    vendor_findings=[r for r in findings if r.get('vendor')]
    contacts = [r for r in findings if r['kind'].startswith('contact_') and not r.get('vendor') and r['file']!='frontend/package-lock.json']
    report = {'date':datetime.now(timezone.utc).isoformat(),'working_files_scanned':files,
              'history_blobs_scanned':blobs,'history_error':history_error,'findings':findings,
              'secret_findings':len(secrets),'contact_candidates':len(contacts),
              'automated_passed':not secrets and not contacts and not history_error,
              'vendor_or_dependency_examples':len(vendor_findings)+sum(r['file']=='frontend/package-lock.json' for r in findings),
              'ignored_local_inputs':sorted(p for p in ignored if p.endswith(('.json','.csv'))),
              'manual_review_required':True,
              'limitations':'Regex scans cannot prove that names, addresses or all personal data are synthetic. Ignored user PDF directories are not distributed or scanned by this source audit.'}
    out.mkdir(parents=True,exist_ok=True)
    (out/'privacy_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report
