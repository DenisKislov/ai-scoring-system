# Дизайн: NER-извлечение навыков (spaCy) в scorer

Дата: 2026-11-16
Статус: утверждён пользователем (подход 1, «in-process модуль в скорере»)
Репозиторий-источник: `Resume-Parser-main/` (внешний, MIT), поглощается этим дизайном

## Контекст

В проект добавлен внешний репозиторий `Resume-Parser-main`: spaCy NER-модель
(11 МБ, пайплайн `tok2vec` + `ner`, без трансформеров и torch) с сущностями
`Skill`, `Work_Experience`, `Education`, `Language`, обученная на 60
англоязычных резюме. Заявленный в её README «RoBERTa-base, F1 96.77%» не
соответствует поставляемой модели; метрика посчитана на 10 тестовых резюме с
авто-пре label-аннотациями — цифре не доверяем, доверяем своему бенчмарку.

Проверка спайком (spacy 3.8.16, текущее окружение):

- загрузка модели — 0.17 с; инференс — ~9 мс на короткое резюме;
- англоязычный сэмпл: все 9 навыков извлечены верно;
- русскоязычный сэмпл: латинские технологии (`Python`, `Django`,
  `PostgreSQL`, `Docker`, `REST API`, `scikit-learn`, `PyTorch`) извлекаются
  корректно; единственный FP — на сущности `Work_Experience`, которая в
  интеграцию не входит.

Текущая система извлекает навыки словарным экстрактором
(`scorer/skill_extractor.py`, онтология ~316 канонических навыков) через
единственную точку входа `scorer/skills.py::extract_skills()`.

## Решение

Навыки документа = **словарь ∪ NER**. NER — дополнительный источник recall;
словарь остаётся якорем качества. Слияние выполняется в
`extract_skills()`, поэтому загрузка резюме, скоринг документов без
сохранённых навыков, PMI-пайплайн и бенчмарки получают идентичное поведение.

Сущности `Education`, `Language`, `Work_Experience` не используются (полей
образование/языки в системе нет; опыт парсится регэкспами в
`api/nlp_parser.py`).

Включение по умолчанию решается бенчмарком (см. «Решающий гейт»); до решения
флаг `ner_skills_enabled = false`.

## Архитектура и файлы

| Действие | Путь | Содержание |
|---|---|---|
| Копировать | `scorer/models/resume_ner/` | Файлы spaCy-модели из `Resume-Parser-main/backend/model/` (11 МБ) |
| Создать | `scorer/ner_skills.py` | Ленивый синглтон `_nlp()`; `ner_extract_skills(text) -> Set[str]`; `ner_enabled() -> bool` |
| Изменить | `scorer/skills.py` | В `extract_skills()`: union за флагом |
| Изменить | `config/algorithm.json` | Ключ `"ner_skills_enabled": false` |
| Изменить | `scorer/config.py` | Манифест: `spacy` в dependencies, хэши `scorer/ner_skills.py` и `scorer/models/resume_ner/meta.json` |
| Изменить | `scorer/requirements.txt`, `requirements.lock` | `spacy==3.8.16` + транзитивные зависимости |
| Создать | `tests/test_ner_skills.py` | Тесты (см. «Тестирование») |
| Перенести | `training/ner/` | `Resume-Parser-main/training/` — аннотации Label Studio и пайплайн обучения; под будущее дообучение на русском |
| Удалить | `Resume-Parser-main/` | Остаток папки после копирования модели и training/ |

### `scorer/ner_skills.py` (контракт)

- `_nlp()` — загружает `spacy.load(MODEL_DIR)` при первом обращении;
  `MODEL_DIR = scorer/models/resume_ner`, переопределяется env
  `NER_SKILLS_MODEL`.
- `ner_enabled() -> bool` — env `NER_SKILLS_ENABLED` (значения `1/true/yes`)
  переопределяет ключ `ner_skills_enabled` из `config/algorithm.json`.
- `ner_extract_skills(text) -> Set[str]` — нормализация текста (правки
  исходного репо: `(cid:N)`, склейка переносов внутри слов, схлопывание
  пробелов), прогон пайплайна, фильтр `ent.label_ == "Skill"`, `strip()`,
  dedupe. Возвращает сырые спаны; каноникализация — ответственность
  вызывающего.
- Отказоустойчивость: при ошибке загрузки/инференса — `logger.critical`,
  latch «NER выключен до рестарта процесса», `ner_extract_skills` возвращает
  пустое множество. Скоринг продолжается на словаре. Состояние видно в
  `GET /config` (поле `ner_skills`).

### `scorer/skills.py` (точка слияния)

```python
def extract_skills(text: str) -> Set[str]:
    if not text or not text.strip():
        return set()
    extractor = _get_extractor()
    skills = normalize_skill_set(extractor.extract(professional_text(text)))
    if ner_enabled():
        skills |= normalize_skill_set(ner_extract_skills(text))
    return skills
```

Текст для NER проходит через тот же `professional_text()`, что и для
словаря (приватность: контакты/демография не попадают в модель).

## Поток данных

PDF/TXT → `api/file_parser.py` (PyMuPDF, лимиты 8 МиБ/200 стр./1М символов —
без изменений) → `db/builders.py::parse_raw_text_to_resume` →
`extract_skills() [словарь ∪ NER]` → `normalize_skill_set` → `doc["skills"]`
в MongoDB → `scorer/service.py` использует сохранённые навыки при скоринге.

- Резюме, загруженные до интеграции, не перерассчитываются автоматически;
  их NER-навыки появятся при повторной загрузке (задокументировать в README).
- `scorer/service.py` без изменений: он уже берёт `doc["skills"]`, если они
  есть.

## Почему union безопасен для Score

`keyword_score` — покрытие требований вакансии: знаменатель — `v_skills`,
и лишние навыки резюме вне таксономии не пересекаются с требованиями и на
скор не влияют. NER-спаны, каноникализирующиеся в таксономию/алиасы, влияют
ровно как прирост recall покрытия. Вне-таксономные спаны обогащают список
навыков в карточке HR и поле `resume_skills` (семейный матчинг по ним не
срабатывает — их нет в `SKILL_FAMILY_GROUPS`). Cosine-компонента работает по
тексту, не по списку навыков.

## Манифест и воспроизводимость

- `algorithm_manifest()` дополняется: `spacy` в `dependencies`, хэши
  `scorer/ner_skills.py` и `scorer/models/resume_ner/meta.json` (бинарники
  модели не хэшируем — манифест остаётся дешёвым; `meta.json` фиксирует
  версию/лейблы модели).
- Ключ `ner_skills_enabled` лежит в `algorithm.json`, который уже хэшируется
  манифестом → переключение флага меняет fingerprint → `db/mongo.py::
  save_scores` корректно чистит несравнимые рейтинги.
- `GET /config` дополнительно возвращает эффективное состояние
  `ner_skills.enabled` (с учётом env-переопределения): env — инструмент
  экспериментов, в fingerprint он не входит, поэтому честное состояние
  видно в рантайме, а воспроизводимые конфигурации фиксируются значением в
  `algorithm.json`.
- При `ner_skills_enabled: false` (и без env-переопределения) поведение и
  fingerprint системы идентичны текущим — PMI-протоколы не затрагиваются.

## Решающий гейт — бенчмарк

Прогон до/после:

```bash
python scripts/benchmark_real_data.py --dataset-dir data/benchmark
```

(10 вакансий, 194 резюме с разметкой навыков; режим `annotated` и
`--ranking-inputs extracted`.)

Метрики решения: micro-F1 извлечения навыков и NDCG@10 ранжирования.

Правило: включаем `ner_skills_enabled: true` по умолчанию, только если F1 не
упал и NDCG@10 не просел более чем на 0.005. Иначе флаг остаётся `false`,
дельта фиксируется отчётом в `reports/`. При переключении в `true`
потребуется новый PMI-прогон (README уже требует новый набор и протокол для
изменённого кода).

## Производительность

- Загрузка модели: 0.17 с, лениво, один раз на процесс.
- Инференс: ~9 мс на резюме; пул 200 резюме ≈ +2 с к `/score` (endpoint уже
  исполняется в threadpool).
- Образы api/scorer вырастут на ~60–80 МБ (spacy + thinc + blis, без torch).

## Тестирование

`tests/test_ner_skills.py`:

1. Модель загружается; `ner_extract_skills` возвращает только `Skill`.
2. Английский сэмпл: `Python`, `SQL` и др. извлекаются.
3. Русский сэмпл: латинские технологии (`Django`, `PostgreSQL`) извлекаются.
4. `extract_skills` с включённым флагом ⊇ результата словаря (union).
5. Флаг выключен → `extract_skills` побитово равен прежнему результату.
6. Битая модель (`NER_SKILLS_MODEL` на несуществующий путь) → пустое
   множество + latch, словарь работает.
7. Детерминизм: два вызова дают одинаковый результат.

Регрессия: весь существующий набор pytest проходит без изменений (при
выключенном флаге — гарантированно; при включённом — тесты, зависящие от
точного списка навыков, проверяются в рамках гейта).

## Уборка репозитория

После копирования модели и `training/` папка `Resume-Parser-main/` удаляется
из дерева (скриншоты 19 МБ, Next.js-фронтенд, pnpm-lock, pdfplumber/docx2txt
не используются). MIT-лицензия исходного проекта сохраняется в заголовке
`scorer/ner_skills.py` и в `training/ner/LICENSE`.

## Вне скоупа

- Дообучение модели на русском корпусе (использовать `training/ner/`).
- Извлечение Education/Language/Work_Experience.
- Замена словарного экстрактора.
- Изменения фронтенда (список навыков уже отображается из `doc["skills"]`).
