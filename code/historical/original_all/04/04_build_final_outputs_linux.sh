#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export AFIRE_PROJECT_ROOT="$ROOT"
[[ -f .venv/bin/activate ]] && source .venv/bin/activate
python -u scripts/v7_aggregate.py
python -u scripts/v7_figures.py
python -u scripts/v7_report.py
python -u scripts/v7_final_check.py
