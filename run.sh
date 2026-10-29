#!/usr/bin/env bash
# Start the email agent with one command: ./run.sh
# Starts the API (backend/) and the web app (frontend/). The first run installs everything.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "Missing .env: copy .env.example to .env and fill OPENROUTER_API_KEY and FIRECRAWL_API_KEY." >&2
  exit 1
fi

cd backend
if [ ! -d .venv ]; then
  python3.14 -m venv .venv
fi
.venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt

.venv/bin/uvicorn app.main:create_app --factory --port 8000 &
trap 'kill $!' EXIT  # stop the API when the frontend stops (Ctrl+C)

cd ../frontend
if [ ! -d node_modules ]; then
  npm install
fi
echo "Open http://localhost:5173 (API on http://localhost:8000, docs on http://localhost:8000/docs)"
npm run dev
