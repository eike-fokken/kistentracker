# Backend image: Django + gunicorn, serving /api, /admin and (via WhiteNoise)
# the collected static files. Build context is the repository root.
FROM docker.io/library/python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.1.3 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# Install Poetry, then the project's runtime dependencies only.
# No poetry.lock is committed, so generate one at build time before installing.
RUN pip install "poetry==${POETRY_VERSION}"
COPY pyproject.toml ./
RUN poetry install --only main --no-root

# Application code (nested package: manage.py lives in dbtrials/).
COPY dbtrials/ ./dbtrials/
COPY deployment/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Persistent data (SQLite db) and collected static live under /app/data
# and /app/staticfiles respectively.
RUN mkdir -p /app/data /app/staticfiles

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
