# AI Candidate Scoring System

Система сравнивает резюме с требованиями вакансии и формирует рейтинг кандидатов. Принимает PDF, TXT и JSON, извлекает навыки и опыт, рассчитывает Score от 0 до 100 и сохраняет результаты и решения HR в MongoDB.

## Содержание

- [Архитектура](#архитектура)
- [Состав системы](#состав-системы)
- [Быстрый старт](#быстрый-старт)
- [Тесты](#тесты)
- [API](#api)
- [Логирование](#логирование)
- [Сетевая конфигурация](#сетевая-конфигурация)
- [Документация по компонентам](#документация-по-компонентам)

## Архитектура

```text
Браузер HR
    │ HTTP :3000
    ▼
Frontend — React / Nginx
    │ /api → HTTP backend:8000
    ▼
Backend — FastAPI
    ├── HTTP scorer:8001 → Scorer — навыки, TF-IDF, Score
    └── MongoDB mongo:27017 → документы, оригиналы, результаты, история HR

Прямой доступ к API и Swagger: http://localhost:8000/docs
```

### Ключевые компоненты

| Модуль | Назначение |
|---|---|
| `frontend/src/App.js` | Загрузка документов, форма вакансии, рейтинг, карточка, подсветка навыков и решения HR |
| `api/routes.py`, `api/schemas.py` | HTTP-методы и проверка запросов |
| `api/file_parser.py` | Извлечение текста PDF через PyMuPDF и чтение TXT в UTF-8 |
| `api/nlp_parser.py` | Формирование профиля резюме, навыки и опыт работы |
| `scorer/skill_extractor.py` | Словарное извлечение навыков и нормализация вариантов написания |
| `scorer/scoring.py`, `scorer/similarity.py` | Покрытие требований, TF-IDF и ранжирование |
| `scorer/service.py`, `scorer/transport.py` | Расчёт по документам БД; локальный или HTTP-вызов ядра |
| `scorer/http_api.py` | Отдельный внутренний сервис скоринга |
| `db/mongo.py` | Хранение документов, результатов, оригиналов и истории решений |
| `config/` | Версия алгоритма, веса и расширяемый справочник навыков |
| `pmi/`, `tests/pmi/` | Генерация контрольного набора и испытания по ПМИ |

### Расчёт и режимы работы

```text
Score = round(100 × (0.85 × keyword_score + 0.15 × cosine_sim))
```

`keyword_score` — взвешенная доля покрытых требований вакансии. Критический навык весит 2, обычный — 1. `cosine_sim` — близость профессиональных текстов по TF-IDF. Используются симметричные группы родственных навыков.

TF-IDF обучается на фиксированном корпусе: оценка пары не зависит от остальных резюме в наборе. При пустом профессиональном тексте или отсутствии совпадений Score равен 0. Опыт используется для сортировки при одинаковом Score. Контактные и демографические строки исключаются из расчёта.

В Docker backend вызывает отдельный скорер по `SCORER_URL`. Без этой переменной используется то же ядро внутри процесса API. Версия алгоритма — `baseline-pmi-1.0.0`; параметры и хэши доступны через `GET /config`.

Фильтр выдачи использует сохранённый в БД порог покрытия навыков. Если порог отсутствует и локальные исходные JSON недоступны, фильтр отключён. Он не является метрикой качества и не меняет Score.

Ограничения входов: PDF/TXT, до 8 МиБ на файл, до 200 страниц PDF, до миллиона символов текста. Для пакетной загрузки резюме — до 200 файлов. OCR отсутствует; PDF должен содержать текстовый слой.

## Состав системы

| Сервис | Директория | Порты | Описание |
|---|---|---|---|
| `frontend` | `frontend/` | `3000 → 80` | React и Nginx; проксирование `/api` |
| `backend` | `api/`, `db/` | `8000 → 8000` | Публичный API, файлы, журнал и MongoDB |
| `scorer` | `scorer/` | `8001`, внутренний | Независимый сервис расчёта |
| `mongo` | Образ `mongo:8` | `27017`, внутренний | Постоянное хранение данных |

`Parser/` — отдельный сборщик исходных данных; для работы сайта не требуется.

## Быстрый старт

### Требования

- Git и Docker Engine либо Docker Desktop с Compose v2.
- Для локальной разработки без контейнеров: Python 3.13, Node.js 22 и MongoDB.
- При первой сборке нужен доступ к реестрам образов и пакетов. GPU не используется.
- Приёмочный стенд ПМИ: Linux/Windows x86-64, от 2 ядер, 8 ГБ RAM и 100 ГБ диска. На Mac Docker Desktop запускает образы `linux/amd64` с эмуляцией.

### Конфигурация

Из корня репозитория при необходимости создайте `.env`:

```bash
cp .env.example .env
```

```env
API_PORT=8000
FRONTEND_PORT=3000
MONGO_URI=mongodb://mongo:27017
MONGO_DB=gb_parse
API_CORS_ORIGINS=http://localhost:3000
REACT_APP_API_URL=/api
```

| Переменная | Обязательная | По умолчанию в Compose | Описание |
|---|---|---|---|
| `API_PORT` | Нет | `8000` | Порт API на хосте |
| `FRONTEND_PORT` | Нет | `3000` | Порт интерфейса на хосте |
| `MONGO_URI` | Нет | `mongodb://mongo:27017` | Адрес MongoDB |
| `MONGO_DB` | Нет | `gb_parse` | Имя базы |
| `API_CORS_ORIGINS` | Нет | `http://localhost:3000` | Разрешённые источники запросов, через запятую |
| `REACT_APP_API_URL` | Нет | `/api` | Адрес API во фронтенде; применяется при сборке |
| `DOCKER_PLATFORM` | Нет | `linux/amd64` | Платформа контейнеров |

`SCORER_URL=http://scorer:8001` задан в `docker-compose.yml`. Для локального запуска отдельных процессов используется `SCORER_URL=http://localhost:8001`; без него скоринг выполняется в API. В локальном режиме адрес API фронтенда по умолчанию — порт 8000 того же хоста, CORS API — `*`.

Дополнительные настройки процессов: `SCORER_TIMEOUT` — 30 секунд, `MONGO_TIMEOUT_MS` — 2000 мс; `ALGORITHM_CONFIG` и `SKILLS_DICTIONARY` переопределяют пути файлов. В Compose дополнительные переменные необходимо явно передать нужному контейнеру; одного добавления в `.env` недостаточно.

| Файл | Настройки |
|---|---|
| `config/algorithm.json` | Веса, вес критического навыка, версия и пути к справочнику и корпусу |
| `config/skills.json` | Направления, канонические навыки и алиасы; изменения перечитываются без перезапуска |

Импорт внешних JSON отключён по умолчанию; пользовательские PDF, реальные JSON, `.env` и журналы в дистрибутив не включаются.

### Запуск

```bash
git clone https://github.com/DenisKislov/ai-scoring-system.git
cd ai-scoring-system

docker compose build
docker compose up -d --wait
```

- Интерфейс: `http://localhost:3000`.
- Swagger: `http://localhost:8000/docs`.
- Проверка API: `http://localhost:8000/status`.
- Проверка БД: `http://localhost:8000/health`.

Начальная база может быть пустой. Создайте вакансию и загрузите резюме либо используйте кнопку «Синтетический генератор»: 5 вакансий и 100 резюме. Затем выберите вакансию, отметьте критические навыки и запустите скоринг. Карточка показывает объяснение, исходный текст, подсветку и историю HR. Рейтинг доступен в JSON.

### Запуск отдельных компонентов

```bash
# API, скорер и MongoDB без интерфейса
docker compose up -d --wait mongo scorer backend

# Интерфейс вместе с необходимыми зависимостями
docker compose up -d --wait frontend
```

Для локальной разработки установите зависимости в активированном окружении:

```bash
python -m pip install -r requirements.lock -r tests/requirements.txt
```

При доступной MongoDB на порту 27017 запустите в отдельных терминалах:

```bash
# Скорер
python -m uvicorn scorer.http_api:app --port 8001

# Backend; пример для bash/zsh
MONGO_URI=mongodb://localhost:27017 SCORER_URL=http://localhost:8001 \
  python -m uvicorn api.main:app --port 8000

# Frontend
cd frontend
npm ci
npm start
```

### Остановка

```bash
docker compose stop
```

Тома `mongo_data` и `app_logs` сохраняются. Возобновление работы: `docker compose up -d --wait`. Порядок резервного копирования и восстановления описан в RUNBOOK.

## Тесты

Из корня проекта, после установки зависимостей:

```bash
python -m pytest -q
python -m pytest -q tests/pmi
python -m pytest -q tests/test_api.py

npm ci --prefix frontend
npm test --prefix frontend -- --watchAll=false --runInBand
npm run build --prefix frontend
```

Последний зафиксированный прогон от 27.10.2026: 186 тестов Python и 11 тестов React пройдены, сборка выполнена. Это результат указанного прогона, а не автоматическое подтверждение полной приёмки ПМИ.

### Вспомогательные скрипты

| Скрипт | Назначение | Когда использовать |
|---|---|---|
| `python -m pmi` | Контрольные данные, качество, нагрузка, аудит и Docker-проверки | Испытания по ПМИ |
| `scripts/benchmark_synthetic.py` | Оценка на более сложной синтетике шести ИТ-направлений | Диагностика ранжирования |
| `scripts/benchmark_real_data.py` | Бенчмарк локальных JSON | Воспроизводимый базовый прогон |
| `scripts/benchmark_pdf_corpus.py` | Оценка по PDF и разметке CSV | Отдельная диагностика при наличии исходных файлов |

Новый протокол ПМИ создаётся отдельно от сохранённых результатов:

```bash
python -m pmi build --dataset data/pmi_v2 --output reports/pmi_v2
python -m pmi verify --dataset data/pmi_v2 --output reports/pmi_v2
python -m pmi run --live --dataset data/pmi_v2 --output reports/pmi_v2
```

`--dataset` задаёт набор и манифест; `--output` — папку отчётов; `--live` запускает отдельный Docker-стенд на портах 18000/13000. Набор: 10 вакансий и 200 синтетических резюме по пяти направлениям. Команда может вернуть ненулевой код при непройденном критерии или незавершённой формальной приёмке. Для повторного прогона изменённого кода нужен новый набор и протокол.

При наличии локальных JSON можно выполнить:

```bash
python scripts/benchmark_real_data.py --limit 10 --threshold 0.1 --ranking-inputs annotated
```

`--limit 0` — все вакансии; `--threshold` — порог бинарной proxy-релевантности; `--ranking-inputs extracted` — извлечение навыков из текста. Режим `annotated` получает готовые размеченные навыки и не оценивает сквозное качество загрузки и извлечения из PDF. JSON-источники не поставляются в репозитории.

## API

Swagger: `http://localhost:8000/docs`. Схема OpenAPI: `http://localhost:8000/openapi.json`. В Docker те же методы доступны через `http://localhost:3000/api`.

### Вакансии, резюме и файлы

| Метод | Путь | Описание |
|---|---|---|
| `GET`, `POST` | `/vacancies` | Список вакансий / создание из JSON |
| `GET`, `DELETE` | `/vacancies/{vacancy_id}` | Получить / удалить вакансию |
| `PATCH` | `/vacancies/{vacancy_id}/critical-skills` | Обновить критические требования |
| `GET`, `POST` | `/candidates` | Список резюме / создание из JSON |
| `GET`, `DELETE` | `/resumes/{resume_id}` | Получить / удалить резюме |
| `POST` | `/upload_vacancy` | Загрузить PDF/TXT вакансии; поле `file`, необязательное `critical_skills` |
| `POST` | `/upload_resume` | Загрузить PDF/TXT резюме; поле `file` |
| `POST` | `/upload_resumes` | Пакет резюме; поле `files` |
| `GET` | `/files/{kind}/{document_id}` | Скачать оригинал; `kind`: `vacancies` или `resumes` |
| `DELETE` | `/vacancies/clear`, `/resumes/clear` | Удалить все документы указанного типа и связанные результаты |

Тело `POST /vacancies`:

```json
{
  "title": "Python-разработчик",
  "description": "Разработка API на Python и PostgreSQL",
  "skills": ["Python", "PostgreSQL"],
  "critical_skills": ["Python"]
}
```

`title` обязателен. Критические навыки должны входить в требования. Ответ содержит `_id`, используемый при запуске скоринга. При удалении документа удаляются связанные результаты, оригинал и история HR.

### Скоринг и решения HR

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/score` | Рассчитать рейтинг и сохранить результаты |
| `GET` | `/results/{vacancy_id}?top=10` | Получить сохранённый рейтинг в JSON |
| `POST` | `/feedback` | Сохранить решение `yes` или `no` |
| `GET` | `/feedback?vacancy_id=...&resume_id=...` | Последнее решение и история с датами |

Тело `POST /score`; ID в примере необходимо заменить на `_id` созданной вакансии:

```json
{
  "vacancy_id": "507f1f77bcf86cd799439011",
  "critical_skills": ["Python"],
  "weights": {"keyword": 0.85, "cosine": 0.15}
}
```

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `vacancy_id` | string | Да | ID вакансии |
| `resume_ids` | array[string] | Нет | Конкретные резюме; один ID — расчёт одной пары |
| `limit_resumes` | integer | Нет | Максимум резюме, не менее 1 |
| `critical_skills` | array[string] | Нет | Критические навыки; пустой массив снимает выбор |
| `weights` | object | Нет | Неотрицательные `keyword` и `cosine`, сумма равна 1 |

Ответ содержит `vacancy_id`, `count` и `results`. Для кандидата возвращаются Score, компоненты, найденные и отсутствующие навыки, критические пробелы. Повторный расчёт обновляет пары без дублирования. Решения HR сохраняются отдельно от алгоритма.

### Служебные методы

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/status` | Состояние процесса API без обращения к БД |
| `GET` | `/health` | Доступность MongoDB |
| `GET` | `/stats` | Число вакансий и резюме |
| `GET` | `/config` | Версия, веса, зависимости и хэши алгоритма |
| `GET` | `/threshold` | Текущий порог фильтра выдачи |
| `POST` | `/threshold/recompute` | Пересчитать порог при наличии локальных источников |
| `GET` | `/logs?lines=50` | Последние записи журнала API |
| `DELETE` | `/logs/clear` | Очистить журнал API |
| `POST` | `/generate_test_data?vacancies=5&resumes=20` | Добавить 5 вакансий и по 20 резюме на каждую |

Внутренний скорер предоставляет `GET /health`, `GET /config`, `POST /rank`; наружу его порт не публикуется.

**Коды ответа:**

| Код | Значение | Причина |
|---|---|---|
| `200` | Успешно | Чтение, расчёт, сохранение решения |
| `201` | Создано | Создание или загрузка документов |
| `400` | Ошибка файла | Пустой, повреждённый, неподдерживаемый файл или отсутствие текста |
| `403` | Запрещено | Отключённый импорт внешних JSON |
| `404` | Не найдено | Неизвестный ID документа |
| `422` | Ошибка валидации | Неверная структура запроса, веса или критические навыки |
| `503` | Сервис недоступен | Сбой MongoDB или отдельного скорера |

## Логирование

Формат: `время с часовым поясом | уровень | сообщение`. Структурированные события записываются JSON в поле сообщения. Пример:

```text
2026-10-28T10:00:00+0700 | INFO | {"event": "upload_started", "kind": "resume", "filename": "resume.pdf", "size_bytes": 2048}
```

- Настройка: `api/logger.py`.
- Обработчики: консоль и `logs/app.log` в UTF-8; файл создаётся при первой записи. Автоматическая ротация не реализована.
- В Docker каталог `/app/logs` backend хранится в томе `app_logs`. База — в томе `mongo_data`.
- Уровень логгера — `INFO`; используются сообщения `INFO`, `WARNING`, `ERROR`.
- Записываются загрузки, длительность скоринга, ошибки и изменения данных. Полный текст резюме в структурированные события не включается.
- Журнал действий интерфейса хранится в состоянии React и сбрасывается при перезагрузке; журнал API доступен отдельно через `/logs`.

```bash
docker compose logs -f backend scorer frontend
```

## Сетевая конфигурация

| Сеть | Подсеть | Участники |
|---|---|---|
| Compose `default` | Назначается Docker, фиксированные IP не заданы | `frontend`, `backend`, `scorer`, `mongo` |

DNS-имена внутри сети: `backend:8000`, `scorer:8001`, `mongo:27017`. По умолчанию frontend и backend публикуются только на `127.0.0.1`; MongoDB и скорер доступны внутри Compose. Имя сети при стандартном имени проекта — `ai-scoring-system_default`.

Nginx удаляет префикс `/api` и перенаправляет запрос backend. Для локального frontend без Docker используется прямой адрес API на порту 8000. При изменении порта интерфейса следует обновить `API_CORS_ORIGINS`, если используются прямые запросы между портами.

## Документация по компонентам

- [Frontend](https://github.com/DenisKislov/ai-scoring-system/blob/main/frontend/README.md) — запуск и сборка интерфейса.
- [Scorer](https://github.com/DenisKislov/ai-scoring-system/blob/main/scorer/README.md) — извлечение навыков и расчёт Score.
- [MongoDB](https://github.com/DenisKislov/ai-scoring-system/blob/main/db/README.md) — хранение данных.
- [Parser](https://github.com/DenisKislov/ai-scoring-system/blob/main/Parser/README.md) — отдельный сборщик данных.
- [Архитектура](https://github.com/DenisKislov/ai-scoring-system/blob/main/docs/ARCHITECTURE.md) — алгоритм и взаимодействие сервисов.
- [RUNBOOK](https://github.com/DenisKislov/ai-scoring-system/blob/main/docs/RUNBOOK.md) — развёртывание и восстановление.
- [Руководство пользователя](https://github.com/DenisKislov/ai-scoring-system/blob/main/docs/USER_GUIDE.md) — основные сценарии работы.
- [ПМИ](https://github.com/DenisKislov/ai-scoring-system/blob/main/docs/PMI.md) — испытания и ограничения приёмки.
- [Функциональный протокол](https://github.com/DenisKislov/ai-scoring-system/blob/main/reports/pmi_functional_2026-10-27/protocol.md) — подтверждённые сценарии и замечания.
- [Бенчмарк](https://github.com/DenisKislov/ai-scoring-system/blob/main/reports/baseline_pmi_2026-10-27/README.md) — методика и результаты ранжирования.
