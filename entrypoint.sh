#!/bin/bash
set -e

mysql -u $DATABASE_USERNAME -p $DATABASE_PASSWORD -e 'CREATE DATABASE $DATABASE_NAME;'

python manage.py makemigrations

python manage.py migrate

exec "$@"
