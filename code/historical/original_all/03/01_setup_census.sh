#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export AFIRE_COUNTY_PROJECT_ROOT="$ROOT"
cd "$ROOT"
python -c 'import pandas, requests' 2>/dev/null || python -m pip install -r requirements_census.txt
if [[ -z "${CENSUS_API_KEY:-}" && ! -f config/census_api_key.env ]]; then
  python scripts/configure_census_key.py
fi
python scripts/census_first_download.py
printf '\nCensus stage completed. Next: bash 03_run_remaining_pipeline.sh\n'
