from __future__ import annotations

import json

import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm

from v7_common import TABLES, filter_spec_data, load_analysis_data
from v7_engine import build_design, estimate_nb_alpha
from v7_specs import ALL_SPECS, SPEC_BY_ID


def main() -> None:
    data, draws = load_analysis_data()
    rows = []
    for spec in ALL_SPECS:
        try:
            subset = filter_spec_data(data, spec)
            _, design, _, _ = build_design(subset, spec)
            rows.append({
                "model_id": spec.model_id,
                "group": spec.group,
                "status": "READY",
                "rows": len(subset),
                "counties": subset["county_fips"].nunique(),
                "parameters": design.shape[1],
                "reason": "",
            })
        except Exception as exc:
            rows.append({
                "model_id": spec.model_id,
                "group": spec.group,
                "status": "BLOCKED",
                "rows": 0,
                "counties": 0,
                "parameters": 0,
                "reason": repr(exc),
            })
    status = pd.DataFrame(rows)
    status.to_csv(TABLES / "quick_design_check_v7.csv", index=False, encoding="utf-8-sig")
    print(status.groupby(["group", "status"]).size().to_string())

    key_models = [
        "O03_state_year_PPML_2009_2020",
        "O10_temperature_adjusted_2009_2020",
        "F01_temperature_exclude_2020",
        "F03_nonwildfire_PM25_2009_2020",
    ]
    fit_rows = []
    for model_id in key_models:
        spec = SPEC_BY_ID[model_id]
        try:
            subset = filter_spec_data(data, spec)
            _, design, names, indices = build_design(subset, spec)
            y = draws[:, subset["row_id"].astype(int).to_numpy()].mean(axis=0)
            offset = np.log(subset["population"].to_numpy(float))
            if spec.family == "poisson":
                fit = sm.GLM(y, design, family=sm.families.Poisson(), offset=offset).fit(maxiter=300)
                alpha = np.nan
            else:
                alpha, warm = estimate_nb_alpha(y, design, offset)
                fit = sm.GLM(
                    y, design,
                    family=sm.families.NegativeBinomial(alpha=alpha),
                    offset=offset,
                ).fit(start_params=warm, maxiter=300)
            beta = float(fit.params[indices[spec.interaction_term]])
            fit_rows.append({
                "model_id": model_id,
                "status": "COMPLETED",
                "interaction_estimate": beta,
                "interaction_percent_change": (np.exp(beta) - 1) * 100,
                "nb_alpha": alpha,
            })
            print(f"{model_id}: interaction={(np.exp(beta)-1)*100:.3f}%")
        except Exception as exc:
            fit_rows.append({"model_id": model_id, "status": "FAILED", "error": repr(exc)})
            print(f"{model_id}: FAILED {exc}")
    pd.DataFrame(fit_rows).to_csv(TABLES / "quick_mean_imputation_models_v7.csv", index=False, encoding="utf-8-sig")
    if status["status"].eq("BLOCKED").any():
        print("部分扩展模型被数据覆盖率阻塞；详见 quick_design_check_v7.csv。")


if __name__ == "__main__":
    main()
