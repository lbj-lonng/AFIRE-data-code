#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export AFIRE_COUNTY_PROJECT_ROOT="$ROOT"
cd "$ROOT"
python - <<'PY'
import json
from pathlib import Path
p=Path('logs/census_status_v6_2.json')
if not p.exists() or json.loads(p.read_text(encoding='utf-8')).get('status') != 'ready':
    raise SystemExit('Census has not passed validation. Run bash 01_setup_census.sh first.')
PY
python scripts/download_real_covariates.py --source noaa
python scripts/download_real_covariates.py --source pm25
python scripts/download_real_covariates.py --source ozone || true
python scripts/download_real_covariates.py --source places || true
python scripts/diagnose_external_covariates.py
python scripts/build_real_covariate_panel.py
python scripts/run_full_realdata_models_v6.py
