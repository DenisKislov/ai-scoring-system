"""Refresh uploaded resumes and vacancies from stored text, preserving HR history.

Use --dry-run first. Run the applying migration while the API is stopped so a
concurrent scoring request cannot persist a result computed from old skills.
Imported/annotated corpora are excluded unless --all-sources is explicit.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from db import mongo  # noqa: E402
from scorer import extract_skills  # noqa: E402
from scorer.config import algorithm_manifest  # noqa: E402
from scorer.skills import normalize_skill_set  # noqa: E402


def backfill(*, dry_run: bool = True, all_sources: bool = False,
             limit: int | None = None, kind: str = 'resumes') -> dict:
    if kind not in {'resumes', 'vacancies', 'both'}:
        raise ValueError('kind must be resumes, vacancies or both')
    if limit is not None and limit < 1:
        raise ValueError('limit must be positive')
    fingerprint = algorithm_manifest()['fingerprint']
    summary = {'dry_run': dry_run, 'updated': 0, 'unchanged': 0,
               'conflicts': 0, 'skills_added': 0, 'skills_removed': 0, 'plan': []}
    kinds = ('resumes', 'vacancies') if kind == 'both' else (kind,)
    for document_kind in kinds:
        is_resume = document_kind == 'resumes'
        collection = mongo._coll(mongo.COLL_RESUMES if is_resume else mongo.COLL_VACANCIES)
        text_field = '_raw_text' if is_resume else 'description'
        query = {text_field: {'$exists': True, '$type': 'string', '$ne': ''}}
        if not all_sources:
            query['_source'] = 'user_upload'
        for doc in collection.find(query).limit(limit or 0):
            old = set(doc.get('skills') or [])
            new = extract_skills(doc[text_field])
            if not is_resume:
                # Critical requirements explicitly selected by HR are retained.
                new |= normalize_skill_set(set(doc.get('critical_skills') or []))
            if new == old:
                summary['unchanged'] += 1
                continue
            added, removed = sorted(new - old), sorted(old - new)
            record = {'kind': document_kind, 'id': str(doc['_id']),
                      'title': doc.get('title') or doc.get('filename') or '',
                      'added': added, 'removed': removed,
                      'old_count': len(old), 'new_count': len(new)}
            if not dry_run:
                if algorithm_manifest()['fingerprint'] != fingerprint:
                    raise RuntimeError('Алгоритм изменился во время пересчёта; повторите миграцию')
                # Clear before mutation, so a partially failed migration is safe to retry.
                field = 'resume_id' if is_resume else 'vacancy_id'
                mongo._coll(mongo.COLL_SCORES).delete_many({field: str(doc['_id'])})
                condition = {'_id': doc['_id'], text_field: doc[text_field], 'skills': doc.get('skills')}
                if not is_resume:
                    condition['critical_skills'] = doc.get('critical_skills')
                result = collection.update_one(condition, {'$set': {
                    'skills': sorted(new), 'tags': sorted(new),
                    'extraction_fingerprint': fingerprint}})
                if not result.matched_count:
                    summary['conflicts'] += 1
                    continue
            summary['updated'] += 1
            summary['skills_added'] += len(added)
            summary['skills_removed'] += len(removed)
            summary['plan'].append(record)
    return summary


def main(argv=None) -> int:
    import json
    parser = argparse.ArgumentParser(description='Пересчёт навыков загруженных документов')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--all-sources', action='store_true')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--kind', choices=('resumes', 'vacancies', 'both'), default='both')
    args = parser.parse_args(argv)
    summary = backfill(dry_run=args.dry_run, all_sources=args.all_sources,
                       limit=args.limit, kind=args.kind)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary['conflicts'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
