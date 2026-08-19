# AI Candidate Scoring System

## Системные требования
* Установленный Docker Desktop.
* **Внимание для пользователей macOS (Apple Silicon):** В настройках Docker (Settings -> Resources) необходимо выделить минимум 8 GB оперативной памяти для корректной компиляции ML-зависимостей.

## Запуск
Откройте терминал в корневой директории проекта и выполните команду:

```bash
docker compose up --build -d
```

## Доступные адреса
* **Фронтенд:** http://localhost:3000
* **API (Swagger):** http://localhost:8000/docs

## Остановка
Для завершения работы контейнеров выполните:

```bash
docker compose down
```