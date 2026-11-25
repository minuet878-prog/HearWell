#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
cd ..
echo "==> project dir:" "$(pwd)"

PY=".venv/bin/python"

echo "==> update file from git:"
git pull --ff-only origin main

echo "==> install dependencies:"
"$PY" -m pip install -r requirements.txt

echo "==> check before deploy:"
"$PY" manage.py check --deploy --fail-level WARNING

echo "==> set up node:"
FNM="/home/jason/.local/share/fnm/fnm"
eval "$("$FNM" env --shell bash)"
"$FNM" use --install-if-missing

echo "==> build frontend:"
npm ci --include=dev --prefix frontend
npm run build --prefix frontend

echo "==> collect static files:"
"$PY" manage.py collectstatic --no-input

echo "==> apply migration:"
"$PY" manage.py migrate --plan
"$PY" manage.py migrate

echo "==> create cache table:"
"$PY" manage.py createcachetable

echo "==> load data fixture and seed questionnaires:"
"$PY" manage.py loaddata questions_fixture.json
"$PY" manage.py seed_questionnaires

echo "==> restart service and check if deploy successful:"
sudo systemctl restart hearwell
systemctl status hearwell --no-pager
curl -sS -o /dev/null --fail --retry 10 --retry-delay 1 --retry-connrefused https://tingpal.tw/

echo "==> deploy done ✅"

