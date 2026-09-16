#!/usr/bin/env bash
# Runs once when the Codespace/devcontainer is created.
# Prepares airflow/.env with generated secrets and boots Airflow.
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/airflow"

if [ ! -f .env ]; then
  cp .env.template .env
  SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  ADMIN_PW="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
  sed -i "s|^AIRFLOW__WEBSERVER__SECRET_KEY=.*|AIRFLOW__WEBSERVER__SECRET_KEY=${SECRET}|" .env
  sed -i "s|^AIRFLOW_ADMIN_PASSWORD=.*|AIRFLOW_ADMIN_PASSWORD=${ADMIN_PW}|" .env
  echo "======================================================"
  echo " Airflow UI login (SAVE THIS — shown once):"
  echo "   username: admin"
  echo "   password: ${ADMIN_PW}"
  echo "======================================================"
  echo "(airflow/.env created; it is git-ignored. Add your real"
  echo " OPENAI_API_KEY / VAPID keys there if you want tasks to run.)"
fi

echo ">> Building and starting Airflow (first build takes a few minutes)..."
docker compose up -d || {
  echo "!! docker compose failed. Run manually: cd airflow && docker compose up -d"
  exit 0
}
echo ">> Done. Open the PORTS tab, set port 8080 visibility to 'Public',"
echo "   then open the forwarded URL and log in as admin."
