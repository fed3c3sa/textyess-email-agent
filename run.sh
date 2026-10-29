#!/usr/bin/env bash
# Start the email agent with one command: ./run.sh
# The first run creates the Python environment and installs the dependencies.
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

echo "API on http://localhost:8000 (interactive docs on http://localhost:8000/docs)"
exec .venv/bin/uvicorn app.main:create_app --factory --port 8000
