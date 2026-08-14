FROM python:3.10-slim

WORKDIR /app

# Ставим системные компиляторы для тяжелых ML-библиотек
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt api/
COPY scorer/requirements.txt scorer/

# Качаем пакеты с максимальной толерантностью к обрывам сети
RUN pip install --no-cache-dir --default-timeout=1000 --retries 10 -r api/requirements.txt -r scorer/requirements.txt

# Скачиваем русскую модель для spacy
RUN python -m spacy download ru_core_news_sm

COPY api/ api/
COPY scorer/ scorer/
COPY db/ db/
COPY data/ data/

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]