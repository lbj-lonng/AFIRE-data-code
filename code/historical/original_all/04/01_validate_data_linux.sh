#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export AFIRE_PROJECT_ROOT="$ROOT"
[[ -f .venv/bin/activate ]] && source .venv/bin/activate
python -u scripts/v7_validate.py 2>&1 | tee logs/01_validate_data.log
