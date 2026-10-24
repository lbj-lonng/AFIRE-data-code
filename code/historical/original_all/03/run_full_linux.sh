#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export AFIRE_COUNTY_PROJECT_ROOT="$ROOT"
if [[ -f .venv/bin/activate ]]; then source .venv/bin/activate; fi
python scripts/validate_census_only.py
python scripts/prepare_integrated_data_v6_3.py
mkdir -p logs/model_results_v6_3
for i in $(seq 1 12); do
  status_file=$(find logs/model_results_v6_3 -maxdepth 1 -name "$(printf '%02d' "$i")_*_status.json" -print -quit || true)
  if [[ -n "$status_file" ]] && grep -q '"status": "completed"' "$status_file"; then
    echo "Full MI model $i already completed; skipping."
  else
    echo "Running full MI model $i/12. Results are checkpointed after each model."
    python scripts/run_one_model_checkpointed_v6_3.py --index "$i"
  fi
done
python scripts/aggregate_models_v6_3.py
python scripts/generate_status_report_v6_3.py
printf '\nFull 30-imputation analysis finished.\n'
