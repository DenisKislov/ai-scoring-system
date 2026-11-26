"""A-9/A-10: literal PMI metrics, no tuning, immutable PDF inputs."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import numpy as np
from scipy.stats import rankdata
from api.file_parser import extract_text_from_file
from api.logger import setup_logger, event
from db.builders import parse_raw_text_to_resume
from scorer import rank_candidates
from db.builders import vacancy_text
from scorer.metrics import ndcg, category_metrics
from scorer.skills import normalize_skill_set
from .dataset import verify

LIMITS = {'ndcg_at_10':.9, 'precision_at_5':.9, 'precision_at_10':.9,
          'recall_at_10':.15, 'spearman':.8}
logger = setup_logger('pmi.quality')


def write_quality_report(out: Path, name: str, report: dict, *, title: str) -> None:
    """Export the five quality criteria and the evidence for the technical check."""
    keys = ('date', 'started_at', 'finished_at', 'scope', 'dataset', 'metrics', 'criteria',
            'a10', 'passed', 'rankings', 'frozen_manifest', 'reference_fields_used_for_prediction',
            'parser_reference_fields_used_for_prediction')
    public = {key: report[key] for key in keys if key in report}
    (out / f'{name}.json').write_text(json.dumps(public, ensure_ascii=False, indent=2) + '\n')
    dataset = report['dataset']
    rows = [f'# {title}', '',
            f'Синтетический набор: {dataset["vacancies"]} вакансий, {dataset["resumes"]} резюме.', '',
            '| Метрика | Значение | Минимум ПМИ | Выполнено |', '|---|---:|---:|---|']
    for label, criterion in report['criteria'].items():
        value = criterion['value']
        display = '—' if value is None else f'{value:.4f}'
        status = 'да' if criterion['passed'] else 'нет'
        rows.append(f'| {label} | {display} | {criterion["minimum"]} | {status} |')
    a10 = 'пройдено' if report['a10']['passed'] else 'не пройдено'
    rows += ['', f'А-10: {a10}.']
    (out / f'{name}.md').write_text('\n'.join(rows) + '\n')


def experience_metrics(resumes, parsed):
    """Reference years are used only to measure extraction, never to rank."""
    rows = []
    for item in resumes:
        expected = item['experience_years']
        predicted = parsed[item['id']].get('experience_years')
        correct = (expected is None and predicted is None) or (
            expected is not None and predicted is not None and abs(expected-predicted) < .005)
        rows.append({'resume_id':item['id'], 'expected_years':expected,
                     'parsed_years':predicted, 'correct':correct})
    return {'ranking_source':'parsed_from_pdf', 'documents':len(rows),
            'correct':sum(r['correct'] for r in rows),
            'accuracy':sum(r['correct'] for r in rows)/len(rows) if rows else None,
            'missing_predictions':sum(r['parsed_years'] is None and r['expected_years'] is not None for r in rows),
            'rows':rows}


def sort_parsed_experience(ranked, parsed):
    """Use the production service order, including known zero before unknown."""
    for row in ranked:
        row['experience_years'] = parsed[row['candidate_id']].get('experience_years')
    ranked.sort(key=lambda r:(-r['score'], r['experience_years'] is None,
                             -(r['experience_years'] or 0), r['candidate_id']))


def summarize_rankings(dataset, rankings):
    """Measure supplied, already ordered predictions without touching their order."""
    labels = {(p['vacancy_id'],p['resume_id']):p['relevance'] for p in dataset['pairs']}
    expected_ids = {r['id'] for r in dataset['resumes']}
    per_query, zero_failures, traces = [], [], {}
    for vacancy in dataset['vacancies']:
        ranked = rankings[vacancy['id']]
        ids = [r['candidate_id'] for r in ranked]
        if len(ids) != len(expected_ids) or set(ids) != expected_ids:
            raise ValueError('Ranking must contain every frozen candidate exactly once')
        rel = [labels[vacancy['id'],rid] for rid in ids]
        metrics = ranking_metrics(rel, [r['score'] for r in ranked])
        per_query.append({'vacancy_id':vacancy['id'],'direction':vacancy['direction'], **metrics})
        strong = [r['score'] for r in ranked if labels[vacancy['id'],r['candidate_id']] >= .7]
        for row in ranked:
            if labels[vacancy['id'],row['candidate_id']] == 0 and (
                    row['score'] > 30 or (strong and row['score'] >= min(strong))):
                zero_failures.append({'vacancy_id':vacancy['id'],'resume_id':row['candidate_id'],
                                      'score':row['score'],'min_strong_score':min(strong) if strong else None})
        traces[vacancy['id']] = [
            {'resume_id':r['candidate_id'], 'score':r['score'],
             'parsed_experience_years':r.get('experience_years'), 'reference_relevance':relevance}
            for r,relevance in zip(ranked,rel)]
    metrics = {}
    for name in per_query[0]:
        if name in ['vacancy_id','direction']:
            continue
        values = [q[name] for q in per_query if q[name] is not None]
        metrics[name] = float(np.mean(values)) if values else None
    criteria = {k:{'value':metrics[k],'minimum':minimum,
                   'passed':metrics[k] is not None and metrics[k] >= minimum}
                for k,minimum in LIMITS.items()}
    a10 = {'passed':not zero_failures,'failures':zero_failures,
           'zero_pairs':sum(p['relevance']==0 for p in dataset['pairs']),
           'strong_pairs':sum(p['relevance']>=.7 for p in dataset['pairs'])}
    return {'metrics':metrics, 'criteria':criteria, 'a10':a10, 'queries':per_query,
            'rankings':traces,
            'passed':all(c['passed'] for c in criteria.values()) and a10['passed']}


def pmi_spearman(scores, relevance):
    """Formula (5) in the supplied PMI, with average ranks for ties.

    This literal simplified formula differs from scipy's Pearson correlation of
    tied ranks.
    """
    n = len(scores)
    if n < 2:
        return 0.0
    delta = rankdata(scores, method='average') - rankdata(relevance, method='average')
    return float(1 - 6 * np.sum(delta ** 2) / (n * (n*n - 1)))


def ranking_metrics(ordered_relevance, scores):
    relevance = list(ordered_relevance)
    positive = [r >= .1 for r in relevance]
    total = sum(positive)
    return {'ndcg_at_10':ndcg(relevance,10),
            'precision_at_5':sum(positive[:5])/5,
            'precision_at_10':sum(positive[:10])/10,
            'recall_at_10':sum(positive[:10])/total if total else None,
            'spearman':pmi_spearman(scores,relevance)}


def evaluate(root: Path, out: Path | None = None) -> dict:
    integrity = verify(root)
    if not integrity['ok']:
        raise ValueError('Frozen inputs changed: '+str(integrity['errors']))
    started = datetime.now(timezone.utc)
    dataset = json.loads((root/'dataset.json').read_text())
    predictions, texts, parsed = {}, {}, {}
    categories = defaultdict(lambda: {'tp':0,'fp':0,'fn':0})
    for kind in ['vacancies','resumes']:
        for item in dataset[kind]:
            path = root/item['file']
            text = extract_text_from_file(path.read_bytes(), path.name)
            texts[item['id']] = text
            parsed[item['id']] = parse_raw_text_to_resume(text)
            predictions[item['id']] = set(parsed[item['id']]['skills'])
            truth = item['skills'] if kind == 'vacancies' else item['text_skills']
            for cat, values in category_metrics(
                    predictions[item['id']], normalize_skill_set(set(truth))).items():
                bucket = categories[kind + ': ' + cat]
                for key in ['tp','fp','fn']:
                    bucket[key] += values[key]
    resumes = dataset['resumes']
    ids = [r['id'] for r in resumes]
    durations = {}
    all_ranked = {}
    for vacancy in dataset['vacancies']:
        t0 = time.perf_counter()
        event(logger, 'scoring_started', vacancy_id=vacancy['id'], pool_size=len(ids))
        scoring_text = texts[vacancy['id']]
        if dataset.get('scoring_input_contract') == 'pdf_upload':
            # Match api.routes._store_file -> db.builders.vacancy_text.
            scoring_text = vacancy_text({'title':Path(vacancy['file']).stem,
                'description':scoring_text,'skills':sorted(predictions[vacancy['id']])})
        ranked = rank_candidates(scoring_text, [texts[rid] for rid in ids],
            candidate_ids=ids, critical_skills=set(vacancy['critical_skills']),
            vacancy_skills=predictions[vacancy['id']],
            resume_skills_list=[predictions[rid] for rid in ids])
        sort_parsed_experience(ranked, parsed)
        duration = time.perf_counter()-t0
        event(logger, 'scoring_completed', vacancy_id=vacancy['id'], duration_seconds=duration)
        durations[vacancy['id']] = duration
        all_ranked[vacancy['id']] = ranked
    ranking = summarize_rankings(dataset,all_ranked)
    for query in ranking['queries']:
        query['ranking_seconds'] = durations[query['vacancy_id']]
    for values in categories.values():
        tp,fp,fn = (values[k] for k in ['tp','fp','fn'])
        p = tp/(tp+fp) if tp+fp else 0
        r = tp/(tp+fn) if tp+fn else 0
        values.update(precision=p,recall=r,f1=2*p*r/(p+r) if p+r else 0)
    criteria, a10 = ranking['criteria'], ranking['a10']
    report = {'protocol':'PMI_T1_1_v1', 'started_at':started.isoformat(),
        'finished_at':datetime.now(timezone.utc).isoformat(), 'relevance_threshold':.1,
        'scope':'PDF bytes -> extracted text -> extracted skills and experience -> unchanged Score -> ranking',
        'scoring_input_contract':dataset.get('scoring_input_contract','raw_pdf_text'),
        'dataset':{'version':dataset['version'],'vacancies':len(dataset['vacancies']),'resumes':len(resumes),'pairs':len(dataset['pairs']),
                   'directions':len({r['direction'] for r in resumes})},
        'frozen_manifest':json.loads((root/'manifest.json').read_text()),
        'skill_extraction_by_category':dict(categories),
        'experience_extraction':experience_metrics(resumes,parsed), **ranking}
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        write_quality_report(out, 'quality', report, title='Качество полного прогона из PDF')
    return report
