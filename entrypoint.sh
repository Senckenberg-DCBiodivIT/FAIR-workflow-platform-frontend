#!/bin/bash

echo "Collect static files"
python manage.py collectstatic --no-input --clear

echo "Apply database migrations"
python manage.py migrate --noinput

echo "Creating superuser"
python manage.py createsuperuser --noinput
if [ $? -ne 0 ]; then
  echo "Failed to create superuser"
  exit 1
fi

# running gunicorn. Increased timeout due to ro crate zip parsing
gunicorn cwr_frontend.wsgi:application \
    --bind 0.0.0.0:8000 \
    --timeout ${GUNICORN_TIMEOUT:-120} \
    --workers ${GUNICORN_WORKERS:-2} \
    --threads ${GUNICORN_THREADS:-5}
