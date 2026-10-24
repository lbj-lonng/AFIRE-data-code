#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
bash 01_validate_data_linux.sh
bash 02_quick_check_linux.sh
bash 03_run_final_missing_experiments_linux.sh
