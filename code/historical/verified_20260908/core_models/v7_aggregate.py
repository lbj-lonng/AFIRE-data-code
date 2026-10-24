from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from v7_common import MODEL_RESULTS, ROOT, TABLES, bh_adjust, effect_scale, load_config, rubin_pool
from v7_specs import SPEC_BY_ID


def read_existing_v63() -> pd.DataFrame:
    path = ROOT / "existing_results_v6_3" / "tables" / "pooled_available_models_v6_3.csv"
    if not path.exists():
        return pd.DataFrame()
    x = pd.read_csv(path)
    mapping = {
        "M1_baseline_SES_fixed_2006_2020": "O01_baseline_SES_fixed_2006_2020",
        "M2_Census_adjusted_2009_2020": "O02_Census_adjusted_2009_2020",
        "M3_Census_state_year_FE_2009_2020": "O03_state_year_PPML_2009_2020",
        "M4_Census_drought_adjusted_2009_2020": "O04_drought_adjusted_2009_2020",
        "M5_exclude_2020_Census_drought": "O05_exclude_2020_drought",
        "M6_timevarying_SES_2010_2020": "O06_timevarying_SES_2010_2020",
        "M7_lag1_Census_drought_2010_2020": "O07_lag1_2010_2020",
        "M8_lead1_placebo_Census_drought_2009_2019": "O08_lead1_placebo_2009_2019",
        "M9_three_state_air_sensitivity_2009_2020": "O09_three_state_air_2009_2020",
        "M10_temperature_adjusted_2009_2020": "O10_temperature_adjusted_2009_2020",
        "M11_full_environment_six_state_2009_2020": "O11_full_environment_2009_2020",
        "M12_smoking_sensitivity_2018_2020": "O12_smoking_2018_2020",
    }
    x["source_version"] = "v6_3_imported"
    specification = x.get("specification", pd.Series("", index=x.index)).astype(str)
    x["model_id"] = specification.map(mapping).fillna(specification)
    x["label"] = x["model_id"].map(
        {model_id: spec.label for model_id, spec in SPEC_BY_ID.items()}
    ).fillna(specification)
    x["group"] = x["model_id"].map(
        {model_id: spec.group for model_id, spec in SPEC_BY_ID.items()}
    ).fillna("legacy_v6_3")
    x["cause_id"] = "copd"
    return x


def marginal_effects() -> pd.DataFrame:
    config = load_config()
    ses_values = list(config.get("ses_marginal_values", [-2, -1, 0, 1, 2]))
    target_models = [
        "O10_temperature_adjusted_2009_2020",
        "O11_full_environment_2009_2020",
        "F03_nonwildfire_PM25_2009_2020",
    ]
    rows = []
    for model_id in target_models:
        model_dir = MODEL_RESULTS / model_id
        per_path = model_dir / "per_imputation.csv.gz"
        cov_path = model_dir / "target_covariance.csv.gz"
        if not per_path.exists() or not cov_path.exists():
            continue
        spec = SPEC_BY_ID[model_id]
        per = pd.read_csv(per_path)
        cov = pd.read_csv(cov_path)
        wide_est = per.pivot(index="imputation", columns="term", values="estimate")
        wide_var = per.pivot(index="imputation", columns="term", values="within_variance")
        common = wide_est.index.intersection(wide_var.index).intersection(cov["imputation"])
        cov_map = cov.set_index("imputation")["covariance"]
        for ses in ses_values:
            estimates = []
            variances = []
            for imp in common:
                b0 = float(wide_est.loc[imp, spec.exposure_term])
                b1 = float(wide_est.loc[imp, spec.interaction_term])
                v0 = float(wide_var.loc[imp, spec.exposure_term])
                v1 = float(wide_var.loc[imp, spec.interaction_term])
                c01 = float(cov_map.loc[imp])
                estimates.append(b0 + float(ses) * b1)
                variances.append(v0 + float(ses) ** 2 * v1 + 2 * float(ses) * c01)
            pooled = rubin_pool(estimates, variances)
            pooled.update({
                "model_id": model_id,
                "label": spec.label,
                "ses_sd": float(ses),
                "interpretation": "每增加1个野火PM2.5 IQR的死亡率变化",
            })
            rows.append(effect_scale(pooled))
    return pd.DataFrame(rows)


def main() -> None:
    pooled_frames = []
    status_rows = []
    failure_frames = []
    for model_dir in sorted(MODEL_RESULTS.iterdir()) if MODEL_RESULTS.exists() else []:
        if not model_dir.is_dir():
            continue
        status_path = model_dir / "status.json"
        if status_path.exists():
            status_rows.append(json.loads(status_path.read_text(encoding="utf-8")))
        pooled_path = model_dir / "pooled.csv"
        if pooled_path.exists():
            x = pd.read_csv(pooled_path)
            x["source_version"] = "v7"
            pooled_frames.append(x)
        failure_path = model_dir / "failures.csv"
        if failure_path.exists():
            try:
                f = pd.read_csv(failure_path)
                if not f.empty:
                    failure_frames.append(f)
            except pd.errors.EmptyDataError:
                pass

    pooled = pd.concat(pooled_frames, ignore_index=True) if pooled_frames else pd.DataFrame()
    existing = read_existing_v63()
    if not existing.empty:
        if pooled.empty:
            pooled = existing
        else:
            # v7 estimates take priority over imported v6.3 estimates with the same model name.
            existing = existing.loc[~existing["model_id"].isin(set(pooled["model_id"]))]
            pooled = pd.concat([pooled, existing], ignore_index=True, sort=False)

    if not pooled.empty:
        interaction = pooled["term"].astype(str).str.contains(":", regex=False)
        pooled["p_fdr_group"] = np.nan
        if "group" in pooled.columns:
            for _, index in pooled.loc[interaction].groupby("group").groups.items():
                pooled.loc[index, "p_fdr_group"] = bh_adjust(pooled.loc[index, "p_value"])
        pooled.loc[interaction, "p_fdr_all_interactions"] = bh_adjust(
            pooled.loc[interaction, "p_value"]
        )
        pooled.to_csv(TABLES / "all_pooled_models_v7.csv", index=False, encoding="utf-8-sig")
        interactions = pooled.loc[interaction].copy()
        interactions.to_csv(TABLES / "interaction_summary_v7.csv", index=False, encoding="utf-8-sig")

        primary_ids = [
            "O03_state_year_PPML_2009_2020",
            "O10_temperature_adjusted_2009_2020",
            "O11_full_environment_2009_2020",
            "F01_temperature_exclude_2020",
            "F02_full_environment_exclude_2020",
            "F03_nonwildfire_PM25_2009_2020",
            "F04_nonwildfire_PM25_exclude_2020",
            "F05_poverty_modifier_2009_2020",
            "F06_period_2009_2016",
            "F07_period_2017_2020",
        ]
        interactions.loc[interactions["model_id"].isin(primary_ids)].to_csv(
            TABLES / "paper_main_and_key_sensitivity_v7.csv", index=False, encoding="utf-8-sig"
        )
        for group, filename in [
            ("leave_one_year", "leave_one_year_out_v7.csv"),
            ("leave_one_state", "leave_one_state_out_v7.csv"),
            ("state_specific", "state_specific_v7.csv"),
            ("secondary_outcomes", "secondary_outcomes_v7.csv"),
        ]:
            interactions.loc[interactions.get("group", "").eq(group)].to_csv(
                TABLES / filename, index=False, encoding="utf-8-sig"
            )

    pd.DataFrame(status_rows).to_csv(TABLES / "model_status_v7.csv", index=False, encoding="utf-8-sig")
    failures = pd.concat(failure_frames, ignore_index=True) if failure_frames else pd.DataFrame(
        columns=["model_id", "imputation", "status", "error"]
    )
    failures.to_csv(TABLES / "model_failures_v7.csv", index=False, encoding="utf-8-sig")

    marginal = marginal_effects()
    marginal.to_csv(TABLES / "marginal_effects_v7.csv", index=False, encoding="utf-8-sig")

    statuses = pd.DataFrame(status_rows)
    summary = {
        "models_completed": int(statuses["status"].eq("completed").sum()) if not statuses.empty else 0,
        "models_incomplete": int(statuses["status"].eq("incomplete").sum()) if not statuses.empty else 0,
        "models_blocked": int(statuses["status"].eq("blocked").sum()) if not statuses.empty else 0,
        "marginal_effect_rows": int(len(marginal)),
    }
    (TABLES / "final_experiment_summary_v7.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
