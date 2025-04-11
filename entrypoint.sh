#!/bin/bash

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
