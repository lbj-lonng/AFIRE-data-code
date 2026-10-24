#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then
  echo "用法：bash import_existing_v6_3_results.sh /绝对路径/Afire_project_v6_3..."
  exit 1
fi
ROOT="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$(realpath "$1")"
DEST="$ROOT/existing_results_v6_3/tables"
mkdir -p "$DEST"
for name in pooled_available_models_v6_3.csv model_run_status_v6_3.csv model_failures_v6_3.csv per_imputation_available_models_v6_3.csv.gz; do
  if [[ -f "$SOURCE/tables/$name" ]]; then
    cp -f "$SOURCE/tables/$name" "$DEST/$name"
    echo "Imported $name"
  else
    echo "Not found (optional): $SOURCE/tables/$name"
  fi
done
