#!/bin/sh
set -e

echo "Syncronizing webhook"
uv run python manage.py webhook

echo "Running migrations..."
uv run python manage.py migrate --noinput

echo "Starting gunicorn..."
exec uv run gunicorn config.wsgi:application --config gunicorn.conf.py
