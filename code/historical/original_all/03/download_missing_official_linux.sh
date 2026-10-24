#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export AFIRE_COUNTY_PROJECT_ROOT="$ROOT"
if [[ -f .venv/bin/activate ]]; then source .venv/bin/activate; fi
# Census files are already included and validated; no Census key is required.
python scripts/download_real_covariates.py --source noaa
python scripts/download_real_covariates.py --source pm25 --force
python scripts/download_real_covariates.py --source ozone --force || echo "Ozone download failed; it remains optional."
python scripts/download_real_covariates.py --source places --force || echo "PLACES download failed; it remains a short-period sensitivity input."
python scripts/diagnose_external_covariates.py
python scripts/prepare_integrated_data_v6_3.py
printf '\nMissing official datasets were refreshed. Run bash run_full_linux.sh next.\n'
