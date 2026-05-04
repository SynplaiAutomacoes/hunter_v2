#!/bin/sh
set -e

echo "Syncronizing webhook"
python manage.py webhook

echo "Running migrations..."
python manage.py migrate --noinput

echo "Starting gunicorn..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-2}" --threads "${GUNICORN_THREADS:-4}"

