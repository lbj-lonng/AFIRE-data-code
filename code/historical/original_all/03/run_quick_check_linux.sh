#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export AFIRE_COUNTY_PROJECT_ROOT="$ROOT"
if [[ -f .venv/bin/activate ]]; then source .venv/bin/activate; fi
python scripts/validate_census_only.py
python scripts/prepare_integrated_data_v6_3.py
mkdir -p logs/screening_results_v6_3
for i in $(seq 1 12); do
  status_file=$(find logs/screening_results_v6_3 -maxdepth 1 -name "$(printf '%02d' "$i")_*.json" -print -quit || true)
  if [[ -n "$status_file" ]] && grep -q '"status": "completed"' "$status_file"; then
    echo "Screening model $i already completed; skipping."
  else
    python scripts/run_one_screening_v6_3.py --index "$i" || echo "Screening model $i did not finish; see logs."
  fi
done
python scripts/aggregate_screening_v6_3.py
python scripts/generate_status_report_v6_3.py
printf '\nQuick check finished. Read reports/实施结果与后续运行说明_v6_3.md\n'
