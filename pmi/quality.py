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
from scorer import extract_skills, rank_candidates
from scorer.metrics import ndcg, category_metrics
from scorer.skills import normalize_skill_set
from .dataset import verify

LIMITS = {'ndcg_at_10':.9, 'precision_at_5':.9, 'precision_at_10':.9,
          'recall_at_10':.15, 'spearman':.8}
logger = setup_logger('pmi.quality')


def pmi_spearman(scores, relevance):
    """Formula (5) in the supplied PMI, with average ranks for ties.

    This literal simplified formula differs from scipy's Pearson correlation of
    tied ranks. Both are recorded; the acceptance gate uses the PMI formula.
    """
    n = len(scores)
    if n < 2:
        return 0.0
    delta = rankdata(scores, method='average') - rankdata(relevance, method='average')
    return float(1 - 6 * np.sum(delta ** 2) / (n * (n*n - 1)))


def ranking_metrics(ordered_relevance, scores):
    from scorer.metrics import spearman
    relevance = list(ordered_relevance)
    positive = [r >= .1 for r in relevance]
    total = sum(positive)
    aps, found = [], 0
    for index, relevant in enumerate(positive, 1):
        if relevant:
            found += 1
            aps.append(found/index)
    return {'ndcg_at_10':ndcg(relevance,10),
            'precision_at_5':sum(positive[:5])/5,
            'precision_at_10':sum(positive[:10])/10,
            'recall_at_10':sum(positive[:10])/total if total else None,
            'spearman':pmi_spearman(scores,relevance),
            'spearman_tie_corrected':spearman(scores,relevance),
            'map':sum(aps)/total if total else 0,
            'mrr':next((1/i for i, r in enumerate(positive,1) if r),0)}


def evaluate(root: Path, out: Path) -> dict:
    integrity = verify(root)
    if not integrity['ok']:
        raise ValueError('Frozen inputs changed: '+str(integrity['errors']))
    started = datetime.now(timezone.utc)
    dataset = json.loads((root/'dataset.json').read_text())
    predictions, texts = {}, {}
    categories = defaultdict(lambda: {'tp':0,'fp':0,'fn':0})
    for kind in ['vacancies','resumes']:
        for item in dataset[kind]:
            path = root/item['file']
            text = extract_text_from_file(path.read_bytes(), path.name)
            texts[item['id']] = text
            predictions[item['id']] = set(parse_raw_text_to_resume(text)['skills'])
            truth = item['skills'] if kind == 'vacancies' else item['text_skills']
            for cat, values in category_metrics(
                    predictions[item['id']], normalize_skill_set(set(truth))).items():
                bucket = categories[kind + ': ' + cat]
                for key in ['tp','fp','fn']:
                    bucket[key] += values[key]
    labels = {(p['vacancy_id'],p['resume_id']):p['relevance'] for p in dataset['pairs']}
    resumes = dataset['resumes']
    ids = [r['id'] for r in resumes]
    years = {r['id']:r['experience_years'] for r in resumes}
    per_query, zero_failures = [], []
    all_ranked = {}
    for vacancy in dataset['vacancies']:
        t0 = time.perf_counter()
        event(logger, 'scoring_started', vacancy_id=vacancy['id'], pool_size=len(ids))
        ranked = rank_candidates(texts[vacancy['id']], [texts[rid] for rid in ids],
            candidate_ids=ids, critical_skills=set(vacancy['critical_skills']),
            vacancy_skills=predictions[vacancy['id']],
            resume_skills_list=[predictions[rid] for rid in ids])
        ranked.sort(key=lambda r:(-r['score'], -years[r['candidate_id']],r['candidate_id']))
        duration = time.perf_counter()-t0
        event(logger, 'scoring_completed', vacancy_id=vacancy['id'], duration_seconds=duration)
        rel = [labels[vacancy['id'],r['candidate_id']] for r in ranked]
        metrics = ranking_metrics(rel, [r['score'] for r in ranked])
        per_query.append({'vacancy_id':vacancy['id'],'direction':vacancy['direction'],
                          'ranking_seconds':duration, **metrics})
        strong = [r['score'] for r in ranked if labels[vacancy['id'],r['candidate_id']] >= .7]
        zero = [r for r in ranked if labels[vacancy['id'],r['candidate_id']] == 0]
        for r in zero:
            if r['score'] > 30 or (strong and r['score'] >= min(strong)):
                zero_failures.append({'vacancy_id':vacancy['id'],'resume_id':r['candidate_id'],
                                      'score':r['score'],'min_strong_score':min(strong) if strong else None})
        all_ranked[vacancy['id']] = ranked
    metrics = {}
    for name in per_query[0]:
        if name in ['vacancy_id','direction','ranking_seconds']:
            continue
        values = [q[name] for q in per_query if q[name] is not None]
        metrics[name] = float(np.mean(values)) if values else None
    for values in categories.values():
        tp,fp,fn = (values[k] for k in ['tp','fp','fn'])
        p = tp/(tp+fp) if tp+fp else 0
        r = tp/(tp+fn) if tp+fn else 0
        values.update(precision=p,recall=r,f1=2*p*r/(p+r) if p+r else 0)
    criteria = {k:{'value':metrics[k],'minimum':minimum,
                   'passed':metrics[k] is not None and metrics[k] >= minimum}
                for k,minimum in LIMITS.items()}
    a10 = {'passed':not zero_failures,'failures':zero_failures,
           'zero_pairs':sum(p['relevance']==0 for p in dataset['pairs']),
           'strong_pairs':sum(p['relevance']>=.7 for p in dataset['pairs'])}
    report = {'protocol':'PMI_T1_1_v1', 'started_at':started.isoformat(),
        'finished_at':datetime.now(timezone.utc).isoformat(), 'relevance_threshold':.1,
        'dataset':{'vacancies':len(per_query),'resumes':len(resumes),'pairs':len(labels),
                   'directions':len({r['direction'] for r in resumes})},
        'frozen_manifest':json.loads((root/'manifest.json').read_text()),
        'metrics':metrics,'criteria':criteria,'skill_extraction_by_category':dict(categories),
        'a10':a10,'queries':per_query, 'passed':all(c['passed'] for c in criteria.values()) and a10['passed']}
    out.mkdir(parents=True, exist_ok=True)
    (out/'quality.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    rows = ['# Качество по ПМИ', '', 'Порог релевантности: 0.1. Разметка: взвешенное покрытие скрытых навыков до рендеринга PDF.',
            'Контролируемая синтетика; результат не является оценкой отбора реальных людей.', '',
            '| Метрика | Значение | Минимум ПМИ | Результат |','|---|---:|---:|---|']
    rows += [f'| {name} | {c["value"]:.3f} | {c["minimum"]} | {"пройдено" if c["passed"] else "не пройдено"} |' for name,c in criteria.items()]
    rows += ['', f'А-10: {"пройдено" if a10["passed"] else "не пройдено"}; нарушений {len(zero_failures)} из {a10["zero_pairs"]} нулевых пар.',
             '', '## Извлечение навыков', '', '| Корпус и категория | TP | FP | FN | Precision | Recall | F1 |', '|---|---:|---:|---:|---:|---:|---:|']
    rows += [f'| {cat} | {c["tp"]} | {c["fp"]} | {c["fn"]} | {c["precision"]:.3f} | {c["recall"]:.3f} | {c["f1"]:.3f} |' for cat,c in sorted(categories.items())]
    rows += ['', '## Методика и ограничения', '',
             'nDCG использует линейный gain rel/log2(i+1). Spearman для приёмки рассчитан буквально по формуле (5) ПМИ со средними рангами; корреляция scipy с поправкой на связи записана отдельно в JSON.',
             'Recall усреднён по запросам, имеющим релевантные резюме. Навыки извлекаются из PDF, а не передаются из эталонных меток.',
             'Отдельный реалистичный генератор шести ИТ-направлений и реальные PDF/JSON остаются диагностическими наборами и оцениваются отдельно.']
    if not report['passed']:
        rows += ['', '## Анализ непройденных критериев', '',
                 'Ошибки возможны из-за пропущенных в тексте скрытых навыков, лишних словарных совпадений и широкой заменяемости технологий в семействах навыков. Требуется проверить независимую разметку, сузить семейства и улучшить словарь на отдельном обучающем наборе. Веса и метки после этого прогона не подбирались.']
    (out/'quality.md').write_text('\n'.join(rows)+'\n')
    return report
