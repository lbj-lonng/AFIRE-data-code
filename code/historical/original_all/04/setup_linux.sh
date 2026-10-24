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
PYTHONPATH=scripts python scripts/self_test_v7.py
printf '\n环境安装完成。下一步把两个数据文件放入 data_processed，然后运行：\n'
printf 'bash 01_validate_data_linux.sh\n'
