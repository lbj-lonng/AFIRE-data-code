from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("AFIRE_COUNTY_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
TABLES = ROOT / "tables"
LOGS.mkdir(exist_ok=True)


def run(script: str, required: bool = True, extra_args: list[str] | None = None) -> int:
    command = [sys.executable, str(ROOT / "scripts" / script)] + (extra_args or [])
    print("\n>>>", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0 and required:
        raise SystemExit(completed.returncode)
    return completed.returncode


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    download_requested = os.environ.get("AFIRE_DOWNLOAD_EXTERNAL", "0") == "1"
    status: dict = {
        "started_utc": started,
        "download_requested": download_requested,
        "download_status": "not_requested",
        "diagnostic_status": "pending",
        "build_status": "pending",
        "model_status": "pending",
    }
    try:
        if download_requested:
            status["download_status"] = "running"
            run("download_real_covariates.py", required=True)
            status["download_status"] = "completed"

        run("diagnose_external_covariates.py", required=False)
        status["diagnostic_status"] = "completed"
        run("build_real_covariate_panel.py", required=True)
        status["build_status"] = "completed"
        build_status = json.loads(
            (LOGS / "covariate_build_status_v6.json").read_text(encoding="utf-8")
        )
        status["covariate_status"] = build_status

        # The model runner always preserves M1 and conditionally executes M2-M6.
        # It never inserts simulated/constant replacements for missing covariates.
        run("run_full_realdata_models_v6.py", required=True)
        model_status_path = TABLES / "full_model_run_status_v6_1.csv"
        if model_status_path.exists():
            import pandas as pd

            model_status = pd.read_csv(model_status_path)
            completed_count = int(model_status["status"].eq("completed").sum())
            skipped_count = int(model_status["status"].str.startswith("skipped").sum())
            failed_count = int(model_status["status"].eq("failed").sum())
            status["model_status"] = (
                "completed_all_available_models" if failed_count == 0 else "completed_with_failures"
            )
            status["completed_model_count"] = completed_count
            status["skipped_model_count"] = skipped_count
            status["failed_model_count"] = failed_count
        else:
            status["model_status"] = "runner_completed_without_status_table"
    finally:
        status["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (LOGS / "pipeline_status_v6.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (LOGS / "pipeline_status_v6_1.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print("\nPipeline status:", json.dumps(status, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
