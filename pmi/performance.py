"""A-16 local pipeline measurements. HTTP/container results are separate."""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import time
from api.file_parser import extract_text_from_file
from api.logger import event, setup_logger
from db.builders import parse_raw_text_to_resume
from scorer import rank_candidates, extract_skills

logger = setup_logger('pmi.performance')


def measure(root: Path, out: Path) -> dict:
    data = json.loads((root/'dataset.json').read_text())
    def parse(item):
        path = root/item['file']
        text = extract_text_from_file(path.read_bytes(),path.name)
        return text,set(parse_raw_text_to_resume(text)['skills'])
    elapsed = {}
    def timed(label, fn):
        event(logger,'performance_started',scenario=label)
        start = time.perf_counter()
        value = fn()
        elapsed[label] = time.perf_counter()-start
        event(logger,'performance_completed',scenario=label,duration_seconds=elapsed[label])
        return value
    timed('single_resume', lambda: parse(data['resumes'][0]))
    timed('batch_100', lambda: [parse(i) for i in data['resumes'][:100]])
    start_all = time.perf_counter()
    candidates = [parse(i) for i in data['resumes']]
    vacancies = [parse(i) for i in data['vacancies']]
    durations = []
    for v,(text,skills) in zip(data['vacancies'],vacancies):
        before = time.perf_counter()
        rank_candidates(text,[r[0] for r in candidates],vacancy_skills=skills,
                        resume_skills_list=[r[1] for r in candidates],
                        critical_skills=set(v['critical_skills']))
        durations.append(time.perf_counter()-before)
    elapsed['ranking_200_max'] = max(durations)
    elapsed['ten_vacancies_200_resumes'] = time.perf_counter()-start_all
    limits = {'single_resume':120,'batch_100':1800,'ranking_200_max':10,'ten_vacancies_200_resumes':3600}
    report = {'date':datetime.now(timezone.utc).isoformat(),'scope':'local parsing and scoring only; no DB/HTTP/container overhead',
              'host':{'os':platform.platform(),'machine':platform.machine()},
              'seconds':elapsed,'limits_seconds':limits,
              'passed':all(elapsed[k] <= limit for k,limit in limits.items()),
              'container_acceptance_completed':False}
    out.mkdir(parents=True,exist_ok=True)
    (out/'performance_local.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report
