#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then
  echo "用法：bash run_one_model_linux.sh MODEL_ID"
  echo "查看模型ID：python scripts/list_models.py"
  exit 1
fi
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export AFIRE_PROJECT_ROOT="$ROOT"
[[ -f .venv/bin/activate ]] && source .venv/bin/activate
python -u scripts/v7_run_model.py --model-id "$1" 2>&1 | tee "logs/$1.log"
