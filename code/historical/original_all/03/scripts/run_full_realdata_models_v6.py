from __future__ import annotations

import json
import math
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
from scipy.stats import norm, t as student_t

warnings.filterwarnings("ignore")

ROOT = Path(os.environ.get("AFIRE_COUNTY_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
DATA = ROOT / "data_processed"
EXT = ROOT / "data_external" / "processed"
TABLES = ROOT / "tables"
LOGS = ROOT / "logs"
TABLES.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)

STATUS_PATH = LOGS / "covariate_build_status_v6.json"
BASE_PATH = DATA / "county_year_disease_panel_base_v5.csv"
COV_PATH = EXT / "county_year_real_covariates_v6.csv"
DRAWS_PATH = DATA / "imputed_deaths_eb_history_v5.npz"


def zscore(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    standard_deviation = values.std(ddof=1)
    if pd.isna(standard_deviation) or standard_deviation <= 0:
        return pd.Series(np.nan, index=series.index)
    return (values - values.mean()) / standard_deviation


def rubin_pool(estimates, within_variances) -> dict:
    q = np.asarray(estimates, dtype=float)
    u = np.asarray(within_variances, dtype=float)
    m = len(q)
    qbar = float(q.mean())
    ubar = float(u.mean())
    between = float(q.var(ddof=1)) if m > 1 else 0.0
    total = ubar + (1 + 1 / m) * between
    standard_error = math.sqrt(max(total, 0.0))
    if ubar > 0:
        relative_increase = (1 + 1 / m) * between / ubar
    else:
        relative_increase = np.inf if between > 0 else 0.0
    if m > 1 and np.isfinite(relative_increase) and relative_increase > 0:
        degrees_freedom = (m - 1) * (1 + 1 / relative_increase) ** 2
    else:
        degrees_freedom = 1e12
    critical = (
        float(student_t.ppf(0.975, degrees_freedom))
        if degrees_freedom < 1e8
        else 1.959963984540054
    )
    if standard_error > 0:
        statistic = abs(qbar / standard_error)
        p_value = (
            float(2 * student_t.sf(statistic, degrees_freedom))
            if degrees_freedom < 1e8
            else float(2 * norm.sf(statistic))
        )
    else:
        p_value = np.nan
    fraction_missing_information = (
        float((relative_increase + 2 / (degrees_freedom + 3)) / (relative_increase + 1))
        if np.isfinite(relative_increase) and relative_increase >= 0
        else 1.0
    )
    return {
        "estimate": qbar,
        "standard_error": standard_error,
        "ci_low": qbar - critical * standard_error,
        "ci_high": qbar + critical * standard_error,
        "p_value": p_value,
        "m_used": m,
        "within_variance": ubar,
        "between_variance": between,
        "total_variance": total,
        "df_rubin": degrees_freedom,
        "fraction_missing_information": fraction_missing_information,
        "monte_carlo_error": math.sqrt(between / m) if m > 1 else 0.0,
    }


def bh_adjust(pvalues: pd.Series) -> pd.Series:
    p = pd.to_numeric(pvalues, errors="coerce")
    result = pd.Series(np.nan, index=p.index, dtype=float)
    valid = p.notna()
    if not valid.any():
        return result
    values = p.loc[valid].to_numpy()
    order = np.argsort(values)
    ranked = values[order]
    m = len(ranked)
    adjusted = ranked * m / np.arange(1, m + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0, 1)
    inverse = np.empty_like(order)
    inverse[order] = np.arange(m)
    result.loc[valid] = adjusted[inverse]
    return result


def coverage(data: pd.DataFrame, variables: list[str], first_year: int, last_year: int) -> dict:
    subset = data.loc[data["year"].between(first_year, last_year)]
    return {
        variable: (
            float(subset[variable].notna().mean())
            if variable in subset.columns and len(subset)
            else 0.0
        )
        for variable in variables
    }


def load_data() -> tuple[pd.DataFrame, np.ndarray, dict]:
    if not STATUS_PATH.exists():
        raise RuntimeError("Run scripts/build_real_covariate_panel.py before the model script")
    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    if not (BASE_PATH.exists() and COV_PATH.exists() and DRAWS_PATH.exists()):
        raise RuntimeError("The v5 panel, real-covariate panel, or MI draw file is missing")

    base = pd.read_csv(BASE_PATH, low_memory=False)
    base = base.loc[base["cause_id"].eq("copd")].copy()
    covariates = pd.read_csv(COV_PATH, low_memory=False)
    for column in ["county_fips", "year"]:
        base[column] = pd.to_numeric(base[column], errors="coerce")
        covariates[column] = pd.to_numeric(covariates[column], errors="coerce")
    base = base.dropna(subset=["county_fips", "year"]).copy()
    covariates = covariates.dropna(subset=["county_fips", "year"]).copy()
    base["county_fips"] = base["county_fips"].astype("int64")
    base["year"] = base["year"].astype("int64")
    covariates["county_fips"] = covariates["county_fips"].astype("int64")
    covariates["year"] = covariates["year"].astype("int64")
    data = base.merge(covariates, on=["county_fips", "year"], how="left", validate="many_to_one")
    data["county_model"] = data["county_fips"].astype("int64").astype(str)
    data["year_model"] = data["year"].astype("int64").astype(str)
    data["state_year"] = data["state_abbr"].astype(str) + "_" + data["year_model"]

    if "population_density_km2" in data:
        data["log_population_density"] = np.log1p(
            pd.to_numeric(data["population_density_km2"], errors="coerce")
        )
    else:
        data["log_population_density"] = np.nan
    standardized = {
        "age65_std": "age65_share",
        "density_std": "log_population_density",
        "temp_annual_std": "temperature_annual_mean",
        "temp_fs_std": "temperature_fireseason_mean",
        "precip_fs_std": "precipitation_fireseason_total",
        "ozone_fs_std": "ozone_fireseason_mean",
        "pm25_total_std": "pm25_annual_mean",
        "nonwildfire_pm25_std": "nonwildfire_pm25_candidate",
        "smoking_std": "smoking_prevalence",
    }
    for output_column, input_column in standardized.items():
        data[output_column] = zscore(data[input_column]) if input_column in data.columns else np.nan

    draws = np.load(DRAWS_PATH)["draws"]
    return data, draws, status


def nonwildfire_compatibility(data: pd.DataFrame) -> dict:
    required = ["nonwildfire_pm25_candidate", "nonwildfire_negative_flag", "pm25_annual_mean"]
    if not all(column in data.columns for column in required):
        return {"usable": False, "reason": "candidate_not_available"}
    subset = data.loc[data["year"].between(2009, 2020)].copy()
    valid = subset["nonwildfire_pm25_candidate"].notna()
    if valid.mean() < 0.95:
        return {
            "usable": False,
            "reason": "candidate_less_than_95_percent_complete",
            "coverage": float(valid.mean()),
        }
    values = subset.loc[valid, "nonwildfire_pm25_candidate"]
    negative_fraction = float(values.lt(0).mean())
    result = {
        "usable": bool(negative_fraction <= 0.01),
        "reason": "ok" if negative_fraction <= 0.01 else "negative_fraction_above_1_percent",
        "coverage": float(valid.mean()),
        "negative_fraction": negative_fraction,
        "minimum": float(values.min()),
        "p01": float(values.quantile(0.01)),
        "median": float(values.median()),
        "p99": float(values.quantile(0.99)),
        "maximum": float(values.max()),
        "warning": (
            "Subtraction is treated as a sensitivity analysis because total and wildfire PM2.5 products "
            "may use different spatial weighting and modeling systems."
        ),
    }
    return result


def fit_one_specification(
    data: pd.DataFrame,
    draws_all: np.ndarray,
    specification: str,
    rhs: str,
    required_variables: list[str],
    first_year: int,
    last_year: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    needed = ["population", "pm25_iqr", "ses_std", "county_fips", "year", "row_id"] + required_variables
    subset = data.loc[data["year"].between(first_year, last_year)].dropna(subset=needed).copy()
    subset = subset.loc[pd.to_numeric(subset["population"], errors="coerce") > 0].copy()
    if len(subset) == 0 or subset["county_fips"].nunique() < 30:
        raise RuntimeError(f"{specification}: insufficient complete observations")

    design_frame = patsy.dmatrix(rhs, subset, return_type="dataframe")
    names = list(design_frame.columns)
    design = np.asarray(design_frame, dtype=float)
    term_index = {name: index for index, name in enumerate(names)}
    target_terms = ["pm25_iqr", "ses_std", "pm25_iqr:ses_std"]
    for term in target_terms:
        if term not in term_index:
            raise RuntimeError(f"{specification}: design matrix is missing {term}")

    row_index = subset["row_id"].astype(int).to_numpy()
    draws = draws_all[:, row_index]
    offset = np.log(subset["population"].to_numpy(float))
    groups = subset["county_fips"].astype(int).to_numpy()
    mean_outcome = draws.mean(axis=0)

    poisson = sm.GLM(mean_outcome, design, family=sm.families.Poisson(), offset=offset).fit(maxiter=150)
    expected = np.asarray(poisson.fittedvalues, dtype=float)
    alpha_numerator = np.sum((mean_outcome - expected) ** 2 - mean_outcome)
    alpha_denominator = max(np.sum(expected**2), 1e-12)
    alpha = float(np.clip(alpha_numerator / alpha_denominator, 0.001, 2.0))
    warm_fit = sm.GLM(
        mean_outcome,
        design,
        family=sm.families.NegativeBinomial(alpha=alpha),
        offset=offset,
    ).fit(start_params=np.asarray(poisson.params, dtype=float), maxiter=150)
    warm_parameters = np.asarray(warm_fit.params, dtype=float)

    per_imputation: list[dict] = []
    failures: list[dict] = []
    for imputation_number, outcome in enumerate(draws, start=1):
        try:
            fit = sm.GLM(
                outcome,
                design,
                family=sm.families.NegativeBinomial(alpha=alpha),
                offset=offset,
            ).fit(
                start_params=warm_parameters,
                maxiter=80,
                cov_type="cluster",
                cov_kwds={"groups": groups},
            )
            warm_parameters = np.asarray(fit.params, dtype=float)
            for term in target_terms:
                index = term_index[term]
                per_imputation.append(
                    {
                        "specification": specification,
                        "imputation": imputation_number,
                        "term": term,
                        "estimate": float(fit.params[index]),
                        "within_variance": float(fit.bse[index] ** 2),
                        "converged": bool(fit.converged),
                    }
                )
        except Exception as exc:
            failures.append(
                {
                    "specification": specification,
                    "imputation": imputation_number,
                    "error": repr(exc),
                }
            )

    per_frame = pd.DataFrame(per_imputation)
    if per_frame.empty:
        raise RuntimeError(f"{specification}: all imputation-specific models failed")
    pooled_rows: list[dict] = []
    for term, group in per_frame.groupby("term"):
        pooled = rubin_pool(group["estimate"], group["within_variance"])
        pooled.update(
            specification=specification,
            term=term,
            n_observations=int(len(subset)),
            n_counties=int(subset["county_fips"].nunique()),
            year_min=int(subset["year"].min()),
            year_max=int(subset["year"].max()),
            nb_alpha_fixed=alpha,
            successful_imputations=int(group["imputation"].nunique()),
            n_parameters=int(design.shape[1]),
        )
        pooled["irr"] = math.exp(pooled["estimate"])
        pooled["irr_ci_low"] = math.exp(pooled["ci_low"])
        pooled["irr_ci_high"] = math.exp(pooled["ci_high"])
        pooled["percent_change"] = (pooled["irr"] - 1) * 100
        pooled["percent_change_ci_low"] = (pooled["irr_ci_low"] - 1) * 100
        pooled["percent_change_ci_high"] = (pooled["irr_ci_high"] - 1) * 100
        pooled_rows.append(pooled)
    return pd.DataFrame(pooled_rows), per_frame, pd.DataFrame(failures)


def main() -> None:
    data, draws, build_status = load_data()
    compatibility = nonwildfire_compatibility(data)
    (LOGS / "nonwildfire_pm25_compatibility_v6.json").write_text(
        json.dumps(compatibility, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    specifications: list[dict] = [
        {
            "name": "M1_v5_baseline_2006_2020",
            "rhs": "pm25_iqr + ses_std + pm25_iqr:ses_std + C(county_model) + C(year_model)",
            "required": [],
            "year_min": 2006,
            "year_max": 2020,
            "tier": "baseline",
        }
    ]

    core_variables = ["temp_fs_std", "age65_std", "density_std"]
    core_coverage = coverage(data, core_variables, 2009, 2020)
    core_ready = all(value >= 0.95 for value in core_coverage.values())
    if core_ready:
        specifications.extend(
            [
                {
                    "name": "M2_core_real_covariates_2009_2020",
                    "rhs": (
                        "pm25_iqr + ses_std + pm25_iqr:ses_std + temp_fs_std + age65_std + "
                        "density_std + C(county_model) + C(year_model)"
                    ),
                    "required": core_variables,
                    "year_min": 2009,
                    "year_max": 2020,
                    "tier": "core",
                },
                {
                    "name": "M3_state_by_year_FE_2009_2020",
                    "rhs": (
                        "pm25_iqr + ses_std + pm25_iqr:ses_std + temp_fs_std + age65_std + "
                        "density_std + C(county_model) + C(state_year)"
                    ),
                    "required": core_variables,
                    "year_min": 2009,
                    "year_max": 2020,
                    "tier": "strict",
                },
            ]
        )

    environmental_variables: list[str] = []
    if coverage(data, ["precip_fs_std"], 2009, 2020)["precip_fs_std"] >= 0.95:
        environmental_variables.append("precip_fs_std")
    if coverage(data, ["ozone_fs_std"], 2009, 2020)["ozone_fs_std"] >= 0.95:
        environmental_variables.append("ozone_fs_std")
    if core_ready and environmental_variables:
        environmental_text = " + ".join(environmental_variables)
        specifications.append(
            {
                "name": "M4_environmental_covariates_2009_2020",
                "rhs": (
                    "pm25_iqr + ses_std + pm25_iqr:ses_std + temp_fs_std + age65_std + "
                    f"density_std + {environmental_text} + C(county_model) + C(year_model)"
                ),
                "required": core_variables + environmental_variables,
                "year_min": 2009,
                "year_max": 2020,
                "tier": "environmental",
            }
        )

    if core_ready and compatibility.get("usable"):
        specifications.append(
            {
                "name": "M5_nonwildfire_PM25_adjusted_2009_2020",
                "rhs": (
                    "pm25_iqr + ses_std + pm25_iqr:ses_std + temp_fs_std + age65_std + "
                    "density_std + nonwildfire_pm25_std + C(county_model) + C(year_model)"
                ),
                "required": core_variables + ["nonwildfire_pm25_std"],
                "year_min": 2009,
                "year_max": 2020,
                "tier": "nonwildfire_pm25_sensitivity",
            }
        )

    smoking_variables = core_variables + ["smoking_std"]
    smoking_coverage = coverage(data, smoking_variables, 2018, 2020)
    if all(value >= 0.95 for value in smoking_coverage.values()):
        specifications.append(
            {
                "name": "M6_PLACES_smoking_sensitivity_2018_2020",
                "rhs": (
                    "pm25_iqr + ses_std + pm25_iqr:ses_std + temp_fs_std + age65_std + "
                    "density_std + smoking_std + C(county_model) + C(year_model)"
                ),
                "required": smoking_variables,
                "year_min": 2018,
                "year_max": 2020,
                "tier": "smoking_sensitivity",
            }
        )

    planned_names = {item["name"] for item in specifications}
    skipped = []
    if not core_ready:
        skipped.extend(
            [
                {
                    "specification": "M2_core_real_covariates_2009_2020",
                    "status": "skipped_missing_real_covariates",
                    "message": json.dumps(core_coverage),
                },
                {
                    "specification": "M3_state_by_year_FE_2009_2020",
                    "status": "skipped_missing_real_covariates",
                    "message": json.dumps(core_coverage),
                },
            ]
        )
    if "M5_nonwildfire_PM25_adjusted_2009_2020" not in planned_names:
        skipped.append(
            {
                "specification": "M5_nonwildfire_PM25_adjusted_2009_2020",
                "status": "skipped_product_incompatibility_or_missing",
                "message": json.dumps(compatibility),
            }
        )
    if "M6_PLACES_smoking_sensitivity_2018_2020" not in planned_names:
        skipped.append(
            {
                "specification": "M6_PLACES_smoking_sensitivity_2018_2020",
                "status": "skipped_missing_optional_smoking",
                "message": json.dumps(smoking_coverage),
            }
        )

    pooled_all: list[pd.DataFrame] = []
    per_all: list[pd.DataFrame] = []
    failures_all: list[pd.DataFrame] = []
    run_status: list[dict] = skipped.copy()
    for item in specifications:
        print(f"Fitting {item['name']}", flush=True)
        try:
            pooled, per_imputation, failures = fit_one_specification(
                data,
                draws,
                item["name"],
                item["rhs"],
                item["required"],
                item["year_min"],
                item["year_max"],
            )
            pooled["model_tier"] = item["tier"]
            pooled_all.append(pooled)
            per_all.append(per_imputation)
            if not failures.empty:
                failures_all.append(failures)
            run_status.append(
                {
                    "specification": item["name"],
                    "status": "completed",
                    "message": "",
                }
            )
        except Exception as exc:
            run_status.append(
                {
                    "specification": item["name"],
                    "status": "failed",
                    "message": repr(exc),
                }
            )

    if pooled_all:
        pooled_output = pd.concat(pooled_all, ignore_index=True)
        interaction_mask = pooled_output["term"].eq("pm25_iqr:ses_std")
        pooled_output.loc[interaction_mask, "p_fdr_bh"] = bh_adjust(
            pooled_output.loc[interaction_mask, "p_value"]
        )
        pooled_output.to_csv(
            TABLES / "copd_full_realdata_models_v6.csv", index=False, encoding="utf-8-sig"
        )
        pooled_output.to_csv(
            TABLES / "copd_full_realdata_models_v6_1.csv", index=False, encoding="utf-8-sig"
        )
        pd.concat(per_all, ignore_index=True).to_csv(
            TABLES / "copd_full_realdata_per_imputation_v6.csv.gz",
            index=False,
            compression="gzip",
        )
    if failures_all:
        pd.concat(failures_all, ignore_index=True).to_csv(
            TABLES / "copd_full_realdata_model_failures_v6.csv",
            index=False,
            encoding="utf-8-sig",
        )
    status_frame = pd.DataFrame(run_status).sort_values("specification")
    status_frame.to_csv(TABLES / "full_model_run_status_v6.csv", index=False, encoding="utf-8-sig")
    status_frame.to_csv(TABLES / "full_model_run_status_v6_1.csv", index=False, encoding="utf-8-sig")
    summary = {
        "build_status": build_status,
        "core_covariate_coverage_2009_2020": core_coverage,
        "smoking_covariate_coverage_2018_2020": smoking_coverage,
        "nonwildfire_compatibility": compatibility,
        "completed_models": status_frame.loc[status_frame["status"].eq("completed"), "specification"].tolist(),
        "skipped_or_failed_models": status_frame.loc[~status_frame["status"].eq("completed")].to_dict("records"),
    }
    (LOGS / "full_model_summary_v6_1.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(status_frame.to_string(index=False))


if __name__ == "__main__":
    main()
