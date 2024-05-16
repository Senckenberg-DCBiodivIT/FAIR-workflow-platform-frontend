#!/bin/bash

echo "Collect static files"
python manage.py collectstatic --no-input --clear

echo "Apply database migrations"
python manage.py migrate --noinput

# running command
echo "running $@"
gunicorn cwr_frontend.wsgi:application --bind 0.0.0.0:8000
