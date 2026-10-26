"""Local scoring for development; the same kernel via HTTP in Compose."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from http.client import HTTPException
from pydantic import TypeAdapter, ValidationError
from api.schemas import ScoreResult
from .scoring import rank_candidates


class ScorerUnavailable(RuntimeError):
    pass


def rank(**payload):
    base = os.environ.get('SCORER_URL')
    if not base:
        return rank_candidates(**payload)
    serializable = {k: [list(s) for s in v] if k == 'resume_skills_list' and v is not None
                    else list(v) if isinstance(v, set) else v for k, v in payload.items()}
    request = Request(base.rstrip('/') + '/rank', data=json.dumps(serializable).encode(),
                      headers={'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=float(os.environ.get('SCORER_TIMEOUT', '30'))) as response:
            result = json.load(response)['results']
            TypeAdapter(list[ScoreResult]).validate_python(result)
            if len(result) != len(payload['candidate_texts']):
                raise ValueError('Incomplete scorer response')
            ids = payload.get('candidate_ids')
            if ids is not None and {r.get('candidate_id') for r in result} != set(ids):
                raise ValueError('Unexpected candidate IDs')
            return result
    except (URLError, HTTPError, OSError, HTTPException, ValueError, KeyError, TypeError, ValidationError) as exc:
        raise ScorerUnavailable('Сервис скоринга временно недоступен') from exc
