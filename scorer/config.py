"""Versioned, file based algorithm settings shared by API and scorer workers."""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def config_path() -> Path:
    return Path(os.environ.get("ALGORITHM_CONFIG", ROOT / "config/algorithm.json"))


def load_config() -> dict:
    config = json.loads(config_path().read_text(encoding="utf-8"))
    validate_weights(config["weights"])
    critical = config['critical_weight']
    if type(critical) not in (int, float) or not math.isfinite(critical) or critical <= 1:
        raise ValueError("critical_weight must be finite and greater than one")
    return config


def validate_weights(weights: dict) -> dict:
    import math
    if set(weights) != {"keyword", "cosine"}:
        raise ValueError("weights must contain keyword and cosine")
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError("weights must be finite and nonnegative")
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9):
        raise ValueError("weights must sum to one")
    return weights


def dictionary_path() -> Path:
    configured = os.environ.get("SKILLS_DICTIONARY", load_config()["skill_dictionary"])
    path = Path(configured)
    return path if path.is_absolute() else ROOT / path


def algorithm_manifest() -> dict:
    config = load_config()
    files = [config_path(), dictionary_path(), ROOT / config["reference_corpus"],
             ROOT / "scorer/skills_auto.json", ROOT / "scorer/skills_auto_raw.json",
             ROOT / "scorer/skill_extractor.py", ROOT / "scorer/skill_families.py",
             ROOT / "scorer/scoring.py", ROOT / "scorer/normalize.py", ROOT / "scorer/privacy.py",
             ROOT / "scorer/skills.py", ROOT / "requirements.lock"]
    dependencies = {}
    for package in ["fastapi", "pydantic", "pymongo", "PyMuPDF", "scikit-learn", "numpy", "scipy", "razdel", "pymorphy3"]:
        try:
            dependencies[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            dependencies[package] = "unavailable"
    hashes = {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else p.name:
              hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.exists()}
    fingerprint = hashlib.sha256(json.dumps({"config":config,"hashes":hashes,"dependencies":dependencies},sort_keys=True).encode()).hexdigest()
    return {**config, "file_hashes": hashes, "dependencies": dependencies, "fingerprint": fingerprint}
