#!/usr/bin/env bash
# ETIP one-command launcher (macOS / Linux).
# Creates the virtual environment, installs, migrates, seeds demo data on first
# run, starts the server, and opens the dashboard. Press Ctrl+C to stop.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
export DATABASE_URL="${DATABASE_URL:-sqlite:///./etip_demo.db}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-demo-secret-key-32-bytes-minimum-xxxx}"

# 1. Virtual environment
if [ ! -d .venv ]; then
  echo "==> Creating virtual environment (.venv)..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 2. Install the project (only if not already importable)
if ! python -c "import app" >/dev/null 2>&1; then
  echo "==> Installing ETIP and dependencies (first run only)..."
  pip install -q --upgrade pip
  pip install -q -e .
fi

# 4. Database schema
echo "==> Applying database migrations..."
alembic upgrade head

# 5. Start the server in the background
echo "==> Starting server on http://localhost:${PORT} ..."
uvicorn app.main:app --port "${PORT}" &
SERVER_PID=$!
trap 'echo; echo "==> Stopping server..."; kill ${SERVER_PID} 2>/dev/null || true' EXIT INT TERM

# 6. Wait until it answers
for _ in $(seq 1 30); do
  curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1 && break
  sleep 1
done

# 7. Seed demo data unless the demo admin already logs in.
#    We probe the login endpoint rather than checking for the DB file, because
#    migrations create the file before any data exists — so a file check would
#    wrongly skip seeding after a first run whose seed did not complete.
LOGIN_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
  -X POST "http://localhost:${PORT}/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  --data-binary '{"organization_slug":"demo-transformation-co","email":"admin@demo.co","password":"Str0ng-Passphrase!1"}' || echo "000")
if [ "${LOGIN_CODE}" != "200" ]; then
  echo "==> Seeding demo data (login probe returned ${LOGIN_CODE})..."
  python scripts/seed_demo.py || echo "   (seed reported an issue — see output above)"
else
  echo "==> Demo data already present; skipping seed."
fi

URL="http://localhost:${PORT}/"
echo ""
echo "======================================================================"
echo "  ETIP is running:   ${URL}"
echo "  API browser:       http://localhost:${PORT}/docs"
echo ""
echo "  Sign in (admin):   organization  demo-transformation-co"
echo "                     email         admin@demo.co"
echo "                     password      Str0ng-Passphrase!1"
echo "  Read-only viewer:  viewer@demo.co  (same org / password)"
echo ""
echo "  Press Ctrl+C to stop."
echo "======================================================================"

# 8. Open the browser (best effort)
( command -v open   >/dev/null 2>&1 && open   "${URL}" ) 2>/dev/null || \
( command -v xdg-open >/dev/null 2>&1 && xdg-open "${URL}" ) 2>/dev/null || true

# 9. Keep the server in the foreground
wait ${SERVER_PID}
