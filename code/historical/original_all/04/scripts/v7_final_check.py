from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from v7_common import FIGURES, REPORTS, TABLES
from v7_specs import ALL_SPECS, ESSENTIAL_FINAL_IDS


def main() -> None:
    status_path = TABLES / "model_status_v7.csv"
    if not status_path.exists():
        raise FileNotFoundError("缺少 model_status_v7.csv，请先运行聚合。")
    status = pd.read_csv(status_path)
    completed = set(status.loc[status["status"].eq("completed"), "model_id"].astype(str))
    expected = set(ESSENTIAL_FINAL_IDS)
    missing = sorted(expected - completed)
    required_files = [
        TABLES / "interaction_summary_v7.csv",
        TABLES / "paper_main_and_key_sensitivity_v7.csv",
        TABLES / "marginal_effects_v7.csv",
        TABLES / "leave_one_year_out_v7.csv",
        TABLES / "leave_one_state_out_v7.csv",
        TABLES / "state_specific_v7.csv",
        TABLES / "secondary_outcomes_v7.csv",
        REPORTS / "Afire_v7_final_experiment_report.md",
    ]
    rows = []
    rows.append({
        "check": "essential_models_completed",
        "status": "PASS" if not missing else "FAIL",
        "detail": ",".join(missing) if missing else f"{len(expected)} models",
    })
    for path in required_files:
        rows.append({
            "check": f"file_{path.name}",
            "status": "PASS" if path.exists() and path.stat().st_size > 0 else "FAIL",
            "detail": str(path),
        })
    frame = pd.DataFrame(rows)
    frame.to_csv(TABLES / "final_check_v7.csv", index=False, encoding="utf-8-sig")
    summary = {
        "status": "complete" if frame["status"].eq("PASS").all() else "incomplete",
        "essential_models_expected": len(expected),
        "essential_models_completed": len(expected - set(missing)),
        "missing_models": missing,
    }
    (TABLES / "final_check_v7.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(frame.to_string(index=False))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["status"] != "complete":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
