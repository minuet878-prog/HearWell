#!/usr/bin/env bash
set -o errexit

# TEMPORARY: check whether Node is available in Render's Python build (Phase 4).
node --version || echo "node: not available"
npm --version || echo "npm: not available"

pip install -r requirements.txt

python manage.py collectstatic --no-input

python manage.py migrate

python manage.py loaddata questions_fixture.json