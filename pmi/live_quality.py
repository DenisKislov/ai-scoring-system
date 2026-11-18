"""Acceptance metrics computed from actual HTTP uploads and service rankings."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

from scorer.metrics import category_metrics
from scorer.skills import normalize_skill_set
from .quality import experience_metrics, summarize_rankings


def evaluate_api_outputs(data, documents, rankings, output: Path):
    """IDs already map back to frozen IDs; never re-sort HTTP response rows."""
    report = summarize_rankings(data,rankings)
    categories = defaultdict(lambda:{'tp':0,'fp':0,'fn':0})
    micro = {}
    predictions = {}
    for kind in ['vacancies','resumes']:
        for item in data[kind]:
            doc = documents[item['id']]
            predictions[item['id']] = {'skills':sorted(doc['skills']),
                'experience_years':doc.get('experience_years')}
            truth = item['skills'] if kind == 'vacancies' else item['text_skills']
            for category,counts in category_metrics(set(doc['skills']),normalize_skill_set(set(truth))).items():
                bucket = categories[kind+': '+category]
                for name in ['tp','fp','fn']:
                    bucket[name] += counts[name]
        counts = {name:sum(c[name] for cat,c in categories.items() if cat.startswith(kind+': '))
                  for name in ['tp','fp','fn']}
        micro[kind] = counts
    for counts in [*categories.values(),*micro.values()]:
        tp,fp,fn = (counts[name] for name in ['tp','fp','fn'])
        precision = tp/(tp+fp) if tp+fp else 0
        recall = tp/(tp+fn) if tp+fn else 0
        counts.update(precision=precision,recall=recall,
                      f1=2*precision*recall/(precision+recall) if precision+recall else 0)
    report.update(date=datetime.now(timezone.utc).isoformat(),
        scope='PDF multipart HTTP upload -> PyMuPDF -> production extraction -> MongoDB -> separate scoring service -> saved ranking',
        reference_fields_used_for_prediction=['HR critical skill selection only'],
        parser_reference_fields_used_for_prediction=False,
        skill_extraction_by_category=dict(categories),skill_extraction_micro=micro,
        experience_extraction=experience_metrics(data['resumes'],documents),
        parser_predictions=predictions,
        dataset={'version':data['version'],'vacancies':len(data['vacancies']),
                 'resumes':len(data['resumes']),'pairs':len(data['pairs'])})
    output.mkdir(parents=True,exist_ok=True)
    (output/'quality_api.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines = ['# Качество полного пути через API','','Все входные документы загружены как PDF. '
             'Навыки и стаж взяты из сохранённых результатов парсера. Порядок получен от сервиса без пересортировки по эталону.',
             '', '| Метрика | Значение | Минимум ПМИ | Выполнено |','|---|---:|---:|---|']
    lines += [f'| {name} | {c["value"]:.6f} | {c["minimum"]} | {"да" if c["passed"] else "нет"} |'
              for name,c in report['criteria'].items()]
    lines += ['', '| Извлечение | Precision | Recall | F1 |','|---|---:|---:|---:|']
    lines += [f'| {kind} | {c["precision"]:.6f} | {c["recall"]:.6f} | {c["f1"]:.6f} |'
              for kind,c in micro.items()]
    exp = report['experience_extraction']
    lines += ['',f'Стаж: {exp["correct"]}/{exp["documents"]} правильных результатов.',
              f'А-10: {"пройдено" if report["a10"]["passed"] else "не пройдено"}.',
              '', 'Результат относится только к новому контролируемому синтетическому набору. '
              'Он не подтверждает прежний эксперимент SuperJob, точность на реальных людях или формальное принятие шаблона PDF комиссией.']
    (output/'quality_api.md').write_text('\n'.join(lines)+'\n')
    return report
