"""Acceptance metrics computed from actual HTTP uploads and service rankings."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from scorer.metrics import category_metrics
from scorer.skills import normalize_skill_set
from .quality import experience_metrics, summarize_rankings, write_quality_report


def evaluate_api_outputs(data, documents, rankings, output: Path | None = None):
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
    if output is not None:
        output.mkdir(parents=True,exist_ok=True)
        write_quality_report(output, 'quality_api', report, title='Качество полного прогона через API')
    return report
