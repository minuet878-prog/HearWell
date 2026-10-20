#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# Production security settings first: a warning stops the build before anything changes.
python manage.py check --deploy --fail-level WARNING

# Frontend bundle goes into screening/static/ before collectstatic picks it up.
npm ci --include=dev --prefix frontend
npm run build --prefix frontend

python manage.py collectstatic --no-input

python manage.py migrate

python manage.py loaddata questions_fixture.json

# Add questionnaires defined in code without assigning ids that could overwrite old questions.
python manage.py seed_questionnaires
