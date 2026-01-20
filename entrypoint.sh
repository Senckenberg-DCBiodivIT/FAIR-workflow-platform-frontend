#!/bin/bash
set -e

if [ "$USE_POSTGRES" = "TRUE" ]; then
  echo "Waiting for Postgres at $POSTGRES_HOST:$POSTGRES_PORT..."
  until nc -z $POSTGRES_HOST $POSTGRES_PORT; do
    sleep 1
  done
  echo "Postgres is up - continuing..."
fi

echo "Collect static files"
python manage.py collectstatic --no-input --clear

echo "Apply database migrations"
python manage.py migrate --noinput

FRONTEND_PORT=${FRONTEND_PORT:-8000}
echo "Starting Gunicorn on port $FRONTEND_PORT..."

exec gunicorn cwr_frontend.wsgi:application \
    --bind 0.0.0.0:$FRONTEND_PORT \
    --timeout ${GUNICORN_TIMEOUT:-120} \
    --workers ${GUNICORN_WORKERS:-2} \
    --threads ${GUNICORN_THREADS:-5} \
    --access-logfile -
