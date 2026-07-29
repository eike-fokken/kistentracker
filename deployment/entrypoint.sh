#!/bin/sh
# Backend container entrypoint: apply migrations, collect static assets, then
# hand off to gunicorn. Runs from the folder that contains manage.py so the
# `dbtrials.wsgi` module resolves (see the nested package layout).
set -e

cd /app/dbtrials

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn dbtrials.wsgi:application \
    --bind "0.0.0.0:${GUNICORN_PORT:-8000}" \
    --workers "${GUNICORN_WORKERS:-3}" \
    --access-logfile - \
    --error-logfile -
