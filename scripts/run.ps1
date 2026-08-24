$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

if (-not (Test-Path "data\videostream.db")) {
    Write-Host "Seeding database with demo users and videos..."
    .\.venv\Scripts\python.exe scripts\seed.py
}

Write-Host "Starting VideoStream on http://localhost:8000 (docs at /docs)"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
