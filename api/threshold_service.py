"""Persist a versioned display threshold calibrated without ground-truth labels."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
from typing import Optional

from db import mongo
from scorer.config import ROOT, algorithm_manifest
from scorer.auto_threshold import METHOD, compute_dataset_threshold

logger = logging.getLogger('api.threshold')
CONFIG_COLLECTION = 'system_config'
THRESHOLD_DOC_ID = 'skill_overlap_threshold'
_DATASET_DIRS = (ROOT / 'data/benchmark', ROOT / 'data')


def _config_coll():
    return mongo._coll(CONFIG_COLLECTION)


def get_threshold_doc() -> Optional[dict]:
    doc = _config_coll().find_one({'_id': THRESHOLD_DOC_ID})
    if not doc or doc.get('method') != METHOD:
        return None
    if doc.get('algorithm_fingerprint') != algorithm_manifest()['fingerprint']:
        return None
    return doc


def get_threshold_value() -> Optional[float]:
    doc = get_threshold_doc()
    return float(doc['value']) if doc else None


def recompute_threshold(*, force: bool = False) -> dict:
    existing = get_threshold_doc()
    if existing and not force:
        return existing
    dataset = next((root for root in _DATASET_DIRS if all(
        (root / name).is_file() for name in ('superjob_dataset.json', 'dataset_resume.json'))), None)
    if dataset is None:
        raise FileNotFoundError('JSON для расчёта порога не найдены')
    paths = [dataset / name for name in ('superjob_dataset.json', 'dataset_resume.json')]
    manifest = algorithm_manifest()
    value, n_vacancies, n_resumes = compute_dataset_threshold(*paths)
    if algorithm_manifest()['fingerprint'] != manifest['fingerprint']:
        raise ValueError('Конфигурация изменилась во время расчёта порога; повторите расчёт')
    doc = {'_id': THRESHOLD_DOC_ID, 'value': value, 'method': METHOD,
           'algorithm_fingerprint': manifest['fingerprint'],
           'updated_at': datetime.now(timezone.utc).isoformat(),
           'source_vacancies': str(paths[0]), 'source_resumes': str(paths[1]),
           'dataset_hashes': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
           'n_vacancies': n_vacancies, 'n_resumes': n_resumes}
    _config_coll().replace_one({'_id': THRESHOLD_DOC_ID}, doc, upsert=True)
    logger.info('Порог отображения %.3f по %d вакансиям и %d резюме', value, n_vacancies, n_resumes)
    return doc


def ensure_threshold_initialized() -> None:
    try:
        recompute_threshold()
    except Exception as exc:
        logger.warning('Порог недоступен, фильтр отключён: %s', exc)
