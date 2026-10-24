#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON:-python3}"

if [[ -n "${AFIRE_DATA_ROOT:-}" && ! -d "$AFIRE_DATA_ROOT" ]]; then
  echo "AFIRE_DATA_ROOT does not exist: $AFIRE_DATA_ROOT"
  exit 1
fi

"$PYTHON_BIN" scripts/run_all.py
