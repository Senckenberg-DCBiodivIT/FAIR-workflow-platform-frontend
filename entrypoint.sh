#!/bin/bash
set -e

if [ -f /app/cwr_frontend/.env ]; then
  export $(grep -v '^#' /app/cwr_frontend/.env | xargs)
fi

if [ "$USE_POSTGRES" = "TRUE" ]; then
  # Wait for Postgres
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

# running gunicorn. Increased timeout due to ro crate zip parsing
gunicorn cwr_frontend.wsgi:application \
    --bind 0.0.0.0:8000 \
    --timeout ${GUNICORN_TIMEOUT:-120} \
    --workers ${GUNICORN_WORKERS:-2} \
    --threads ${GUNICORN_THREADS:-5} \
    --access-logfile -  
