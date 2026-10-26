FROM python:3.13-slim@sha256:98ce6fb13b3803744fbca11434f00818f1e300e4e48a4f204e07b2c928b6218e
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY api/ api/
COPY scorer/ scorer/
COPY db/ db/
COPY config/ config/
# Only synthetic templates are part of the distributable image.
COPY data/__init__.py data/profiles.py data/synthetic.py data/synthetic_roles.json data/
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
