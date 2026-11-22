"""spaCy skill extraction with a checked, reloadable model and dictionary fallback."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import logging
import os
from pathlib import Path
import re
import threading
from typing import Set

logger = logging.getLogger("scorer.ner_skills")
_MODEL_DIR = Path(__file__).resolve().parent / "models" / "resume_ner"
_CID = re.compile(r"\(cid:\d+\)")
_LOCK = threading.RLock()
_nlp = None
_load_failed = False
_loaded_signature = None


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CID.sub(" ", text)
    text = re.sub(r"([a-z])\n([a-z])", r"\1 \2", text, flags=re.I)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _model_path() -> Path:
    return Path(os.environ.get("NER_SKILLS_MODEL") or _MODEL_DIR).resolve()


def _signature() -> tuple:
    root = _model_path()
    files = sorted(path for path in root.rglob('*') if path.is_file()
                   and '__pycache__' not in path.parts)
    return (str(root), tuple((str(path.relative_to(root)), path.stat().st_mtime_ns,
                             path.stat().st_size) for path in files))


@lru_cache(maxsize=4)
def _hash_files(signature: tuple) -> tuple:
    root, files = signature
    return tuple((name, hashlib.sha256((Path(root) / name).read_bytes()).hexdigest())
                 for name, _, _ in files)


def model_file_hashes() -> dict:
    """Hash every effective model artifact, including weights and tokenizer."""
    return dict(_hash_files(_signature()))


def _load():
    global _nlp, _load_failed, _loaded_signature
    with _LOCK:
        if _load_failed:
            return None
        try:
            signature = _signature()
            if _nlp is not None and signature == _loaded_signature:
                return _nlp
            import spacy
            model = spacy.load(str(_model_path()))
            if 'ner' not in model.pipe_names or 'Skill' not in model.get_pipe('ner').labels:
                raise ValueError('Model must contain an NER component with the Skill label')
            _nlp, _loaded_signature = model, signature
        except Exception as exc:
            _nlp = None
            _load_failed = True
            logger.error("NER-модель недоступна: %s; используется словарь", exc)
        return _nlp


def ner_enabled() -> bool:
    env = os.environ.get("NER_SKILLS_ENABLED", "").strip().lower()
    if env in {"1", "true", "yes"}:
        return True
    if env in {"0", "false", "no"}:
        return False
    from .config import load_config
    return bool(load_config().get("ner_skills_enabled", False))


def ner_status() -> dict:
    enabled = ner_enabled()
    return {"enabled": enabled, "available": _load() is not None if enabled else False}


def ner_skill_mentions(text: str) -> list[tuple[str, int, int]]:
    """Recognise skills with offsets in the supplied text."""
    if not text or not text.strip():
        return []
    nlp = _load()
    if nlp is None:
        return []
    return [(entity.text.strip(), entity.start_char, entity.end_char)
            for entity in nlp(text).ents if entity.label_ == "Skill" and entity.text.strip()]


def ner_extract_skills(text: str) -> Set[str]:
    return {name for name, _, _ in ner_skill_mentions(_clean_text(text))} if text else set()


def _reset_for_tests() -> None:
    global _nlp, _load_failed, _loaded_signature
    with _LOCK:
        _nlp = None
        _load_failed = False
        _loaded_signature = None
        _hash_files.cache_clear()
