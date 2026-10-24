#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export AFIRE_PROJECT_ROOT="$ROOT"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
[[ -f .venv/bin/activate ]] && source .venv/bin/activate
WORKERS="${AFIRE_WORKERS:-2}"
python -u scripts/v7_run_suite.py --suite final --workers "$WORKERS" 2>&1 | tee logs/03_final_suite.log
python -u scripts/v7_aggregate.py 2>&1 | tee logs/03_aggregate.log
python -u scripts/v7_figures.py 2>&1 | tee logs/03_figures.log
python -u scripts/v7_report.py 2>&1 | tee logs/03_report.log
python -u scripts/v7_final_check.py 2>&1 | tee logs/03_final_check.log
