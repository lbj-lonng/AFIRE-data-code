from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from v7_common import DRAWS_PATH, PANEL_PATH, TABLES, load_analysis_data, write_json
from v7_specs import ALL_SPECS


def main() -> None:
    rows: list[dict] = []
    try:
        data, draws = load_analysis_data()
    except Exception as exc:
        print(f"DATA VALIDATION FAILED: {exc}")
        raise SystemExit(1)

    rows.extend([
        {"check": "panel_exists", "status": "PASS", "value": str(PANEL_PATH)},
        {"check": "draws_exists", "status": "PASS", "value": str(DRAWS_PATH)},
        {"check": "panel_rows", "status": "PASS" if len(data) >= 26880 else "WARN", "value": len(data)},
        {"check": "draws_shape", "status": "PASS" if draws.shape[0] >= 30 else "FAIL", "value": str(draws.shape)},
        {"check": "row_id_unique", "status": "PASS" if data["row_id"].is_unique else "FAIL", "value": data["row_id"].nunique()},
        {"check": "counties", "status": "PASS" if data["county_fips"].nunique() == 256 else "WARN", "value": data["county_fips"].nunique()},
        {"check": "years", "status": "PASS", "value": f"{data['year'].min()}-{data['year'].max()}"},
        {"check": "causes", "status": "PASS" if data["cause_id"].nunique() >= 7 else "WARN", "value": data["cause_id"].nunique()},
    ])

    copd = data.loc[data["cause_id"].eq("copd")].drop_duplicates(["county_fips", "year"])
    coverage_vars = [
        "pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7",
        "drought_d1_fs_std_v7", "temperature_fs_std_v7", "pm25_total_std_v7",
        "ozone_std_v7", "nonwildfire_pm25_std_v7", "smoking_std_v7",
    ]
    for var in coverage_vars:
        if var in {"age65_std_v7", "density_std_v7", "pm25_total_std_v7", "ozone_std_v7", "nonwildfire_pm25_std_v7"}:
            period = copd.loc[copd["year"].between(2009, 2020)]
        elif var == "smoking_std_v7":
            period = copd.loc[copd["year"].between(2018, 2020)]
        else:
            period = copd
        if var not in period.columns:
            coverage = 0.0
        else:
            coverage = float(period[var].notna().mean())
        expected = 0.95
        rows.append({
            "check": f"coverage_{var}",
            "status": "PASS" if coverage >= expected else "WARN",
            "value": f"{coverage:.2%}",
        })

    candidate = pd.to_numeric(copd.get("nonwildfire_pm25_candidate"), errors="coerce")
    neg_share = float(candidate.lt(0).mean()) if len(candidate) else np.nan
    rows.append({
        "check": "nonwildfire_negative_share",
        "status": "PASS" if np.isfinite(neg_share) and neg_share <= 0.01 else "WARN",
        "value": f"{neg_share:.2%}" if np.isfinite(neg_share) else "NA",
    })

    cause_counts = data.groupby("cause_id")["row_id"].count().to_dict()
    for cause in sorted({s.cause_id for s in ALL_SPECS}):
        rows.append({
            "check": f"cause_{cause}",
            "status": "PASS" if cause_counts.get(cause, 0) >= 3000 else "WARN",
            "value": cause_counts.get(cause, 0),
        })

    frame = pd.DataFrame(rows)
    frame.to_csv(TABLES / "data_validation_v7.csv", index=False, encoding="utf-8-sig")
    summary = {
        "status": "ready" if not frame["status"].eq("FAIL").any() else "failed",
        "panel_rows": int(len(data)),
        "draws_shape": list(draws.shape),
        "counties": int(data["county_fips"].nunique()),
        "causes": sorted(data["cause_id"].astype(str).unique().tolist()),
        "failed_checks": frame.loc[frame["status"].eq("FAIL"), "check"].tolist(),
        "warnings": frame.loc[frame["status"].eq("WARN"), "check"].tolist(),
    }
    write_json(TABLES / "data_validation_v7.json", summary)
    print(frame.to_string(index=False))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["status"] != "ready":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
