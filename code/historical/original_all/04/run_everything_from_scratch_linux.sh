#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export AFIRE_PROJECT_ROOT="$ROOT"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
[[ -f .venv/bin/activate ]] && source .venv/bin/activate
bash 01_validate_data_linux.sh
bash 02_quick_check_linux.sh
WORKERS="${AFIRE_WORKERS:-2}"
python -u scripts/v7_run_suite.py --suite all --workers "$WORKERS" 2>&1 | tee logs/all_models_from_scratch.log
bash 04_build_final_outputs_linux.sh
