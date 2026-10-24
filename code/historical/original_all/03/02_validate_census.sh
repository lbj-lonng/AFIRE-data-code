#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export AFIRE_COUNTY_PROJECT_ROOT="$ROOT"
cd "$ROOT"
python scripts/validate_census_only.py
