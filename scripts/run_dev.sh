#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pip install -r requirements.txt
python examples/demo.py
echo
echo "Starting API on http://127.0.0.1:8000/docs"
python -m uvicorn controlplane.api:app --reload
