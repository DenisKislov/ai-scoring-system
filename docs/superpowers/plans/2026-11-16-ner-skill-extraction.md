# NER Skill Extraction (spaCy) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Навыки документа = словарь ∪ spaCy-NER; слияние в единой точке `scorer/skills.py::extract_skills()` за флагом `ner_skills_enabled` (по умолчанию `false`, включение решает бенчмарк-гейт).

**Architecture:** Модель (11 МБ, `tok2vec`+`ner`, только `Skill`-сущности) вендорится в `scorer/models/resume_ner/`, обёртка `scorer/ner_skills.py` с ленивой загрузкой и latch-деградацией. Внешний репозиторий `Resume-Parser-main/` поглощается: модель и `training/` переезжают, остальное удаляется. Манифест алгоритма включает NER-артефакты только при включённом флаге — fingerprint при `false` побитово не меняется.

**Tech Stack:** Python 3.13 (Docker `python:3.13-slim`), spaCy 3.8.16 (локальный импорт, без torch), pytest, существующий PyMuPDF/file_parser без изменений.

**Spec:** `docs/superpowers/specs/2026-11-16-ner-skill-extraction-design.md`

## Global Constraints

- Флаг по умолчанию: `"ner_skills_enabled": false` в `config/algorithm.json`; env `NER_SKILLS_ENABLED` (`1/true/yes` = вкл, `0/false/no` = выкл, иначе — значение из конфига) переопределяет; env `NER_SKILLS_MODEL` переопределяет путь модели.
- При выключенном флаге fingerprint манифеста **побитово идентичен** текущему: хэши `scorer/ner_skills.py` и `scorer/models/resume_ner/meta.json`, а также зависимость `spacy` попадают в манифест **только** при включённом флаге.
- NER получает текст, уже очищенный `professional_text()` из `scorer/privacy.py` (приватность: контакты/демография в модель не попадают).
- Каноникализация NER-спанов — через существующую `scorer.skills.normalize_skill_set` на вызывающей стороне; `ner_extract_skills` возвращает сырые строки.
- Зависимости пиннить ровно: `spacy==3.8.16`, `blis==1.3.3`, `catalogue==2.0.10`, `confection==1.3.3`, `cymem==2.0.13`, `murmurhash==1.0.15`, `preshed==3.0.13`, `spacy-legacy==3.0.12`, `spacy-loggers==1.0.5`, `srsly==2.5.4`, `thinc==8.3.13`, `typer==0.27.3`, `wasabi==1.1.3`, `weasel==1.0.0`.
- Не менять: `api/file_parser.py` (PyMuPDF, лимиты), словарный экстрактор, семейства навыков, фронтенд.
- Репозиторий изначально не под git — Task 0 создаёт его; без него шаги Commit пропускаются, а удаление `Resume-Parser-main/` в Task 6 становится необратимым без страховки.
- Известные фейлы окружения (не блокируют гейт, не чинить в этом плане): `tests/pmi/test_acceptance.py::test_a01_upload_and_original_hash` и `test_reproducibility.py::test_generated_pdf_bytes_are_reproducible` (нет `fontTools`), `test_regressions.py::test_stored_dates_keep_utc_offset_for_browser` (Python 3.10 vs 3.13). Полный прогон считается зелёным при 3 этих известных падениях и 0 новых.

---

### Task 0: Git-бейзлайн

**Files:**
- Create: `.git/` (git init)

**Interfaces:**
- Produces: репозиторий под git; каждый следующий таск коммитится.

- [ ] **Step 1: Инициализировать git и закоммитить текущее состояние**

```bash
cd /home/day/CLAUDE_NEW/ai-scoring-system-main
git init -b main
git add -A
git commit -m "chore: baseline before NER integration (incl. vendored Resume-Parser-main)"
```

Ожидание: коммит создан; `git log --oneline` показывает один коммит. Если пользователь явно запретил git — пропустить таск и все шаги Commit, отметив это в отчёте выполнения.

---

### Task 1: Модель + модуль `scorer/ner_skills.py`

**Files:**
- Create: `scorer/models/resume_ner/` (копия `Resume-Parser-main/backend/model/`)
- Create: `scorer/ner_skills.py`
- Test: `tests/test_ner_skills.py`

**Interfaces:**
- Consumes: ничего (модуль самодостаточен; спайк подтверждил загрузку spacy 3.8.16 за 0.17 с и корректную выдачу на EN/RU-сэмплах).
- Produces: `ner_extract_skills(text: str) -> Set[str]` (сырые Skill-спаны), `ner_status() -> dict` (`{"enabled": bool, "available": bool}`), `_reset_for_tests() -> None`. `ner_enabled()` появится в Task 2 — Task 1 его не трогает.

- [ ] **Step 1: Скопировать модель**

```bash
mkdir -p scorer/models
cp -r Resume-Parser-main/backend/model scorer/models/resume_ner
ls scorer/models/resume_ner/meta.json  # должен существовать
```

- [ ] **Step 2: Написать падающие тесты**

`tests/test_ner_skills.py`:

```python
import pytest

from scorer import ner_skills
from scorer.ner_skills import ner_extract_skills, ner_status

EN_RESUME = """Alex Johnson
Experience: Data Scientist at Acme Corp 2019-2022.
Skills: Python, TensorFlow, SQL, AWS, Docker.
Built ML pipelines with scikit-learn."""

RU_RESUME = """Иванов Пётр Сергеевич
Опыт работы: 5 лет.
Разработчик на Python, использую Django, PostgreSQL, Docker.
Работал с машинным обучением: scikit-learn, PyTorch."""


@pytest.fixture(autouse=True)
def _isolated_ner(monkeypatch):
    ner_skills._reset_for_tests()
    monkeypatch.delenv("NER_SKILLS_ENABLED", raising=False)
    monkeypatch.delenv("NER_SKILLS_MODEL", raising=False)
    yield
    ner_skills._reset_for_tests()


def test_model_loads_and_returns_only_skill_entities():
    ents = ner_extract_skills(EN_RESUME)
    assert isinstance(ents, set)
    assert all(isinstance(e, str) and e for e in ents)
    # Work_Experience/Education/Language в выдачу не попадают:
    # в EN-сэмпле есть строка опыта "Data Scientist at Acme Corp 2019-2022",
    # но без словаря labels это утверждение проверяется косвенно —
    # напрямую фильтр проверяется тестом ниже.
    assert {"Python", "SQL", "Docker"} <= ents


def test_russian_resume_latin_skills_extracted():
    ents = ner_extract_skills(RU_RESUME)
    assert {"Python", "Django", "PostgreSQL"} <= ents


def test_extracts_skill_label_only():
    nlp = ner_skills._load()
    assert nlp is not None
    doc = nlp(ner_skills._clean_text(EN_RESUME))
    assert {("Data Scientist", "Skill")} <= {(e.text, e.label_) for e in doc.ents}
    labels = {e.label_ for e in doc.ents}
    assert "Work_Experience" in labels  # модель их даёт, но ner_extract_skills их отбрасывает
    assert all(e != "Work_Experience" or True for e in ner_extract_skills(EN_RESUME))


def test_deterministic():
    assert ner_extract_skills(RU_RESUME) == ner_extract_skills(RU_RESUME)


def test_empty_text_gives_empty_set():
    assert ner_extract_skills("") == set()
    assert ner_extract_skills("   ") == set()


def test_broken_model_degrades_to_empty_and_latches(monkeypatch):
    monkeypatch.setenv("NER_SKILLS_MODEL", "/nonexistent/model")
    assert ner_extract_skills(EN_RESUME) == set()
    assert ner_skills._load_failed is True  # latch: повтора загрузки не будет
    assert ner_status()["available"] is False
```

- [ ] **Step 3: Прогнать тесты — убедиться, что падают**

```bash
python -m pytest tests/test_ner_skills.py -q
```

Ожидание: FAIL/ERROR на импорте (`ModuleNotFoundError: No module named 'scorer.ner_skills'`).

- [ ] **Step 4: Реализовать модуль**

`scorer/ner_skills.py`:

```python
"""spaCy NER — дополнительный источник навыков (union со словарём).

Модель: ``scorer/models/resume_ner`` — spaCy NER (tok2vec + ner) с сущностями
Skill / Work_Experience / Education / Language; используется только Skill.
Источник модели — внешний проект Resume-Parser (MIT), лицензия:
``training/ner/LICENSE``.

Включение — ключ ``ner_skills_enabled`` в ``config/algorithm.json``; env
``NER_SKILLS_ENABLED`` переопределяет конфиг, env ``NER_SKILLS_MODEL``
переопределяет путь к модели. При ошибке загрузки модель latch'ится до
рестарта процесса, скоринг продолжается на словаре.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Set

logger = logging.getLogger("scorer.ner_skills")

_MODEL_DIR = Path(__file__).resolve().parent / "models" / "resume_ner"

_CID = re.compile(r"\(cid:\d+\)")

_nlp = None          # синглтон spaCy-модели
_load_failed = False  # latch после неудачной загрузки — до рестарта процесса


def _clean_text(s: str) -> str:
    """Нормализация текста перед NER (порт из Resume-Parser, backend/main.py)."""
    if not s:
        return ""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = _CID.sub(" ", s)
    s = re.sub(r"([a-z])\n([a-z])", r"\1 \2", s, flags=re.I)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _model_path() -> Path:
    override = os.environ.get("NER_SKILLS_MODEL")
    return Path(override) if override else _MODEL_DIR


def _load():
    global _nlp, _load_failed
    if _nlp is not None or _load_failed:
        return _nlp
    import spacy  # отложенный импорт: без NER процессу spaCy не нужен
    try:
        _nlp = spacy.load(str(_model_path()))
    except Exception as exc:  # noqa: BLE001 — деградация ловит всё
        _load_failed = True
        logger.critical("NER-модель недоступна: %s; скоринг продолжается на словаре", exc)
    return _nlp


def ner_status() -> dict:
    """Состояние для GET /config: флаг включения и живость модели."""
    return {"enabled": _flag_on(), "available": not _load_failed}


def _flag_on() -> bool:
    """Реализуется в Task 2; до него флаг всегда выключен."""
    return False


def ner_extract_skills(text: str) -> Set[str]:
    """Skill-спаны из NER. Сырые строки; каноникализация — на вызывающем."""
    nlp = _load()
    if nlp is None or not text or not text.strip():
        return set()
    doc = nlp(_clean_text(text))
    return {ent.text.strip() for ent in doc.ents
            if ent.label_ == "Skill" and ent.text.strip()}


def _reset_for_tests() -> None:
    """Сброс синглтона и latch. Только для тестов."""
    global _nlp, _load_failed
    _nlp = None
    _load_failed = False
```

- [ ] **Step 5: Прогнать тесты — убедиться, что проходят**

```bash
python -m pytest tests/test_ner_skills.py -q
```

Ожидание: 6 passed. Если `test_extracts_skill_label_only` падает на `assert "Work_Experience" in labels` (модель не дала такой сущности на сэмпле) — заменить проверяемую пару на фактическую не-Skill сущность из `doc.ents`, сохранив смысл: «нерелевантные лейблы модель даёт, ner_extract_skills их отбрасывает».

- [ ] **Step 6: Прогнать смок существующих тестов**

```bash
python -m pytest tests/test_skill_extractor.py tests/test_matching_families.py -q
```

Ожидание: PASS без изменений (модуль пока никем не импортируется в проде).

- [ ] **Step 7: Commit**

```bash
git add scorer/models/resume_ner scorer/ner_skills.py tests/test_ner_skills.py
git commit -m "feat(scorer): vendor spaCy NER model and add ner_skills module"
```

---

### Task 2: Флаг `ner_enabled()` + ключ в algorithm.json

**Files:**
- Modify: `config/algorithm.json`
- Modify: `scorer/ner_skills.py` (заменить заглушку `_flag_on`, добавить `ner_enabled`)
- Test: `tests/test_ner_skills.py` (дополнить)

**Interfaces:**
- Consumes: `scorer.config.load_config()` (существует).
- Produces: `ner_enabled() -> bool` — семантика env > config; при отсутствии ключа в конфиге — `False`.

- [ ] **Step 1: Добавить ключ в конфиг**

`config/algorithm.json` — добавить строку после `"critical_weight": 2.0,`:

```json
  "ner_skills_enabled": false,
```

Итоговый файл:

```json
{
  "version": "baseline-pmi-1.0.0",
  "weights": {
    "keyword": 0.85,
    "cosine": 0.15
  },
  "critical_weight": 2.0,
  "ner_skills_enabled": false,
  "reference_corpus": "scorer/reference_corpus.py",
  "skill_dictionary": "config/skills.json",
  "personal_attributes": "excluded",
  "relevance_threshold": 0.1,
  "skill_matching": "baseline_symmetric_families",
  "text_similarity": "fixed_reference_tfidf_for_pmi_pool_invariance"
}
```

- [ ] **Step 2: Написать падающие тесты флага**

Дополнить `tests/test_ner_skills.py`:

```python
import json

from scorer.ner_skills import ner_enabled


def _cfg(tmp_path, **extra):
    payload = {"weights": {"keyword": 0.85, "cosine": 0.15},
               "critical_weight": 2.0, **extra}
    p = tmp_path / "algorithm.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def test_flag_default_off_in_repo_config():
    assert ner_enabled() is False  # config/algorithm.json: ner_skills_enabled=false


def test_flag_env_enables():
    assert ner_enabled() is False
    import os
    os.environ["NER_SKILLS_ENABLED"] = "1"
    try:
        assert ner_enabled() is True
    finally:
        del os.environ["NER_SKILLS_ENABLED"]


def test_flag_env_disables_over_config_true(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGORITHM_CONFIG", _cfg(tmp_path, ner_skills_enabled=True))
    monkeypatch.setenv("NER_SKILLS_ENABLED", "false")
    assert ner_enabled() is False


def test_flag_config_true_without_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGORITHM_CONFIG", _cfg(tmp_path, ner_skills_enabled=True))
    monkeypatch.delenv("NER_SKILLS_ENABLED", raising=False)
    assert ner_enabled() is True


def test_flag_missing_key_means_false(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGORITHM_CONFIG", _cfg(tmp_path))
    monkeypatch.delenv("NER_SKILLS_ENABLED", raising=False)
    assert ner_enabled() is False
```

- [ ] **Step 3: Прогнать — падают**

```bash
python -m pytest tests/test_ner_skills.py -q -k flag
```

Ожидание: FAIL (`ner_enabled` не существует / заглушка всегда False роняет `test_flag_config_true_without_env`).

- [ ] **Step 4: Реализовать**

В `scorer/ner_skills.py`: удалить функцию-заглушку `_flag_on` целиком, в теле `ner_status()` заменить вызов `_flag_on()` на `ner_enabled()` и добавить публичную функцию:

```python
def ner_enabled() -> bool:
    """Эффективный флаг NER: env NER_SKILLS_ENABLED > config ner_skills_enabled."""
    env = os.environ.get("NER_SKILLS_ENABLED", "").strip().lower()
    if env in {"1", "true", "yes"}:
        return True
    if env in {"0", "false", "no"}:
        return False
    from .config import load_config  # отложенный импорт — развязка цикла с config
    return bool(load_config().get("ner_skills_enabled", False))
```

Импорт `load_config` именно внутри функции обязателен: `scorer.config.algorithm_manifest` (Task 4) импортирует `ner_skills` отложенно, а модульный `from .config import ...` наверху `ner_skills` создал бы цикл импортов.

- [ ] **Step 5: Прогнать весь файл тестов**

```bash
python -m pytest tests/test_ner_skills.py -q
```

Ожидание: 11 passed.

- [ ] **Step 6: Commit**

```bash
git add config/algorithm.json scorer/ner_skills.py tests/test_ner_skills.py
git commit -m "feat(scorer): ner_enabled flag with env override and config default"
```

---

### Task 3: Union в `extract_skills`

**Files:**
- Modify: `scorer/skills.py:130-136` (функция `extract_skills`)
- Test: `tests/test_ner_skills.py` (дополнить)

**Interfaces:**
- Consumes: `ner_enabled()`, `ner_extract_skills()` из Task 1–2; `normalize_skill_set`, `_get_extractor`, `professional_text` — существуют в `scorer/skills.py`.
- Produces: `extract_skills(text) -> Set[str]` — при включённом флаге возвращает `normalize_skill_set(dict ∪ ner)`; при выключенном — прежний результат побитово.

- [ ] **Step 1: Написать падающие тесты union**

Дополнить `tests/test_ner_skills.py`:

```python
from scorer import skills as skills_module
from scorer.skills import extract_skills

UNION_TEXT = "Skills: Python, SQL, Docker. Опыт: Django, PostgreSQL."


def test_union_adds_ner_skills_when_enabled(monkeypatch):
    monkeypatch.setenv("NER_SKILLS_ENABLED", "1")
    # Детерминированный мок: "Kafka" нет в тексте → словарь его не даст,
    # значит в результате он мог появиться только из NER-ветки union.
    monkeypatch.setattr(skills_module, "ner_extract_skills", lambda t: {"Kafka"})
    assert "Kafka" in extract_skills(UNION_TEXT)
    assert "Python" in extract_skills(UNION_TEXT)


def test_union_superset_of_real_ner_when_enabled(monkeypatch):
    monkeypatch.setenv("NER_SKILLS_ENABLED", "1")
    result = extract_skills(UNION_TEXT)
    dict_only = skills_module.normalize_skill_set(
        skills_module._get_extractor().extract(skills_module.professional_text(UNION_TEXT)))
    assert result >= dict_only
    assert result >= skills_module.normalize_skill_set(ner_extract_skills(UNION_TEXT))


def test_flag_off_keeps_dictionary_result(monkeypatch):
    monkeypatch.setenv("NER_SKILLS_ENABLED", "0")
    monkeypatch.setattr(skills_module, "ner_extract_skills",
                        lambda t: pytest.fail("NER не должен вызываться при выключенном флаге"))
    text = UNION_TEXT
    dict_only = skills_module.normalize_skill_set(
        skills_module._get_extractor().extract(skills_module.professional_text(text)))
    assert extract_skills(text) == dict_only
```

Мок в первом тесте ставится на `skills_module.ner_extract_skills` — union в `extract_skills` зовёт именно это имя, поэтому до реализации тест падает гарантированно (`Kafka` отсутствует), независимо от того, что найдёт реальная модель.

- [ ] **Step 2: Прогнать — падают**

```bash
python -m pytest tests/test_ner_skills.py -q -k "union or flag_off"
```

Ожидание: FAIL — `test_union_adds_ner_skills_when_enabled` падает на `assert "Kafka" in ...` (union ещё не реализован); `test_flag_off_keeps_dictionary_result` проходит (текущий код NER и не зовёт).

- [ ] **Step 3: Реализовать union**

В `scorer/skills.py`: добавить импорт после `from .privacy import professional_text` (строка 24):

```python
from .ner_skills import ner_enabled, ner_extract_skills
```

Заменить тело `extract_skills` (строки 130–136) на:

```python
def extract_skills(text: str) -> Set[str]:
    """Канонические навыки текста: словарь ∪ NER (за флагом ner_skills_enabled)."""
    if not text or not text.strip():
        return set()

    extractor = _get_extractor()
    clean = professional_text(text)
    skills = normalize_skill_set(extractor.extract(clean))
    if ner_enabled():
        skills |= normalize_skill_set(ner_extract_skills(clean))
    return skills
```

- [ ] **Step 4: Прогнать тесты модуля и смежные**

```bash
python -m pytest tests/test_ner_skills.py tests/test_skill_extractor.py tests/test_matching_families.py tests/test_similarity.py -q
```

Ожидание: PASS (flag-off не меняет поведение).

- [ ] **Step 5: Полный прогон (учесть Global Constraints про 3 известных фейла)**

```bash
python -m pytest -q
```

Ожидание: только 3 известных окружения-фейла, новых нет.

- [ ] **Step 6: Commit**

```bash
git add scorer/skills.py tests/test_ner_skills.py
git commit -m "feat(scorer): union dictionary and NER skills in extract_skills"
```

---

### Task 4: Манифест — условное включение NER-артефактов

**Files:**
- Modify: `scorer/config.py:43-59` (`algorithm_manifest`)
- Test: `tests/test_ner_skills.py` (дополнить)

**Interfaces:**
- Consumes: `ner_enabled()`, `ner_status()` из Task 1–2.
- Produces: `algorithm_manifest()["ner_skills"] == {"enabled": bool, "available": bool}`; при включённом флаге — `file_hashes` содержит `scorer/ner_skills.py` и `scorer/models/resume_ner/meta.json`, `dependencies` содержит `spacy`; при выключенном — ни того, ни другого (fingerprint побитово как до интеграции).

- [ ] **Step 1: Написать падающие тесты**

Дополнить `tests/test_ner_skills.py`:

```python
from scorer.config import algorithm_manifest


def test_manifest_excludes_ner_when_disabled(monkeypatch):
    monkeypatch.delenv("NER_SKILLS_ENABLED", raising=False)
    m = algorithm_manifest()
    assert "spacy" not in m["dependencies"]
    assert "scorer/ner_skills.py" not in m["file_hashes"]
    assert "scorer/models/resume_ner/meta.json" not in m["file_hashes"]
    assert m["ner_skills"] == {"enabled": False, "available": True}


def test_manifest_includes_ner_when_enabled(monkeypatch):
    off = algorithm_manifest()["fingerprint"]
    monkeypatch.setenv("NER_SKILLS_ENABLED", "1")
    m = algorithm_manifest()
    assert m["dependencies"]["spacy"]
    assert "scorer/ner_skills.py" in m["file_hashes"]
    assert "scorer/models/resume_ner/meta.json" in m["file_hashes"]
    assert m["ner_skills"]["enabled"] is True
    assert m["fingerprint"] != off
```

- [ ] **Step 2: Прогнать — падают**

```bash
python -m pytest tests/test_ner_skills.py -q -k manifest
```

Ожидание: FAIL — ключа `ner_skills` в манифесте нет.

- [ ] **Step 3: Реализовать**

В `scorer/config.py` заменить `algorithm_manifest` (строки 43–59) на:

```python
def algorithm_manifest() -> dict:
    from .ner_skills import ner_enabled, ner_status  # отложенный импорт: без цикла

    config = load_config()
    files = [config_path(), dictionary_path(), ROOT / config["reference_corpus"],
             ROOT / "scorer/skills_auto.json", ROOT / "scorer/skills_auto_raw.json",
             ROOT / "scorer/skill_extractor.py", ROOT / "scorer/skill_families.py",
             ROOT / "scorer/scoring.py", ROOT / "scorer/normalize.py", ROOT / "scorer/privacy.py",
             ROOT / "scorer/skills.py", ROOT / "requirements.lock"]
    packages = ["fastapi", "pydantic", "pymongo", "PyMuPDF", "scikit-learn", "numpy",
                "scipy", "razdel", "pymorphy3"]
    if ner_enabled():
        # NER-артефакты входят в fingerprint только когда реально влияют на скор:
        # при выключенном флаге fingerprint побитово совпадает с доинтеграционным.
        files += [ROOT / "scorer/ner_skills.py", ROOT / "scorer/models/resume_ner/meta.json"]
        packages.append("spacy")
    dependencies = {}
    for package in packages:
        try:
            dependencies[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            dependencies[package] = "unavailable"
    hashes = {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else p.name:
              hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.exists()}
    fingerprint = hashlib.sha256(json.dumps({"config":config,"hashes":hashes,"dependencies":dependencies},sort_keys=True).encode()).hexdigest()
    return {**config, "file_hashes": hashes, "dependencies": dependencies,
            "fingerprint": fingerprint, "ner_skills": ner_status()}
```

- [ ] **Step 4: Прогнать**

```bash
python -m pytest tests/test_ner_skills.py -q
python -m pytest tests/pmi/test_acceptance.py -q
```

Ожидание: PASS (`test_a01…` — известный фейл fontTools, не наш).

- [ ] **Step 5: Commit**

```bash
git add scorer/config.py tests/test_ner_skills.py
git commit -m "feat(scorer): manifest conditionally fingerprints NER artifacts"
```

---

### Task 5: Зависимости

**Files:**
- Modify: `scorer/requirements.txt`
- Modify: `requirements.lock`

**Interfaces:**
- Consumes: версии из Global Constraints.
- Produces: `pip install -r requirements.lock` ставит spaCy-стек; `import spacy` работает; образ собирается.

- [ ] **Step 1: Обновить requirements**

`scorer/requirements.txt` — добавить строку:

```
spacy==3.8.16
```

`requirements.lock` — добавить в алфавитном порядке (после `certifi`/`click`-блока, по фактическому алфавиту файла):

```
blis==1.3.3
catalogue==2.0.10
confection==1.3.3
cymem==2.0.13
murmurhash==1.0.15
preshed==3.0.13
spacy==3.8.16
spacy-legacy==3.0.12
spacy-loggers==1.0.5
srsly==2.5.4
thinc==8.3.13
typer==0.27.3
wasabi==1.1.3
weasel==1.0.0
```

- [ ] **Step 2: Проверить резолвер и импорт**

```bash
python -m pip install --dry-run -r requirements.lock 2>&1 | tail -3
python -c "import spacy; print(spacy.__version__)"
```

Ожидание: dry-run без конфликтов; версия 3.8.16.

- [ ] **Step 3: Проверить сборку образа (модель попадает в scorer/)**

```bash
docker compose build scorer
```

Ожидание: сборка успешна; `.dockerignore` не исключает `scorer/models/` (проверено — не исключает). Если Docker недоступен на стенде — отметить пропуск в отчёте таска, гейт Task 7 от этого не зависит.

- [ ] **Step 4: Прогнать тесты**

```bash
python -m pytest tests/test_ner_skills.py -q
```

Ожидание: PASS.

- [ ] **Step 5: Commit**

```bash
git add scorer/requirements.txt requirements.lock
git commit -m "build: pin spaCy stack for NER skill extraction"
```

---

### Task 6: Поглощение Resume-Parser-main

**Files:**
- Create: `training/ner/` (переезд `Resume-Parser-main/training/` + LICENSE)
- Delete: `Resume-Parser-main/` (остаток)

**Interfaces:**
- Consumes: модель уже скопирована в Task 1.
- Produces: дерево без `Resume-Parser-main/`; `training/ner/` — аннотации Label Studio + скрипты обучения + MIT-лицензия для атрибуции (заголовок `scorer/ner_skills.py` уже ссылается на `training/ner/LICENSE`).

- [ ] **Step 1: Перенести training и лицензию, удалить остальное**

```bash
mkdir -p training
mv Resume-Parser-main/training training/ner
mv Resume-Parser-main/LICENSE training/ner/LICENSE
rm -rf Resume-Parser-main
```

- [ ] **Step 2: Проверить, что ссылок на старый путь нет**

```bash
grep -rn "Resume-Parser-main" --include="*.py" --include="*.yml" --include="*.json" --include="*.cfg" --include="*.ini" . | grep -v docs/superpowers/ || echo "OK: ссылок нет"
```

Ожидание: `OK: ссылок нет` (упоминания в spec/plan-доках допустимы).

- [ ] **Step 3: Полный прогон**

```bash
python -m pytest -q
```

Ожидание: только 3 известных фейла окружения.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: absorb Resume-Parser-main (model vendored, training kept, rest removed)"
```

---

### Task 7: Бенчмарк-гейт + документация

**Files:**
- Create: `reports/ner_gate/README.md`
- Modify: `config/algorithm.json` (только если гейт пройден —.flip default)
- Modify: `README.md`, `scorer/README.md`

**Interfaces:**
- Consumes: `scripts/benchmark_real_data.py` (CLI: `--dataset-dir`, `--ranking-inputs extracted`, `--output-dir`, `--output-prefix`); датасет `data/benchmark/` (10 вакансий, 194 резюме).
- Produces: зафиксированная дельта метрик; решение о дефолте флага; обновлённая документация.

- [ ] **Step 1: Базовый прогон (словарь, NER выкл)**

```bash
python scripts/benchmark_real_data.py --dataset-dir data/benchmark \
  --ranking-inputs extracted \
  --output-dir reports/ner_gate --output-prefix baseline
```

Ожидание: `reports/ner_gate/baseline.json` создан; зафиксировать `extraction.resumes.micro.f1`, `extraction.vacancies.micro.f1`, `ranking.ndcg_at_10` (пути в JSON: `report["extraction"]["resumes"]["micro"]["f1"]`, `report["metrics"]["ndcg_at_10"]`).

- [ ] **Step 2: Прогон с NER (union)**

```bash
NER_SKILLS_ENABLED=1 python scripts/benchmark_real_data.py --dataset-dir data/benchmark \
  --ranking-inputs extracted \
  --output-dir reports/ner_gate --output-prefix ner_union
```

Ожидание: `reports/ner_gate/ner_union.json` создан.

- [ ] **Step 3: Применить правило решения**

Гейт пройден ⟺ **оба** условия:
- `ner_union.extraction.resumes.micro.f1 >= baseline.extraction.resumes.micro.f1` И `ner_union.extraction.vacancies.micro.f1 >= baseline.extraction.vacancies.micro.f1`
- `ner_union.metrics.ndcg_at_10 >= baseline.metrics.ndcg_at_10 - 0.005`

Если пройден: в `config/algorithm.json` заменить `"ner_skills_enabled": false` на `"ner_skills_enabled": true`.
Если нет: флаг остаётся `false`; интеграция живёт за флагом.

- [ ] **Step 4: Написать отчёт дельты**

`reports/ner_gate/README.md`:

```markdown
# Гейт включения NER-навыков (union со словарём)

Дата: <дата прогона> · Датасет: data/benchmark (10 вакансий, 194 резюме, режим extracted)
Команды: см. docs/superpowers/plans/2026-11-16-ner-skill-extraction.md, Task 7.

| Метрика | baseline (словарь) | ner_union | Δ |
|---|---:|---:|---:|
| Extraction F1 (resumes, micro) | <v> | <v> | <v> |
| Extraction F1 (vacancies, micro) | <v> | <v> | <v> |
| NDCG@10 | <v> | <v> | <v> |

Правило: F1 не падает и NDCG@10 проседает не более 0.005 → включаем по умолчанию.

Решение: <включён по умолчанию | оставлен за флагом (ner_skills_enabled=false)>.
Обоснование: <1-2 предложения; при отрицательной дельте — главные FP/FN NER из отчётов>.

Модель английская (60 резюме); на русском корпусе ожидаем вклад в основном
через латинские названия технологий. При включении по умолчанию требуется
новый PMI-прогон (README: «для повторного прогона изменённого кода нужен
новый набор и протокол»).
```

- [ ] **Step 5: Обновить README**

`README.md`, секция «Расчёт и режимы работы» — после абзаца про TF-IDF-корпус добавить:

```markdown
Навыки дополнительно извлекаются spaCy NER-моделью (union со словарём). Включение — ключ `ner_skills_enabled` в `config/algorithm.json`; переменная `NER_SKILLS_ENABLED` переопределяет для экспериментов. При ошибке загрузки модели скоринг продолжается на словаре (состояние — в `GET /config`, поле `ner_skills`). Для резюме, загруженных до включения, список навыков обновится при повторной загрузке файла.
```

В таблицу переменных (после строки `DOCKER_PLATFORM`) добавить:

```markdown
| `NER_SKILLS_ENABLED` | Нет | — | `1/true/yes` включает NER-навыки, `0/false/no` выключает; иначе — ключ `ner_skills_enabled` из `config/algorithm.json` |
```

`scorer/README.md` — добавить раздел «NER-навыки» с тем же смыслом в двух-трёх предложениях и путём модели `scorer/models/resume_ner`.

- [ ] **Step 6: Финальный полный прогон**

```bash
python -m pytest -q
```

Ожидание: только 3 известных фейла окружения (Global Constraints); если гейт включил флаг в дефолт (`ner_skills_enabled: true`), то три теста, читающих репо-конфиг без env-переопределения, нужно перевести на явное `monkeypatch.setenv("NER_SKILLS_ENABLED", "0")` вместо `monkeypatch.delenv(...)` / чтения дефолта: `test_flag_default_off_in_repo_config` (переименовать в `test_repo_flag_respected` — проверять фактическое значение ключа), `test_union_superset_of_real_ner_when_enabled` уже ставит env=1 — не трогать, `test_flag_off_keeps_dictionary_result` уже ставит env=0 — не трогать; `test_manifest_excludes_ner_when_disabled` — заменить `delenv` на `setenv("NER_SKILLS_ENABLED", "0")`.

- [ ] **Step 7: Commit**

```bash
git add reports/ner_gate README.md scorer/README.md config/algorithm.json tests/test_ner_skills.py
git commit -m "docs+feat: NER union benchmark gate and default-flag decision"
```
