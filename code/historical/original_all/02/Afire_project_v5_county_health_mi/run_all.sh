#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export AFIRE_COUNTY_PROJECT_ROOT="$ROOT"
python "$ROOT/scripts/run_all.py"
