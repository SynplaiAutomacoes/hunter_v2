#!/bin/sh
set -e

echo "Syncronizing webhook"
uv run python manage.py webhook

echo "Creating migrations"
uv run python manage.py makemigrations --noinput

echo "Running migrations..."
uv run python manage.py migrate --noinput

echo "Starting gunicorn..."
exec uv run gunicorn config.wsgi:application --bind 0.0.0.0:8000

