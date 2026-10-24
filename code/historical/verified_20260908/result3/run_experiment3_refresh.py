#!/usr/bin/env python3
"""Refresh research-content-3 models after county death imputation changes.

No manuscript is edited.  Existing fixed-EB 0--9 results are reused.  Missing
paired models are fitted for fixed-EB 1--9 and two hierarchical-EB boundaries.
Smoking and any model search are explicitly outside scope.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
_SCRIPT_OUTPUT_ROOT = Path(__file__).resolve().parents[1]
_MPL_CACHE = _SCRIPT_OUTPUT_ROOT / "logs/matplotlib"
_MPL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPL_CACHE))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parents[1]
CONFIG_DEFAULT = HERE / "config/experiment3_refresh.json"
TABLES = HERE / "tables"
CHECKPOINTS = HERE / "models/checkpoints"
FIGURES = HERE / "figures"
REPORTS = HERE / "reports"
LOGS = HERE / "logs"

P4 = ROOT / "experiment_feasibility_20260906/source_snapshot/all/04"
STAGE2_COMMON = ROOT / "experiment_validation_stage2_20260906/01_common_sample_models.csv"
PRECIP_RESULT = ROOT / "experiment_framework_revision_20260908/tables/05_precipitation_extension_model.csv"
OLD_ALL_MODELS = P4 / "results/tables/all_pooled_models_v7.csv"
OLD_LST_RESULTS = ROOT / "experiment_closeout_v3/paired_LST_results_complete.csv"
LST_PANEL = ROOT / "experiment_longrun_20260906/processed/main_2009_2020_v3/county_year_LST_long.csv"
FIXED_B1 = ROOT / "experiment_validation_stage3_20260906/copd_B1_1_9_draws.npz"
HIER_B0 = ROOT / "experiment_suppression_innovation_20260908/outputs/imputations/COPD_hierarchical_exact_margin_bem_hbmi_pilot_v2_0_9.npz"
HIER_B1 = ROOT / "experiment_suppression_innovation_20260908/outputs/imputations/COPD_hierarchical_exact_margin_bem_hbmi_pilot_v2_1_9.npz"

os.environ["AFIRE_PROJECT_ROOT"] = str(P4)
sys.path.insert(0, str(P4 / "scripts"))
from v7_common import ModelSpec, filter_spec_data, load_analysis_data, rubin_pool, zscore_series  # noqa: E402
from v7_engine import build_design, estimate_nb_alpha, fit_negative_binomial  # noqa: E402


TERM = "pm25_iqr:ses_baseline_std"
M0 = "pm25_iqr + pm25_iqr:ses_baseline_std + C(county_model) + C(year_model)"
M1 = "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + C(county_model) + C(year_model)"
M2 = "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)"
M2P = "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + precipitation_fs_std_extension + C(county_model) + C(year_model)"
M3 = "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + nonwildfire_pm25_std_v7 + ozone_std_v7 + C(county_model) + C(year_model)"
POVERTY = "pm25_iqr + pm25_iqr:poverty_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + C(county_model) + C(year_model)"
TIME_SES = "pm25_iqr + ses_timevarying_std + pm25_iqr:ses_timevarying_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + C(county_model) + C(year_model)"

REQ = {
    "M0": ("pm25_iqr", "ses_baseline_std"),
    "M1": ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7"),
    "M2": ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7"),
    "M2P": ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7", "precipitation_fs_std_extension"),
    "M3": ("pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7", "nonwildfire_pm25_std_v7", "ozone_std_v7"),
    "poverty_baseline": ("pm25_iqr", "poverty_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7"),
    "time_varying_SES": ("pm25_iqr", "ses_timevarying_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7"),
}
FORMULA = {"M0": M0, "M1": M1, "M2": M2, "M2P": M2P, "M3": M3,
           "poverty_baseline": POVERTY, "time_varying_SES": TIME_SES}


def ensure_dirs() -> None:
    for p in (TABLES, CHECKPOINTS, FIGURES, REPORTS, LOGS):
        p.mkdir(parents=True, exist_ok=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def key_hash(d: pd.DataFrame) -> str:
    x = d[["county_fips", "year"]].drop_duplicates().sort_values(["county_fips", "year"])
    s = "\n".join(f"{int(a):05d}-{int(b)}" for a, b in x.itertuples(index=False, name=None))
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def spec(mid: str, formula: str, required: tuple[str, ...], *, term: str = TERM,
         year_min: int = 2009, year_max: int = 2020) -> ModelSpec:
    return ModelSpec(model_id=mid, label=mid, group="experiment3_imputation_refresh",
                     cause_id="copd", family="negative_binomial", rhs=formula,
                     exposure_term="pm25_iqr", interaction_term=term,
                     required=required, year_min=year_min, year_max=year_max,
                     min_rows=100, min_counties=10)


def load_scenarios(config: dict, old_b0: np.ndarray) -> dict:
    out = {"fixed_EB_B0_0_9": {"draws": old_b0, "row_ids": None,
                                "source": P4 / "data_processed/imputed_deaths_eb_history_v5.npz",
                                "draw_selection": "archived 30"}}
    z = np.load(FIXED_B1)
    out["fixed_EB_B1_1_9"] = {"draws": z["draws"], "row_ids": z["row_ids"],
                               "source": FIXED_B1, "draw_selection": "all 30"}
    within = config["hierarchical_draw_selection"]["selected_within_chain_zero_based"]
    per_chain = config["hierarchical_draw_selection"]["draws_per_chain_available"]
    selected = np.array([c * per_chain + j for c in range(3) for j in within], dtype=int)
    for name, path in [("hierarchical_EB_B0_0_9", HIER_B0),
                       ("hierarchical_EB_B1_1_9", HIER_B1)]:
        z = np.load(path)
        if z["draws"].shape[0] != 90:
            raise RuntimeError(f"{name}: expected 90 hierarchical draws")
        out[name] = {"draws": z["draws"][selected], "row_ids": z["row_ids"],
                     "source": path, "draw_selection": "balanced 10 per chain from 90"}
    return out


def outcomes_for(sub: pd.DataFrame, scenario: dict) -> np.ndarray:
    if scenario["row_ids"] is None:
        return scenario["draws"][:, sub.row_id.astype(int).to_numpy()].astype(float)
    mapper = pd.Series(np.arange(len(scenario["row_ids"])), index=scenario["row_ids"].astype(int))
    loc = mapper.loc[sub.row_id.astype(int)].to_numpy(int)
    return scenario["draws"][:, loc].astype(float)


def fit_job(job_id: str, sub: pd.DataFrame, formula: str, required: tuple[str, ...],
            interaction_term: str, scenario_name: str, scenario: dict,
            analysis_block: str, lst_added: bool = False, qa: str = "not_applicable",
            period: str = "not_applicable") -> dict:
    cp = CHECKPOINTS / f"{job_id}.json"
    signature = {
        "job_id": job_id, "formula": formula, "sample_hash": key_hash(sub),
        "scenario": scenario_name, "draw_source_hash": sha256(scenario["source"]),
        "n_draws": int(len(scenario["draws"])), "term": interaction_term,
    }
    old = json.loads(cp.read_text()) if cp.exists() else {}
    if old.get("status") == "completed_and_validated" and old.get("signature") == signature:
        print(f"reuse {job_id}", flush=True)
        return old

    sp = spec(job_id, formula, required, term=interaction_term,
              year_min=int(sub.year.min()), year_max=int(sub.year.max()))
    _, X, _, idx = build_design(sub, sp)
    if np.linalg.matrix_rank(X) != X.shape[1]:
        raise RuntimeError(f"{job_id}: rank deficient design")
    outcomes = outcomes_for(sub, scenario)
    offset = np.log(sub.population.to_numpy(float))
    groups = sub.county_fips.to_numpy(int)
    alpha, warm = estimate_nb_alpha(outcomes.mean(axis=0), X, offset)
    fits = old.get("fits", []) if old.get("signature") == signature else []
    done = {int(x["imputation"]) for x in fits if x.get("status") == "ok"}
    started = time.time()
    j = idx[interaction_term]
    for m, y in enumerate(outcomes, 1):
        if m in done:
            continue
        try:
            fit, _ = fit_negative_binomial(y, X, offset, groups, alpha, warm)
            fits.append({"imputation": m, "estimate": float(fit.params[j]),
                         "variance": float(fit.cov_params()[j, j]), "status": "ok"})
        except Exception as exc:
            fits.append({"imputation": m, "status": "failed", "error": repr(exc)})
        cp.write_text(json.dumps({"status": "running", "signature": signature,
                                  "fits": fits}, indent=2), encoding="utf-8")
    good = [x for x in fits if x.get("status") == "ok"]
    if len(good) != len(outcomes):
        raise RuntimeError(f"{job_id}: {len(good)}/{len(outcomes)} fits completed")
    pool = rubin_pool([x["estimate"] for x in good], [x["variance"] for x in good])
    result = {
        "status": "completed_and_validated", "signature": signature, "fits": fits,
        "analysis_block": analysis_block, "model_id": job_id,
        "model_family": job_id.split("__")[0], "imputation_scenario": scenario_name,
        "imputation_draw_selection": scenario["draw_selection"],
        "beta": pool["estimate"], "SE": pool["standard_error"],
        "beta_CI_lower": pool["ci_low"], "beta_CI_upper": pool["ci_high"],
        "interaction_percent": 100 * math.expm1(pool["estimate"]),
        "CI_percent_lower": 100 * math.expm1(pool["ci_low"]),
        "CI_percent_upper": 100 * math.expm1(pool["ci_high"]),
        "P_value": pool["p_value"], "within_variance": pool["within_variance"],
        "between_imputation_variance": pool["between_variance"],
        "fraction_missing_information": pool["fraction_missing_information"],
        "monte_carlo_error": pool["monte_carlo_error"],
        "n_imputations": len(good), "n_county_years": len(sub),
        "n_counties": int(sub.county_fips.nunique()),
        "n_states": int(sub.state_abbr.nunique()), "sample_hash": key_hash(sub),
        "year_min": int(sub.year.min()), "year_max": int(sub.year.max()),
        "formula": formula, "interaction_term": interaction_term,
        "design_rank": int(np.linalg.matrix_rank(X)), "design_columns": int(X.shape[1]),
        "nb_alpha": float(alpha), "convergence": f"{len(good)}/{len(outcomes)}",
        "LST_added": bool(lst_added), "QA_rule": qa, "day_or_night": period,
        "elapsed_seconds": time.time() - started,
    }
    cp.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"complete {job_id}: {result['interaction_percent']:.4f}% "
          f"({result['CI_percent_lower']:.4f}, {result['CI_percent_upper']:.4f})",
          flush=True)
    return result


def prepare_data() -> tuple[pd.DataFrame, np.ndarray]:
    data, old_b0 = load_analysis_data()
    u = data[["county_fips", "year", "precipitation_fireseason_total"]].drop_duplicates(["county_fips", "year"])
    u["precipitation_fs_std_extension"] = zscore_series(u.precipitation_fireseason_total)
    mapper = u.set_index(["county_fips", "year"]).precipitation_fs_std_extension
    data["precipitation_fs_std_extension"] = pd.MultiIndex.from_frame(
        data[["county_fips", "year"]]).map(mapper)
    return data, old_b0


def imputation_change_summary(data: pd.DataFrame, scenarios: dict) -> None:
    c = data.loc[data.cause_id.eq("copd")].sort_values("row_id").copy()
    sup = c.death_suppressed.astype(bool).to_numpy()
    sub = c.loc[sup].copy()
    means = {}
    for name, sc in scenarios.items():
        means[name] = outcomes_for(sub, sc).mean(axis=0)
    rows = []
    ref = means["fixed_EB_B0_0_9"]
    scopes = {
        "all_suppressed_COPD": np.ones(len(sub), bool),
        "2020": sub.year.eq(2020).to_numpy(),
        "California": sub.state_abbr.eq("CA").to_numpy(),
        "California_x_2020": (sub.state_abbr.eq("CA") & sub.year.eq(2020)).to_numpy(),
        "other": (~(sub.state_abbr.eq("CA") | sub.year.eq(2020))).to_numpy(),
    }
    for name, x in means.items():
        for scope, mask in scopes.items():
            if not mask.any():
                continue
            rows.append({"scenario": name, "scope": scope, "n_suppressed_cells": int(mask.sum()),
                         "mean_imputed_count": float(x[mask].mean()),
                         "mean_absolute_change_vs_fixed_B0": float(np.abs(x[mask] - ref[mask]).mean()),
                         "max_absolute_change_vs_fixed_B0": float(np.abs(x[mask] - ref[mask]).max()),
                         "correlation_with_fixed_B0": float(np.corrcoef(x[mask], ref[mask])[0, 1]) if mask.sum() > 1 else np.nan})
    pd.DataFrame(rows).to_csv(TABLES / "00_county_death_imputation_change_summary.csv", index=False)


def old_common_rows() -> pd.DataFrame:
    d = pd.read_csv(STAGE2_COMMON)
    d = d[d.model_id.isin(["M0", "M1", "M2", "M3"])].copy()
    rows = []
    for _, r in d.iterrows():
        rows.append({"analysis_block": "common_covariate", "model_id": r.model_id,
                     "model_family": r.model_id, "imputation_scenario": "fixed_EB_B0_0_9",
                     "beta": r.interaction_beta, "SE": r.pooled_SE,
                     "interaction_percent": r.interaction_percent,
                     "CI_percent_lower": r.CI_lower, "CI_percent_upper": r.CI_upper,
                     "P_value": r.P_value, "n_imputations": r.n_imputations,
                     "n_county_years": r.n_county_years, "n_counties": r.n_counties,
                     "n_states": 6, "sample_hash": str(r.sample_id).replace("common_", ""),
                     "formula": r.formula, "interaction_term": TERM,
                     "LST_added": False, "QA_rule": "not_applicable",
                     "day_or_night": "not_applicable", "status": "reused_validated"})
    p = pd.read_csv(PRECIP_RESULT).iloc[0]
    rows.append({"analysis_block": "common_covariate", "model_id": "M2P",
                 "model_family": "M2P", "imputation_scenario": "fixed_EB_B0_0_9",
                 "beta": p.interaction_beta, "SE": p.pooled_SE,
                 "interaction_percent": p.interaction_percent,
                 "CI_percent_lower": p.CI_lower, "CI_percent_upper": p.CI_upper,
                 "P_value": p.P_value, "n_imputations": p.n_imputations,
                 "n_county_years": p.n_county_years, "n_counties": p.n_counties,
                 "n_states": 6, "sample_hash": p.sample_hash, "formula": p.formula,
                 "interaction_term": TERM, "LST_added": False,
                 "QA_rule": "not_applicable", "day_or_night": "not_applicable",
                 "status": "reused_validated"})
    return pd.DataFrame(rows)


def run_common(data: pd.DataFrame, scenarios: dict) -> pd.DataFrame:
    m3sp = spec("common_sample", M3, REQ["M3"])
    common = filter_spec_data(data, m3sp).sort_values(["county_fips", "year"]).copy()
    if len(common) != 3062 or key_hash(common) != "d15d10108a6a2bac":
        raise RuntimeError("common covariate key set no longer matches the frozen 3,062-row sample")
    rows = old_common_rows().to_dict("records")
    for scenario_name in ["fixed_EB_B1_1_9", "hierarchical_EB_B0_0_9", "hierarchical_EB_B1_1_9"]:
        sc = scenarios[scenario_name]
        for family in ["M0", "M1", "M2", "M2P", "M3"]:
            job = f"{family}__common__{scenario_name}"
            rows.append(fit_job(job, common, FORMULA[family], REQ[family], TERM,
                                scenario_name, sc, "common_covariate"))
    out = pd.DataFrame(rows)
    out.to_csv(TABLES / "01_common_covariate_models_by_imputation.csv", index=False)
    return out


def old_supplemental_rows() -> pd.DataFrame:
    d = pd.read_csv(OLD_ALL_MODELS)
    rows = []
    for family, mid, term in [
        ("poverty_baseline", "F05_poverty_modifier_2009_2020", "pm25_iqr:poverty_baseline_std"),
        ("time_varying_SES", "O06_timevarying_SES_2010_2020", "pm25_iqr:ses_timevarying_std"),
    ]:
        r = d[(d.model_id.eq(mid)) & (d.term.eq(term))].iloc[0]
        rows.append({"analysis_block": "alternative_effect_modifier", "model_id": family,
                     "model_family": family, "imputation_scenario": "fixed_EB_B0_0_9",
                     "beta": r.estimate, "SE": r.standard_error,
                     "interaction_percent": 100 * math.expm1(r.estimate),
                     "CI_percent_lower": 100 * math.expm1(r.ci_low),
                     "CI_percent_upper": 100 * math.expm1(r.ci_high),
                     "P_value": r.p_value, "n_imputations": r.m_used,
                     "n_county_years": r.n_observations, "n_counties": r.n_counties,
                     "n_states": r.n_states, "sample_hash": "existing_model_specific_sample",
                     "formula": r.rhs, "interaction_term": term, "LST_added": False,
                     "QA_rule": "not_applicable", "day_or_night": "not_applicable",
                     "status": "reused_validated"})
    return pd.DataFrame(rows)


def run_supplemental(data: pd.DataFrame, scenarios: dict) -> pd.DataFrame:
    rows = old_supplemental_rows().to_dict("records")
    definitions = {
        "poverty_baseline": ("pm25_iqr:poverty_baseline_std", 2009, 2020),
        "time_varying_SES": ("pm25_iqr:ses_timevarying_std", 2010, 2020),
    }
    for family, (term, ymin, ymax) in definitions.items():
        sub = filter_spec_data(data, spec(family, FORMULA[family], REQ[family],
                                          term=term, year_min=ymin, year_max=ymax))
        for scenario_name in ["fixed_EB_B1_1_9", "hierarchical_EB_B0_0_9", "hierarchical_EB_B1_1_9"]:
            job = f"{family}__{scenario_name}"
            rows.append(fit_job(job, sub, FORMULA[family], REQ[family], term,
                                scenario_name, scenarios[scenario_name],
                                "alternative_effect_modifier"))
    out = pd.DataFrame(rows)
    out.to_csv(TABLES / "02_alternative_effect_modifier_models.csv", index=False)
    return out


def old_lst_rows() -> pd.DataFrame:
    d = pd.read_csv(OLD_LST_RESULTS)
    d = d[d.analysis_step.isin(["LST_eligible_sample_no_LST", "same_eligible_sample_with_LST"])].copy()
    return pd.DataFrame({
        "analysis_block": "LST_paired", "model_id": d.model_id,
        "model_family": d.model_family, "imputation_scenario": "fixed_EB_B0_0_9",
        "beta": d.beta, "SE": d.SE, "interaction_percent": d.interaction_percent,
        "CI_percent_lower": d.CI_lower, "CI_percent_upper": d.CI_upper,
        "n_imputations": 30, "n_county_years": d.n_county_years,
        "n_counties": d.n_counties, "n_states": d.n_states,
        "sample_hash": d.sample_id, "LST_added": d.LST_added,
        "QA_rule": d.QA_rule, "day_or_night": d.day_or_night,
        "status": "reused_validated", "LST_definition": d.LST_definition,
    })


def run_lst(data: pd.DataFrame, scenarios: dict) -> pd.DataFrame:
    panel = pd.read_csv(LST_PANEL)
    rows = old_lst_rows().to_dict("records")
    expected = old_lst_rows()
    for qa, period in [("strict", "day"), ("relaxed", "day"),
                       ("strict", "night"), ("relaxed", "night")]:
        x = panel[(panel.QA_rule.eq(qa)) & (panel.period.eq(period)) & panel.eligible_s070].copy()
        x["county_fips"] = x.FIPS.astype(int)
        lstvar = f"{period}_LST_per10"
        x[lstvar] = x.LST_C / 10
        for family in ["M2", "M3"]:
            base = filter_spec_data(data, spec(f"base_{family}", FORMULA[family], REQ[family]))
            sub = base.merge(x[["county_fips", "year", lstvar, "coverage"]],
                             on=["county_fips", "year"], how="inner", validate="one_to_one")
            exp = expected[(expected.QA_rule.eq(qa)) &
                           (expected.day_or_night.eq(period)) &
                           (expected.model_family.eq(family)) &
                           (~expected.LST_added.astype(bool))].iloc[0]
            if len(sub) != int(exp.n_county_years) or key_hash(sub) != str(exp.sample_hash):
                raise RuntimeError(f"{qa}/{period}/{family}: LST sample differs from validated v3 keys")
            for scenario_name in ["fixed_EB_B1_1_9", "hierarchical_EB_B0_0_9", "hierarchical_EB_B1_1_9"]:
                sc = scenarios[scenario_name]
                for added in [False, True]:
                    formula = FORMULA[family] + (f" + {lstvar}" if added else "")
                    required = REQ[family] + ((lstvar,) if added else ())
                    job = f"{family}__{qa}_{period}__{'withLST' if added else 'noLST'}__{scenario_name}"
                    r = fit_job(job, sub, formula, required, TERM, scenario_name, sc,
                                "LST_paired", added, qa, period)
                    r["LST_definition"] = f"MOD11A2.061 May-Oct {period} LST per 10C; {qa} QA"
                    rows.append(r)
    out = pd.DataFrame(rows)
    out.to_csv(TABLES / "03_LST_paired_models_by_imputation.csv", index=False)
    return out


def plots(common: pd.DataFrame, lst: pd.DataFrame) -> None:
    colors = {"fixed_EB_B0_0_9": "#1f77b4", "fixed_EB_B1_1_9": "#4fa3d1",
              "hierarchical_EB_B0_0_9": "#d95f02", "hierarchical_EB_B1_1_9": "#f4a259"}
    display = {"fixed_EB_B0_0_9": "Fixed EB, 0–9",
               "fixed_EB_B1_1_9": "Fixed EB, 1–9",
               "hierarchical_EB_B0_0_9": "Hierarchical EB, 0–9",
               "hierarchical_EB_B1_1_9": "Hierarchical EB, 1–9"}
    families = ["M0", "M1", "M2", "M2P", "M3"]
    scenarios = list(colors)
    fig, ax = plt.subplots(figsize=(10.2, 5.2))
    for si, s in enumerate(scenarios):
        d = common[common.imputation_scenario.eq(s)].set_index("model_family").loc[families]
        y = np.arange(len(families)) + (si - 1.5) * .15
        ax.errorbar(d.interaction_percent, y,
                    xerr=[d.interaction_percent - d.CI_percent_lower,
                          d.CI_percent_upper - d.interaction_percent],
                    fmt="o", ms=4, capsize=2, color=colors[s], label=display[s])
    ax.axvline(0, color="0.45", lw=.8)
    ax.set_yticks(range(len(families)), families)
    ax.invert_yaxis(); ax.set_xlabel("Smoke × SES interaction (%)")
    ax.set_title("Experiment 3: common-sample covariate models by imputation scenario")
    ax.legend(fontsize=8, frameon=False, loc="center left", bbox_to_anchor=(1.01, .5))
    fig.tight_layout()
    fig.savefig(FIGURES / "common_covariate_models_by_imputation.png", dpi=220)
    plt.close(fig)

    pairs = []
    for keys, g in lst.groupby(["imputation_scenario", "QA_rule", "day_or_night", "model_family"]):
        if set(g.LST_added.astype(bool)) != {False, True}:
            continue
        a = g.loc[~g.LST_added.astype(bool)].iloc[0]
        b = g.loc[g.LST_added.astype(bool)].iloc[0]
        pairs.append({"imputation_scenario": keys[0], "branch": f"{keys[1]} {keys[2]} {keys[3]}",
                      "delta_percent": b.interaction_percent - a.interaction_percent})
    p = pd.DataFrame(pairs)
    fig, ax = plt.subplots(figsize=(9, 5.8))
    branches = sorted(p.branch.unique())
    for si, s in enumerate(scenarios):
        d = p[p.imputation_scenario.eq(s)].set_index("branch").loc[branches]
        ax.scatter(d.delta_percent, np.arange(len(branches)) + (si - 1.5) * .14,
                   s=22, color=colors[s], label=display[s])
    ax.axvline(0, color="0.45", lw=.8)
    ax.set_yticks(range(len(branches)), branches); ax.invert_yaxis()
    ax.set_xlabel("Within-identical-sample change after adding LST (percentage points)")
    ax.set_title("LST paired adjustment under four county-death imputations")
    ax.legend(fontsize=7, frameon=False); fig.tight_layout()
    fig.savefig(FIGURES / "LST_paired_change_by_imputation.png", dpi=220)
    plt.close(fig)
    p.to_csv(TABLES / "04_LST_paired_changes.csv", index=False)


def report(common: pd.DataFrame, supplemental: pd.DataFrame, lst: pd.DataFrame) -> None:
    spread = common.groupby("model_family").agg(
        min_percent=("interaction_percent", "min"), max_percent=("interaction_percent", "max"),
        min_SE=("SE", "min"), max_SE=("SE", "max")).reset_index()
    spread["percent_range"] = spread.max_percent - spread.min_percent
    spread.to_csv(TABLES / "05_common_model_imputation_spread.csv", index=False)
    pair = pd.read_csv(TABLES / "04_LST_paired_changes.csv")
    alt_spread = supplemental.groupby("model_family").agg(
        min_percent=("interaction_percent", "min"),
        max_percent=("interaction_percent", "max"),
        min_n=("n_county_years", "min"),
        max_n=("n_county_years", "max"),
    ).reset_index()

    scenarios = sorted(common.imputation_scenario.unique())
    pair_errors = 0
    for _, g in lst.groupby(["imputation_scenario", "QA_rule", "day_or_night", "model_family"]):
        if set(g.LST_added.astype(bool)) != {False, True}:
            pair_errors += 1
            continue
        a = g.loc[~g.LST_added.astype(bool)].iloc[0]
        b = g.loc[g.LST_added.astype(bool)].iloc[0]
        if (int(a.n_county_years) != int(b.n_county_years)
                or str(a.sample_hash) != str(b.sample_hash)):
            pair_errors += 1
    new_rows = pd.concat([
        common[common.imputation_scenario.ne("fixed_EB_B0_0_9")],
        supplemental[supplemental.imputation_scenario.ne("fixed_EB_B0_0_9")],
        lst[lst.imputation_scenario.ne("fixed_EB_B0_0_9")],
    ], ignore_index=True)
    checks = pd.DataFrame([
        {"check_id": "common_table_shape", "observed": len(common), "expected": 20,
         "passed": len(common) == 20},
        {"check_id": "common_five_models_per_scenario",
         "observed": int(common.groupby("imputation_scenario").size().min()), "expected": 5,
         "passed": len(scenarios) == 4 and common.groupby("imputation_scenario").size().eq(5).all()},
        {"check_id": "common_frozen_key_hash", "observed": common.sample_hash.nunique(), "expected": 1,
         "passed": common.sample_hash.astype(str).eq("d15d10108a6a2bac").all()},
        {"check_id": "alternative_modifier_table_shape", "observed": len(supplemental), "expected": 8,
         "passed": len(supplemental) == 8},
        {"check_id": "LST_table_shape", "observed": len(lst), "expected": 64,
         "passed": len(lst) == 64},
        {"check_id": "LST_noLST_withLST_key_pairs", "observed": pair_errors, "expected": 0,
         "passed": pair_errors == 0},
        {"check_id": "new_model_convergence_30_of_30",
         "observed": int(new_rows.convergence.astype(str).eq("30/30").sum()),
         "expected": len(new_rows),
         "passed": new_rows.convergence.astype(str).eq("30/30").all()},
        {"check_id": "smoking_terms_in_model_formulas",
         "observed": int(pd.concat([common, supplemental, lst]).formula.fillna("").str.contains(
             "smok", case=False, regex=False).sum()), "expected": 0,
         "passed": not pd.concat([common, supplemental, lst]).formula.fillna("").str.contains(
             "smok", case=False, regex=False).any()},
    ])
    checks.to_csv(TABLES / "06_validation_checks.csv", index=False)
    if not checks.passed.all():
        failed = checks.loc[~checks.passed, "check_id"].tolist()
        raise RuntimeError(f"experiment-3 validation checks failed: {failed}")
    lines = [
        "# 研究内容三：县级死亡插补更新后的实验刷新",
        "",
        "## 执行结论",
        "",
        "研究内容三已按四套县级死亡插补刷新。固定历史EB 0–9仍是经伪压制验证支持的主方案；"
        "其他三套是结构化敏感性，不按P值选优。吸烟率未纳入。LST与空气温度、干旱、降水和背景污染一样作为普通协变量。",
        "",
        "## 共同样本协变量链",
        "",
    ]
    for _, r in spread.iterrows():
        lines.append(f"- {r.model_family}: 四插补方案估计范围 {r.min_percent:.4f}%–{r.max_percent:.4f}%；范围宽度 {r.percent_range:.4f}个百分点。")
    lines += ["", "## 替代效应修饰指标", ""]
    for _, r in alt_spread.iterrows():
        lines.append(
            f"- {r.model_family}: 四插补方案估计范围 {r.min_percent:.4f}%–{r.max_percent:.4f}%；"
            f"county-year样本量 {int(r.min_n)}–{int(r.max_n)}。"
        )
    lines += ["", "## LST同键配对", ""]
    for branch, g in pair.groupby("branch"):
        lines.append(f"- {branch}: 加入LST后的变化范围 {g.delta_percent.min():+.4f}至{g.delta_percent.max():+.4f}个百分点。")
    lines += [
        "", "## 解释边界", "",
        "- 固定EB与层级EB是不同的县级死亡分配模型；它们不是四套独立观测数据。",
        "- 共同样本模型只在3,062个固定county-year键内比较；LST模型只在各QA分支的具体同键样本内比较。",
        "- 插补方案间结果接近只支持实验三对这些合理县级分配假设的稳定性，不证明suppression插补无偏。",
        "- 贫困率和时变SES是替代效应修饰，不与baseline SES同时作为普通协变量解释。",
        "- 不把LST调整后的变化解释为热环境机制贡献。",
    ]
    (REPORTS / "experiment3_refresh_decision_CN.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=CONFIG_DEFAULT)
    ap.add_argument("--stage", choices=["all", "common", "lst", "report", "status"], default="all")
    args = ap.parse_args(); ensure_dirs()
    config = json.loads(args.config.read_text())
    if args.stage == "status":
        done = len(list(CHECKPOINTS.glob("*.json")))
        print(json.dumps({"checkpoint_files": done, "output_tables": [p.name for p in TABLES.glob("*.csv")]}, indent=2))
        return
    started = time.time()
    data, old_b0 = prepare_data(); scenarios = load_scenarios(config, old_b0)
    imputation_change_summary(data, scenarios)
    common_file = TABLES / "01_common_covariate_models_by_imputation.csv"
    supplemental_file = TABLES / "02_alternative_effect_modifier_models.csv"
    lst_file = TABLES / "03_LST_paired_models_by_imputation.csv"
    if args.stage in ("all", "common") or not common_file.exists():
        common = run_common(data, scenarios)
        supplemental = run_supplemental(data, scenarios)
    else:
        common = pd.read_csv(common_file); supplemental = pd.read_csv(supplemental_file)
    if args.stage == "common":
        return
    if args.stage in ("all", "lst") or not lst_file.exists():
        lst = run_lst(data, scenarios)
    else:
        lst = pd.read_csv(lst_file)
    plots(common, lst); report(common, supplemental, lst)
    checkpoint_seconds = 0.0
    for p in CHECKPOINTS.glob("*.json"):
        cp = json.loads(p.read_text(encoding="utf-8"))
        checkpoint_seconds += float(cp.get("elapsed_seconds", 0.0))
    manifest = {
        "version": config["version"], "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_seconds_current_invocation": time.time() - started,
        "recorded_model_fit_seconds_from_checkpoints": checkpoint_seconds,
        "runtime_note": "Current invocation may be a report-only refresh; model-fit time is summed from validated checkpoints.",
        "inputs": {str(p.relative_to(ROOT)): sha256(p) for p in
                   [Path(__file__).resolve(), CONFIG_DEFAULT, STAGE2_COMMON, PRECIP_RESULT, OLD_LST_RESULTS,
                    LST_PANEL, FIXED_B1, HIER_B0, HIER_B1]},
        "outputs": [str(p.relative_to(ROOT)) for p in sorted(TABLES.glob("*.csv"))]
                   + [str(p.relative_to(ROOT)) for p in sorted(FIGURES.glob("*.png"))],
        "smoking_excluded": True, "paper_modified": False,
        "status": "completed_and_validated",
    }
    (HERE / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": manifest["status"],
                      "elapsed_seconds_current_invocation": manifest["elapsed_seconds_current_invocation"],
                      "recorded_model_fit_seconds": manifest["recorded_model_fit_seconds_from_checkpoints"]}, indent=2))


if __name__ == "__main__":
    main()
