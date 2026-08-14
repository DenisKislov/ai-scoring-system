FROM python:3.10-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY api/requirements.txt api/
COPY scorer/requirements.txt scorer/

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r api/requirements.txt -r scorer/requirements.txt

# Копируем остальной код бэкенда и базы данных
COPY api/ api/
COPY scorer/ scorer/
COPY db/ db/
COPY data/ data/

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]