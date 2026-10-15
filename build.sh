#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# Frontend bundle goes into screening/static/ before collectstatic picks it up.
npm ci --include=dev --prefix frontend
npm run build --prefix frontend

python manage.py collectstatic --no-input

python manage.py migrate

python manage.py loaddata questions_fixture.json