#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
chmod +x ./*.sh
python scripts/self_test_census_v6_2.py
python scripts/self_test_v6_1.py
printf '\nLinux environment is ready. Next run: bash run_quick_check_linux.sh\n'
