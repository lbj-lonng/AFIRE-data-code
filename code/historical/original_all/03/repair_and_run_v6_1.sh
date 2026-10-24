#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export AFIRE_COUNTY_PROJECT_ROOT="$ROOT"
python "$ROOT/scripts/self_test_v6_1.py"
python "$ROOT/scripts/download_real_covariates.py" --source census
python "$ROOT/scripts/download_real_covariates.py" --source noaa --force
python "$ROOT/scripts/download_real_covariates.py" --source pm25 --force
python "$ROOT/scripts/download_real_covariates.py" --source ozone --force || echo 'Ozone failed; optional.'
python "$ROOT/scripts/download_real_covariates.py" --source places --force || echo 'PLACES smoking failed; optional.'
python "$ROOT/scripts/diagnose_external_covariates.py"
python "$ROOT/scripts/build_real_covariate_panel.py"
python "$ROOT/scripts/run_full_realdata_models_v6.py"
