#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi

if [ ! -f "data/videostream.db" ]; then
  echo "Seeding database with demo users and videos..."
  .venv/bin/python scripts/seed.py
fi

echo "Starting VideoStream on http://localhost:8000 (docs at /docs)"
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
