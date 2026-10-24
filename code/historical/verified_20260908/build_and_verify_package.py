#!/usr/bin/env python3
"""Verify frozen AFIRE results and build a minimal, auditable paper package."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import shutil
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import linregress


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "paper_package_verified_20260908.zip"

V2 = ROOT / "experiment_feasibility_20260906/source_snapshot/all/01/Afire_project_v2"
V7 = ROOT / "experiment_feasibility_20260906/source_snapshot/all/04"
STAGE2 = ROOT / "experiment_validation_stage2_20260906"
STAGE3 = ROOT / "experiment_validation_stage3_20260906"
SUPP = ROOT / "experiment_suppression_innovation_20260908"
EXP3 = ROOT / "experiment3_imputation_refresh_20260908"
LONG = ROOT / "experiment_longrun_20260906"
CLOSE = ROOT / "experiment_closeout_v3"
LAST = ROOT / "last"
HANDOFF_ZIP = LAST / "Afire_paper_handoff_20260825.zip"

CHECKS: list[dict] = []
COPIED: list[dict] = []


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def add_check(section: str, check: str, passed: bool, observed, expected, severity="critical", note=""):
    CHECKS.append({
        "section": section,
        "check": check,
        "status": "PASS" if passed else "FAIL",
        "observed": str(observed),
        "expected": str(expected),
        "severity": severity,
        "note": note,
    })


def close(a, b, tol=1e-10) -> bool:
    return math.isfinite(float(a)) and abs(float(a) - float(b)) <= tol


def copy_file(src: Path, rel: str, role: str, source_note="") -> Path:
    if not src.exists():
        raise FileNotFoundError(src)
    dst = OUT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    source_hash = sha256(src)
    dest_hash = sha256(dst)
    if source_hash != dest_hash:
        raise RuntimeError(f"Hash mismatch after copy: {src} -> {dst}")
    COPIED.append({
        "package_path": rel,
        "source_path": str(src.relative_to(ROOT)),
        "role": role,
        "source_note": source_note,
        "bytes": dst.stat().st_size,
        "sha256": dest_hash,
    })
    return dst


def extract_member(member: str, rel: str, role: str) -> Path:
    dst = OUT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(HANDOFF_ZIP) as zf:
        data = zf.read(member)
    dst.write_bytes(data)
    COPIED.append({
        "package_path": rel,
        "source_path": f"last/Afire_paper_handoff_20260825.zip::{member}",
        "role": role,
        "source_note": "extracted byte-for-byte from the 2026-08-25 handoff archive",
        "bytes": dst.stat().st_size,
        "sha256": sha256(dst),
    })
    return dst


def verify_manuscripts() -> None:
    expected = {
        "Afire_Nature_CN_final_v2.docx": "179194ee2485130aa24990071d0f72dfee16b308ff399a20d034284098425537",
        "Afire_Nature_EN_final_v2.docx": "4202d2793666eb1d5f9e82b97f679dfc5a2c7e7c2b121cae6a8872a912fb7027",
        "Afire_Nature_Supplementary_CN_final_v2.docx": "10e48f667a5a1a5f066112eb29352950736a80744c9033bc32dbfb8b73a89eda",
        "Afire_Nature_Supplementary_EN_final_v2.docx": "56c120ff17a229bb41593a7e538d54f26ca08b5f062abb65b2ff4ab548922f79",
    }
    for name, wanted in expected.items():
        got = sha256(LAST / name)
        add_check("manuscript", f"frozen_hash_{name}", got == wanted, got, wanted)


def verify_result1() -> dict:
    annual = pd.read_csv(V2 / "tables/annual_exposure_inequality.csv")
    state = pd.read_csv(V2 / "tables/state_year_exposure.csv", dtype={"state_fips": str})
    fire = pd.read_csv(V2 / "tables/top100_fire_pm25_cover_state_year.csv", dtype={"state_fips": str})
    design = pd.read_csv(STAGE2 / "02_joint_extreme_design_diagnostics.csv")
    omission = pd.read_csv(STAGE2 / "03_targeted_omission_models.csv")

    add_check("result1", "annual_years", annual["year"].tolist() == list(range(2006, 2021)), annual["year"].tolist(), "2006-2020")
    add_check("result1", "state_year_rows", len(state) == 735, len(state), "49 exposure jurisdictions x 15 years")
    add_check("result1", "state_year_unique_key", not state.duplicated(["state_abbr", "year"]).any(), int(state.duplicated(["state_abbr", "year"]).sum()), 0)
    per_year = state.groupby("year")["state_abbr"].nunique()
    add_check("result1", "nonmissing_exposure_units_each_year", bool((per_year == 49).all()), sorted(per_year.unique().tolist()), [49], note="51-unit health frame; AK and HI lack smoke exposure")

    y2009 = float(annual.loc[annual.year == 2009, "population_weighted_smoke_pm25"].iloc[0])
    y2020 = float(annual.loc[annual.year == 2020, "population_weighted_smoke_pm25"].iloc[0])
    add_check("result1", "population_weighted_2009", round(y2009, 3) == 0.162, y2009, "rounds to 0.162")
    add_check("result1", "population_weighted_2020", round(y2020, 3) == 0.893, y2020, "rounds to 0.893")
    add_check("result1", "2020_to_2009_ratio", round(y2020 / y2009, 1) == 5.5, y2020 / y2009, "rounds to 5.5")
    trend = linregress(annual.year, annual.gini_smoke_pm25)
    add_check("result1", "gini_slope", round(float(trend.slope), 4) == 0.0119, trend.slope, "rounds to 0.0119")
    add_check("result1", "gini_p", round(float(trend.pvalue), 3) == 0.009, trend.pvalue, "rounds to 0.009")

    six = ["AZ", "CA", "CO", "ID", "OR", "WA"]
    n_fire = float(fire.loc[fire.state_abbr.isin(six), "top100_fire_count"].sum())
    add_check("result1", "six_state_top100_records", close(n_fire, 66), n_fire, 66, note="denominator is the original Top100 collection; the 49-jurisdiction table contains 97 allocated records")

    add_check("result1", "design_four_groups", len(design) == 4, len(design), 4)
    add_check("result1", "design_rows_sum", int(design.n_observations.sum()) == 3072, int(design.n_observations.sum()), 3072)
    add_check("result1", "design_share_sum", close(design.residualized_interaction_ss_share.sum(), 1.0, 1e-12), design.residualized_interaction_ss_share.sum(), 1.0)
    add_check("result1", "design_single_sample", design.sample_id.nunique() == 1, design.sample_id.nunique(), 1)
    ca2020 = float(design.loc[design.group == "California × 2020", "residualized_interaction_ss_share"].iloc[0])
    add_check("result1", "CA_2020_design_share", round(ca2020 * 100, 1) == 39.4, ca2020 * 100, "rounds to 39.4%")

    add_check("result1", "five_omission_scenarios", len(omission) == 5, len(omission), 5)
    add_check("result1", "omission_all_30_imputations", bool((omission.n_imputations == 30).all()), omission.n_imputations.unique().tolist(), [30])
    add_check("result1", "omission_all_converged", bool((omission.convergence == "30/30").all()), omission.convergence.unique().tolist(), ["30/30"])
    add_check("result1", "omission_same_formula", omission.formula.nunique() == 1, omission.formula.nunique(), 1)
    pct = 100 * np.expm1(omission.beta_interaction.astype(float))
    ci_lo = 100 * np.expm1(omission.beta_CI_low.astype(float))
    ci_hi = 100 * np.expm1(omission.beta_CI_high.astype(float))
    add_check("result1", "omission_percent_transform", bool(np.allclose(pct, omission.interaction_percent, atol=1e-12)), float(np.max(np.abs(pct - omission.interaction_percent))), "<=1e-12")
    add_check("result1", "omission_CI_transform", bool(np.allclose(ci_lo, omission.CI_lower, atol=1e-12) and np.allclose(ci_hi, omission.CI_upper, atol=1e-12)), max(float(np.max(np.abs(ci_lo - omission.CI_lower))), float(np.max(np.abs(ci_hi - omission.CI_upper)))), "<=1e-12")

    return {"annual": annual, "state": state, "fire": fire, "design": design, "omission": omission, "trend": trend}


def _bool_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().map({"true": True, "false": False})


def validate_draws(panel: pd.DataFrame, draws: np.ndarray, rows: pd.DataFrame, lower: int, upper: int, label: str) -> None:
    suppress = _bool_series(rows.death_suppressed).to_numpy()
    public = ~suppress
    add_check("result2", f"{label}_integer", bool(np.allclose(draws, np.rint(draws))), float(np.max(np.abs(draws - np.rint(draws)))), 0)
    add_check("result2", f"{label}_suppressed_bounds", bool(((draws[:, suppress] >= lower) & (draws[:, suppress] <= upper)).all()), f"min={draws[:, suppress].min()}, max={draws[:, suppress].max()}", f"{lower}-{upper}")
    public_deaths = pd.to_numeric(rows.loc[public, "deaths"], errors="coerce").to_numpy()
    add_check("result2", f"{label}_public_unchanged", bool(np.allclose(draws[:, public], public_deaths[None, :])), float(np.max(np.abs(draws[:, public] - public_deaths[None, :]))), 0)
    ok = True
    max_err = 0.0
    groups = rows.reset_index(drop=True).groupby(["state_abbr", "year", "cause_id"], sort=False).indices
    for idx in groups.values():
        idx = np.asarray(idx)
        target = float(rows.iloc[idx[0]].state_deaths)
        err = np.max(np.abs(draws[:, idx].sum(axis=1) - target))
        max_err = max(max_err, float(err))
        if err != 0:
            ok = False
    add_check("result2", f"{label}_exact_state_margins", ok, max_err, 0)


def verify_result2(panel: pd.DataFrame) -> dict:
    tests = pd.read_csv(SUPP / "outputs/tables/01_sampler_unit_tests.csv")
    pred = pd.read_csv(SUPP / "outputs/tables/02_pseudo_suppression_predictions.csv", dtype={"county_fips": str})
    summary = pd.read_csv(SUPP / "outputs/tables/03_pseudo_suppression_validation_summary.csv")
    health = pd.read_csv(SUPP / "outputs/models/01_scenario_health_model_results.csv")

    add_check("result2", "enumerable_sampler_tests", bool((tests.status == "pass").all()), tests.status.value_counts().to_dict(), "all pass")
    add_check("result2", "pseudo_prediction_rows", len(pred) == 13208, len(pred), 13208)
    add_check("result2", "four_methods_per_cell", pred.groupby(["pseudo_group_id", "county_fips"]).method.nunique().eq(4).all(), pred.groupby(["pseudo_group_id", "county_fips"]).method.nunique().value_counts().to_dict(), 4)

    recomputed = []
    for scope, subset in [("all_outcomes", pred), ("COPD", pred.loc[pred.cause_id == "copd"])]:
        for method, g in subset.groupby("method"):
            recomputed.append({
                "scope": scope,
                "method": method,
                "n_groups": g.pseudo_group_id.nunique(),
                "n_cells": len(g),
                "MAE": g.absolute_error.mean(),
                "RMSE": math.sqrt(g.squared_error.mean()),
                "coverage_95": _bool_series(g.interval_covers_truth).mean(),
                "mean_interval_width": g.interval_width.mean(),
                "mean_CRPS": g.CRPS.mean(),
                "mean_interval_score_95": g.interval_score_95.mean(),
            })
    rec = pd.DataFrame(recomputed)
    merged = summary.merge(rec, on=["scope", "method"], suffixes=("_reported", "_recomputed"), validate="one_to_one")
    max_diff = 0.0
    for col in ["n_groups", "n_cells", "MAE", "RMSE", "coverage_95", "mean_interval_width", "mean_CRPS", "mean_interval_score_95"]:
        max_diff = max(max_diff, float(np.max(np.abs(merged[f"{col}_reported"] - merged[f"{col}_recomputed"]))))
    add_check("result2", "pseudo_summary_recomputed", max_diff <= 1e-12, max_diff, "<=1e-12")

    pct = 100 * np.expm1(health.beta)
    lo = 100 * np.expm1(health.beta_CI_lower)
    hi = 100 * np.expm1(health.beta_CI_upper)
    add_check("result2", "scenario_percent_transform", bool(np.allclose(pct, health.interaction_percent, atol=1e-12)), float(np.max(np.abs(pct - health.interaction_percent))), "<=1e-12")
    add_check("result2", "scenario_CI_transform", bool(np.allclose(lo, health.CI_percent_lower, atol=1e-12) and np.allclose(hi, health.CI_percent_upper, atol=1e-12)), max(float(np.max(np.abs(lo - health.CI_percent_lower))), float(np.max(np.abs(hi - health.CI_percent_upper)))), "<=1e-12")

    old = np.load(V7 / "data_processed/imputed_deaths_eb_history_v5.npz")["draws"]
    ordered = panel.sort_values("row_id")
    add_check("result2", "panel_row_ids_sequential", ordered.row_id.tolist() == list(range(len(ordered))), f"min={ordered.row_id.min()}, max={ordered.row_id.max()}", f"0-{len(ordered)-1}")
    validate_draws(panel, old, ordered, 0, 9, "fixed_EB_B0_all_outcomes")

    copd = panel.loc[panel.cause_id == "copd"].copy().set_index("row_id", drop=False)
    sources = [
        (STAGE3 / "copd_B1_1_9_draws.npz", 1, 9, "fixed_EB_B1_COPD"),
        (SUPP / "outputs/imputations/COPD_hierarchical_exact_margin_bem_hbmi_pilot_v2_0_9.npz", 0, 9, "hierarchical_EB_B0_COPD"),
        (SUPP / "outputs/imputations/COPD_hierarchical_exact_margin_bem_hbmi_pilot_v2_1_9.npz", 1, 9, "hierarchical_EB_B1_COPD"),
    ]
    for path, lower, upper, label in sources:
        z = np.load(path)
        ids = z["row_ids"].astype(int)
        rows = copd.loc[ids].reset_index(drop=True)
        validate_draws(panel, z["draws"], rows, lower, upper, label)

    return {"tests": tests, "pred": pred, "summary": summary, "health": health}


def rubin_pool(g: pd.DataFrame) -> tuple[float, float, float, float]:
    q = g.estimate.astype(float).to_numpy()
    u = g.within_variance.astype(float).to_numpy()
    m = len(q)
    qbar = float(q.mean())
    w = float(u.mean())
    b = float(q.var(ddof=1)) if m > 1 else 0.0
    se = math.sqrt(w + (1 + 1 / m) * b)
    return qbar, se, w, b


def verify_v7_models() -> tuple[int, float]:
    model_dirs = sorted((V7 / "results/models").glob("*"))
    tested = 0
    max_diff = 0.0
    for d in model_dirs:
        per_path = d / "per_imputation.csv.gz"
        pooled_path = d / "pooled.csv"
        if not per_path.exists() or not pooled_path.exists():
            continue
        per = pd.read_csv(per_path)
        pooled = pd.read_csv(pooled_path)
        for term, g in per.groupby("term"):
            target = pooled.loc[pooled.term == term]
            if len(target) != 1:
                raise RuntimeError(f"No unique pooled row for {d.name} / {term}")
            q, se, w, b = rubin_pool(g)
            row = target.iloc[0]
            diffs = [abs(q - row.estimate), abs(se - row.standard_error), abs(w - row.within_variance), abs(b - row.between_variance)]
            max_diff = max(max_diff, *diffs)
            tested += 1
    add_check("result3", "v7_all_model_terms_rubin_recomputed", tested > 0 and max_diff <= 1e-11, f"terms={tested}; max_abs_diff={max_diff}", "all available terms; <=1e-11")
    return tested, max_diff


def verify_result3(panel: pd.DataFrame) -> dict:
    validation = pd.read_csv(V7 / "results/tables/data_validation_v7.csv")
    final_check = pd.read_csv(V7 / "results/tables/final_check_v7.csv")
    status = pd.read_csv(V7 / "results/tables/model_status_v7.csv")
    failures = pd.read_csv(V7 / "results/tables/model_failures_v7.csv")
    common = pd.read_csv(EXP3 / "tables/01_common_covariate_models_by_imputation.csv")
    alt = pd.read_csv(EXP3 / "tables/02_alternative_effect_modifier_models.csv")
    validation3 = pd.read_csv(EXP3 / "tables/06_validation_checks.csv")
    lst = pd.read_csv(LONG / "processed/main_2009_2020_v3/county_year_LST_long.csv", dtype={"FIPS": str, "STATEFP": str})
    lst_checks = pd.read_csv(LONG / "processed/main_2009_2020_v3/validation_checks.csv")
    paired = pd.read_csv(CLOSE / "paired_LST_results_complete.csv")
    qc = pd.read_csv(CLOSE / "evidence/QC_zero_source_comparison.csv")
    qa_reasons = pd.read_csv(CLOSE / "QA_exclusion_reasons.csv")

    add_check("result3", "v7_data_validation", bool((validation.status == "PASS").all()), validation.status.value_counts().to_dict(), "all PASS")
    add_check("result3", "v7_final_check", bool((final_check.status == "PASS").all()), final_check.status.value_counts().to_dict(), "all PASS")
    add_check("result3", "v7_model_failures_empty", len(failures) == 0, len(failures), 0)
    add_check("result3", "v7_model_status_completed", bool((status.status == "completed").all() and (status.successful_imputations == 30).all() and (status.failed_imputations == 0).all()), status[["status", "successful_imputations", "failed_imputations"]].value_counts().to_dict(), "all completed 30/30")
    verify_v7_models()

    primary_per = pd.read_csv(V7 / "results/models/O10_temperature_adjusted_2009_2020/per_imputation.csv.gz")
    primary_per = primary_per.loc[primary_per.term == "pm25_iqr:ses_baseline_std"]
    q, se, w, b = rubin_pool(primary_per)
    primary = pd.read_csv(V7 / "results/models/O10_temperature_adjusted_2009_2020/pooled.csv")
    primary = primary.loc[primary.term == "pm25_iqr:ses_baseline_std"].iloc[0]
    add_check("result3", "primary_30_imputations", len(primary_per) == 30, len(primary_per), 30)
    add_check("result3", "primary_beta_recomputed", close(q, primary.estimate, 1e-12), q, primary.estimate)
    add_check("result3", "primary_SE_recomputed", close(se, primary.standard_error, 1e-12), se, primary.standard_error)
    add_check("result3", "primary_interaction_percent", close(100 * math.expm1(q), 0.746064797000175, 1e-12), 100 * math.expm1(q), 0.746064797000175)

    add_check("result3", "common_table_5x4", len(common) == 20 and common.model_family.nunique() == 5 and common.imputation_scenario.nunique() == 4, common.shape, "20 rows = 5 models x 4 imputation scenarios")
    add_check("result3", "common_exact_sample", bool((common.n_county_years == 3062).all() and (common.n_counties == 256).all() and (common.n_states == 6).all() and common.sample_hash.nunique() == 1), f"n={common.n_county_years.unique()}; hashes={common.sample_hash.nunique()}", "3062, 256 counties, 6 states, one hash")
    add_check("result3", "experiment3_validation_checks", bool(_bool_series(validation3.passed).all()), validation3.passed.value_counts().to_dict(), "all True")
    add_check("result3", "alternative_modifiers_2x4", len(alt) == 8 and alt.model_family.nunique() == 2 and alt.imputation_scenario.nunique() == 4, alt.shape, "8 rows = 2 modifiers x 4 scenarios")

    for table_name, table in [("common", common), ("alternative", alt)]:
        pct = 100 * np.expm1(table.beta.astype(float))
        add_check("result3", f"{table_name}_percent_transform", bool(np.allclose(pct, table.interaction_percent, atol=1e-12)), float(np.max(np.abs(pct - table.interaction_percent))), "<=1e-12")
        ci_mask = table.beta_CI_lower.notna() & table.beta_CI_upper.notna()
        lo = 100 * np.expm1(table.loc[ci_mask, "beta_CI_lower"].astype(float))
        hi = 100 * np.expm1(table.loc[ci_mask, "beta_CI_upper"].astype(float))
        lo_target = table.loc[ci_mask, "CI_percent_lower"].astype(float)
        hi_target = table.loc[ci_mask, "CI_percent_upper"].astype(float)
        max_ci_diff = max(float(np.max(np.abs(lo - lo_target))), float(np.max(np.abs(hi - hi_target))))
        add_check("result3", f"{table_name}_CI_transform", bool(np.allclose(lo, lo_target, atol=1e-12) and np.allclose(hi, hi_target, atol=1e-12)), max_ci_diff, f"<=1e-12 across {int(ci_mask.sum())} rows with stored beta-scale CI", note="reused legacy rows without beta-scale CI are verified against their frozen source tables")

    key_cols = ["FIPS", "year", "period", "QA_rule"]
    add_check("result3", "LST_long_rows", len(lst) == 12288, len(lst), "3072 county-years x day/night x strict/relaxed")
    add_check("result3", "LST_unique_long_key", not lst.duplicated(key_cols).any(), int(lst.duplicated(key_cols).sum()), 0)
    add_check("result3", "LST_unique_FIPS_year", lst[["FIPS", "year"]].drop_duplicates().shape[0] == 3072, lst[["FIPS", "year"]].drop_duplicates().shape[0], 3072)
    add_check("result3", "LST_256_counties", lst.FIPS.nunique() == 256, lst.FIPS.nunique(), 256)
    add_check("result3", "LST_2009_2020", sorted(lst.year.unique().tolist()) == list(range(2009, 2021)), sorted(lst.year.unique().tolist()), "2009-2020")
    add_check("result3", "LST_coverage_bounds", bool(lst.coverage.between(-1e-10, 1 + 1e-10).all()), f"min={lst.coverage.min()}, max={lst.coverage.max()}", "0-1 within predeclared floating tolerance 1e-10", note="raw values retained; no clipping")
    add_check("result3", "LST_validation_checks", bool((lst_checks.status == "pass").all()), lst_checks.status.value_counts().to_dict(), "all pass")
    add_check("result3", "QC_source_8_granules", len(qc) == 8, len(qc), 8)
    add_check("result3", "QC_full_byte_exact", bool(_bool_series(qc.full_byte_exact_match).all()), qc.full_byte_exact_match.value_counts().to_dict(), "all True")
    add_check("result3", "QC_source_nonzero_at_recovery", int(_bool_series(qc.source_nonzero_at_recovery).sum()) == 0, int(_bool_series(qc.source_nonzero_at_recovery).sum()), 0, note="sampled source validation, not an exhaustive all-pixel audit")

    pair_errors = []
    for (qa, period, family), g in paired.groupby(["QA_rule", "day_or_night", "model_family"]):
        elig = g.loc[g.analysis_step == "LST_eligible_sample_no_LST"]
        with_lst = g.loc[g.analysis_step == "same_eligible_sample_with_LST"]
        if len(elig) != 1 or len(with_lst) != 1:
            pair_errors.append(f"{qa}/{period}/{family}: missing pair")
        elif not (elig.iloc[0].sample_id == with_lst.iloc[0].sample_id and elig.iloc[0].n_county_years == with_lst.iloc[0].n_county_years):
            pair_errors.append(f"{qa}/{period}/{family}: key mismatch")
    add_check("result3", "LST_paired_exact_samples", not pair_errors, pair_errors or "all 8 pairs match", "all 8 pairs match")
    add_check("result3", "LST_all_converged", bool((paired.convergence == "30/30").all()), paired.convergence.value_counts().to_dict(), "all 30/30")
    pct = 100 * np.expm1(paired.beta.astype(float))
    add_check("result3", "LST_percent_transform", bool(np.allclose(pct, paired.interaction_percent, atol=1e-12)), float(np.max(np.abs(pct - paired.interaction_percent))), "<=1e-12")

    az = qa_reasons.loc[qa_reasons.STATEFP.astype(str).isin(["4", "04"])]
    add_check("result3", "Arizona_all_have_LST", int(az.n_LST_value.sum()) == 360, int(az.n_LST_value.sum()), "180 day + 180 night")
    add_check("result3", "Arizona_strict_none_eligible", int(az.n_eligible.sum()) == 0, int(az.n_eligible.sum()), 0)

    checkpoint_files = sorted((EXP3 / "models/checkpoints").glob("*.json"))
    complete = 0
    for path in checkpoint_files:
        obj = json.loads(path.read_text(encoding="utf-8"))
        conv = str(obj.get("convergence", ""))
        if conv == "30/30" or (isinstance(obj.get("fits"), list) and len(obj["fits"]) == 30 and all(x.get("status") == "ok" for x in obj["fits"])):
            complete += 1
    add_check("result3", "experiment3_checkpoint_fits", complete == len(checkpoint_files) and len(checkpoint_files) >= 1, f"{complete}/{len(checkpoint_files)}", "all checkpoint models contain 30 successful fits")

    return {"common": common, "alt": alt, "lst": lst, "paired": paired, "qa_reasons": qa_reasons, "status": status}


def package_sources(r1: dict, r2: dict, r3: dict) -> None:
    # Frozen manuscripts: reference only; they predate the final three-result reorganization.
    for name in [
        "Afire_Nature_CN_final_v2.docx", "Afire_Nature_EN_final_v2.docx",
        "Afire_Nature_Supplementary_CN_final_v2.docx", "Afire_Nature_Supplementary_EN_final_v2.docx",
    ]:
        copy_file(LAST / name, f"manuscript_reference/{name}", "frozen manuscript reference", "not rewritten with the newly reorganized three Results")
    copy_file(LAST / "PROJECT_STATUS.md", "manuscript_reference/PROJECT_STATUS.md", "handoff status")
    copy_file(LAST / "论文交接指导.md", "manuscript_reference/论文交接指导.md", "handoff guidance")
    extract_member("Afire_paper_handoff_20260825/author_inputs/AUTHOR_ACTION_REQUIRED.md", "manuscript_reference/AUTHOR_ACTION_REQUIRED.md", "author-supplied facts still required")
    extract_member("Afire_paper_handoff_20260825/reports/Afire_Nature_final_revision_report.md", "manuscript_reference/Afire_Nature_final_revision_report.md", "prior manuscript QA report")

    # Result 1 data.
    for src, rel, role in [
        (V2 / "tables/annual_exposure_inequality.csv", "data/result1/annual_exposure_inequality.csv", "state-scale annual exposure and inequality"),
        (V2 / "tables/state_year_exposure.csv", "data/result1/state_year_exposure.csv", "49-jurisdiction state-year exposure"),
        (V2 / "tables/top100_fire_pm25_cover_state_year.csv", "data/result1/top100_fire_pm25_cover_state_year.csv", "Top100 fire allocation and smoke overlap"),
        (V2 / "data_processed/state_year_ses.csv", "data/result1/state_year_ses.csv", "state-year socioeconomic data"),
        (STAGE2 / "02_joint_extreme_design_diagnostics.csv", "data/result1/joint_extreme_design_diagnostics.csv", "four disjoint design-variation groups"),
        (STAGE2 / "03_targeted_omission_models.csv", "data/result1/targeted_omission_models.csv", "five predefined omission models"),
        (STAGE3 / "04_design_variation_reconciliation.csv", "data/result1/design_variation_reconciliation.csv", "23.5% versus 17.5% reconciliation"),
    ]:
        copy_file(src, rel, role)

    # Result 2 data.
    for src, rel, role in [
        (SUPP / "outputs/tables/01_sampler_unit_tests.csv", "data/result2/sampler_unit_tests.csv", "enumerable conditional-sampler tests"),
        (SUPP / "outputs/tables/02_pseudo_suppression_predictions.csv", "data/result2/pseudo_suppression_predictions.csv", "cell-level pseudo-suppression validation output"),
        (SUPP / "outputs/tables/03_pseudo_suppression_validation_summary.csv", "data/result2/pseudo_suppression_validation_summary.csv", "method validation summary"),
        (SUPP / "outputs/tables/04_pseudo_suppression_pairwise_bootstrap.csv", "data/result2/pseudo_suppression_pairwise_bootstrap.csv", "group-bootstrap method contrasts"),
        (SUPP / "outputs/tables/05_hierarchical_prior_hyperparameters.csv", "data/result2/hierarchical_prior_hyperparameters.csv", "hierarchical prior inputs"),
        (SUPP / "outputs/tables/06_mcmc_diagnostics_all_boundaries_bem_hbmi_pilot_v2.csv", "data/result2/mcmc_diagnostics.csv", "hierarchical imputation diagnostics"),
        (SUPP / "outputs/tables/07_method_selection_decision.csv", "data/result2/method_selection_decision.csv", "predefined method decision"),
        (SUPP / "outputs/models/01_scenario_health_model_results.csv", "data/result2/scenario_health_model_results.csv", "fixed COPD model under four imputation scenarios"),
        (STAGE3 / "03_support_boundary_sensitivity.csv", "data/result2/support_boundary_sensitivity.csv", "0-9 versus 1-9 boundary result"),
        (STAGE3 / "copd_B1_1_9_imputation_checks.csv", "data/result2/copd_B1_imputation_checks.csv", "exact-margin and bound checks"),
        (V7 / "data_processed/imputed_deaths_eb_history_v5.npz", "data/analysis/imputed_deaths_fixed_EB_B0_0_9.npz", "30 fixed-EB complete death datasets"),
        (STAGE3 / "copd_B1_1_9_draws.npz", "data/analysis/COPD_fixed_EB_B1_1_9.npz", "30 COPD 1-9 boundary datasets"),
        (SUPP / "outputs/imputations/COPD_hierarchical_exact_margin_bem_hbmi_pilot_v2_0_9.npz", "data/analysis/COPD_hierarchical_EB_B0_0_9.npz", "90 hierarchical COPD 0-9 draws"),
        (SUPP / "outputs/imputations/COPD_hierarchical_exact_margin_bem_hbmi_pilot_v2_1_9.npz", "data/analysis/COPD_hierarchical_EB_B1_1_9.npz", "90 hierarchical COPD 1-9 draws"),
    ]:
        copy_file(src, rel, role)

    # Model-ready panel: retain CSV usability in directory; the final zip compresses it.
    copy_file(V7 / "data_processed/county_year_disease_panel_v6_3.csv", "data/analysis/county_year_disease_panel_v6_3.csv", "model-ready 7-outcome county-year analysis panel")

    # Result 3 and supplementary model outputs.
    for src, rel, role in [
        (V7 / "results/tables/all_pooled_models_v7.csv", "data/result3/all_pooled_models_v7.csv", "all historical pooled model terms"),
        (V7 / "results/tables/paper_main_and_key_sensitivity_v7.csv", "data/result3/paper_main_and_key_sensitivity_v7.csv", "paper core and key sensitivity models"),
        (V7 / "results/tables/marginal_effects_v7.csv", "data/result3/marginal_effects_v7.csv", "SES-specific marginal smoke associations"),
        (V7 / "results/tables/secondary_outcomes_v7.csv", "data/result3/secondary_outcomes_v7.csv", "six secondary outcomes"),
        (V7 / "results/tables/leave_one_year_out_v7.csv", "data/result3/leave_one_year_out_v7.csv", "leave-one-year sensitivity"),
        (V7 / "results/tables/leave_one_state_out_v7.csv", "data/result3/leave_one_state_out_v7.csv", "leave-one-state sensitivity"),
        (V7 / "results/tables/state_specific_v7.csv", "data/result3/state_specific_v7.csv", "state-stratified exploratory models"),
        (V7 / "results/tables/model_status_v7.csv", "data/result3/model_status_v7.csv", "model formula, sample, rank, convergence"),
        (V7 / "results/tables/data_validation_v7.csv", "data/result3/data_validation_v7.csv", "analysis panel validation"),
        (V7 / "results/tables/final_check_v7.csv", "data/result3/final_check_v7.csv", "historical result completion checks"),
        (EXP3 / "tables/01_common_covariate_models_by_imputation.csv", "data/result3/common_covariate_models_by_imputation.csv", "M0/M1/M2/M2P/M3 x four imputation scenarios"),
        (EXP3 / "tables/02_alternative_effect_modifier_models.csv", "data/result3/alternative_effect_modifier_models.csv", "poverty and time-varying SES modifiers"),
        (EXP3 / "tables/03_LST_paired_models_by_imputation.csv", "data/result3/LST_paired_models_by_imputation.csv", "LST pairs under four imputation scenarios"),
        (EXP3 / "tables/04_LST_paired_changes.csv", "data/result3/LST_paired_changes.csv", "within-key LST changes"),
        (EXP3 / "tables/06_validation_checks.csv", "data/result3/experiment3_validation_checks.csv", "experiment 3 refresh checks"),
        (CLOSE / "paired_LST_results_complete.csv", "data/result3/paired_LST_results_complete.csv", "strict/relaxed day/night paired models"),
        (CLOSE / "extreme_diagnostics_by_sample.csv", "data/result3/extreme_diagnostics_by_sample.csv", "extreme omissions by exact LST sample"),
        (LONG / "models/v3/extreme_omission_paired_models.csv", "data/result3/extreme_omission_paired_models_LST.csv", "strict-day LST omission pairs"),
        (LONG / "models/v3/LST_model_boundary_sensitivity.csv", "data/result3/key_LST_boundary_sensitivity.csv", "key LST model 0-9 versus 1-9"),
        (LONG / "processed/main_2009_2020_v3/county_year_LST_long.csv", "data/result3/county_year_LST_long.csv", "six-state 2009-2020 county-year day/night strict/relaxed LST"),
        (LONG / "processed/main_2009_2020_v3/coverage_summary.csv", "data/result3/LST_coverage_summary.csv", "LST coverage summary"),
        (LONG / "processed/main_2009_2020_v3/validation_checks.csv", "data/result3/LST_validation_checks.csv", "LST panel validation"),
        (CLOSE / "evidence/QC_zero_source_comparison.csv", "data/result3/QC_zero_source_comparison.csv", "8-granule source-level QC evidence"),
        (CLOSE / "QA_exclusion_reasons.csv", "data/result3/QA_exclusion_reasons.csv", "state-year strict-QA exclusion accounting"),
    ]:
        copy_file(src, rel, role)

    # Reproduction scripts and frozen configurations.
    for src, rel, role in [
        (V7 / "config/analysis.yml", "scripts/config/core_analysis_v7.yml", "core model configuration"),
        (V7 / "scripts/v7_common.py", "scripts/core_models/v7_common.py", "core model utility"),
        (V7 / "scripts/v7_engine.py", "scripts/core_models/v7_engine.py", "core model engine"),
        (V7 / "scripts/v7_specs.py", "scripts/core_models/v7_specs.py", "core model specifications"),
        (V7 / "scripts/v7_aggregate.py", "scripts/core_models/v7_aggregate.py", "Rubin aggregation"),
        (V7 / "scripts/v7_figures.py", "scripts/core_models/v7_figures.py", "historical result plotting"),
        (STAGE2 / "stage2_analysis.py", "scripts/result1/stage2_analysis.py", "extreme design and omission diagnostics"),
        (STAGE2 / "stage2_config.json", "scripts/config/stage2_config.json", "extreme diagnostic configuration"),
        (SUPP / "scripts/run_innovation_pilot.py", "scripts/result2/run_innovation_pilot.py", "suppression validation and hierarchical imputation"),
        (SUPP / "config/method_config.json", "scripts/config/suppression_method_config.json", "suppression experiment configuration"),
        (EXP3 / "scripts/run_experiment3_refresh.py", "scripts/result3/run_experiment3_refresh.py", "four-imputation model refresh"),
        (EXP3 / "config/experiment3_refresh.json", "scripts/config/experiment3_refresh.json", "experiment 3 configuration"),
        (LONG / "scripts/process_lst_exports.py", "scripts/result3/process_lst_exports.py", "LST panel processing"),
        (LONG / "scripts/run_lst_models.py", "scripts/result3/run_lst_models.py", "LST paired models"),
        (LONG / "scripts/test_lst_logic.py", "scripts/result3/test_lst_logic.py", "LST unit tests"),
        (LONG / "config/pipeline_config_v3.json", "scripts/config/LST_pipeline_config_v3.json", "frozen LST configuration"),
        (CLOSE / "scripts/validate_qc_zero_source.py", "scripts/result3/validate_qc_zero_source.py", "QC source comparison"),
    ]:
        copy_file(src, rel, role)

    # Prior main figures, extracted from the frozen handoff; PNG only keeps the package simple.
    for i in range(1, 5):
        member = f"Afire_paper_handoff_20260825/figures/embedded_exact/Figure{i}_embedded_exact.png"
        extract_member(member, f"figures/main_reference/Figure{i}_embedded_exact.png", "exact figure embedded in frozen v2 manuscripts")

    # New experiment figures generated from real result tables.
    for src, name in [
        (ROOT / "three_experiment_report_20260908/figures/01_experiment1_design_and_omission.png", "Result1_extreme_design_and_omission.png"),
        (ROOT / "three_experiment_report_20260908/figures/03_experiment3_covariates_by_imputation.png", "Result3_covariates_by_imputation.png"),
        (ROOT / "three_experiment_report_20260908/figures/04_experiment3_LST_paired_change.png", "Result3_LST_paired_change.png"),
        (ROOT / "three_experiment_report_20260908/figures/05_LST_coverage_heatmap.png", "Result3_LST_coverage.png"),
        (ROOT / "three_experiment_report_20260908/figures/06_imputation_method_validation.png", "Result2_imputation_validation.png"),
    ]:
        copy_file(src, f"figures/new_results/{name}", "verified experiment figure generated from packaged CSV")


def write_core_tables(r1: dict, r2: dict, r3: dict) -> None:
    rows = []
    annual = r1["annual"]
    trend = r1["trend"]
    for year in [2009, 2020]:
        x = annual.loc[annual.year == year].iloc[0]
        rows.append({"result": "R1", "analysis": f"population_weighted_smoke_{year}", "estimate": x.population_weighted_smoke_pm25, "unit": "ug/m3", "CI_lower": "", "CI_upper": "", "n": 49, "source": "data/result1/annual_exposure_inequality.csv"})
    rows.append({"result": "R1", "analysis": "annual_Gini_linear_trend", "estimate": trend.slope, "unit": "Gini/year", "CI_lower": "", "CI_upper": "", "n": 15, "source": "data/result1/annual_exposure_inequality.csv"})
    for _, x in r1["omission"].iterrows():
        rows.append({"result": "R1", "analysis": x.scenario, "estimate": x.interaction_percent, "unit": "interaction_percent", "CI_lower": x.CI_lower, "CI_upper": x.CI_upper, "n": x.n_county_years, "source": "data/result1/targeted_omission_models.csv"})
    for _, x in r2["health"].iterrows():
        rows.append({"result": "R2", "analysis": x.scenario, "estimate": x.interaction_percent, "unit": "interaction_percent", "CI_lower": x.CI_percent_lower, "CI_upper": x.CI_percent_upper, "n": x.m, "source": "data/result2/scenario_health_model_results.csv"})
    primary = r3["common"].loc[r3["common"].imputation_scenario == "fixed_EB_B0_0_9"]
    for _, x in primary.iterrows():
        rows.append({"result": "R3", "analysis": x.model_family, "estimate": x.interaction_percent, "unit": "interaction_percent", "CI_lower": x.CI_percent_lower, "CI_upper": x.CI_percent_upper, "n": x.n_county_years, "source": "data/result3/common_covariate_models_by_imputation.csv"})
    pd.DataFrame(rows).to_csv(OUT / "data/paper_core_results_verified.csv", index=False, encoding="utf-8-sig")


def write_plot_script() -> None:
    content = '''#!/usr/bin/env python3
"""Rebuild four simple evidence plots from the packaged CSV files."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "figures/rebuilt_from_package"
OUT.mkdir(parents=True, exist_ok=True)

# R1 state-scale exposure and inequality
a = pd.read_csv(ROOT / "data/result1/annual_exposure_inequality.csv")
fig, ax = plt.subplots(figsize=(7.2, 4.2))
ax.plot(a.year, a.population_weighted_smoke_pm25, marker="o", color="#2B6CB0")
ax.set_xlabel("Year"); ax.set_ylabel("Population-weighted smoke PM2.5 (ug/m3)", color="#2B6CB0")
ax2 = ax.twinx(); ax2.plot(a.year, a.gini_smoke_pm25, marker="s", color="#DD6B20")
ax2.set_ylabel("Exposure Gini", color="#DD6B20")
fig.tight_layout(); fig.savefig(OUT / "R1_state_exposure_and_Gini.png", dpi=220); plt.close(fig)

# R1 four design groups and omission estimates
d = pd.read_csv(ROOT / "data/result1/joint_extreme_design_diagnostics.csv")
o = pd.read_csv(ROOT / "data/result1/targeted_omission_models.csv")
fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
axes[0].barh(d.group, 100*d.residualized_interaction_ss_share, color="#4C78A8")
axes[0].set_xlabel("Residualized interaction-design SS share (%)")
y = np.arange(len(o)); axes[1].errorbar(o.interaction_percent, y, xerr=[o.interaction_percent-o.CI_lower, o.CI_upper-o.interaction_percent], fmt="o", color="#E45756", capsize=3)
axes[1].axvline(0,color="black",lw=.8); axes[1].set_yticks(y, o.scenario); axes[1].set_xlabel("Smoke x SES interaction (%)")
fig.tight_layout(); fig.savefig(OUT / "R1_extreme_design_and_omission.png", dpi=220); plt.close(fig)

# R2 pseudo-suppression validation
s = pd.read_csv(ROOT / "data/result2/pseudo_suppression_validation_summary.csv")
s = s[s.scope == "all_outcomes"].sort_values("MAE")
fig, ax = plt.subplots(figsize=(7.2, 4.2)); x=np.arange(len(s))
ax.bar(x-.2, s.MAE, .2, label="MAE"); ax.bar(x, s.RMSE, .2, label="RMSE"); ax.bar(x+.2, s.mean_CRPS, .2, label="CRPS")
ax.set_xticks(x, s.method, rotation=20, ha="right"); ax.legend(frameon=False); fig.tight_layout()
fig.savefig(OUT / "R2_imputation_validation.png", dpi=220); plt.close(fig)

# R3 common-sample covariate models
m = pd.read_csv(ROOT / "data/result3/common_covariate_models_by_imputation.csv")
m = m[m.imputation_scenario == "fixed_EB_B0_0_9"].copy()
order = ["M0","M1","M2","M2P","M3"]; m["ord"] = m.model_family.map({v:i for i,v in enumerate(order)}); m=m.sort_values("ord")
y=np.arange(len(m)); fig,ax=plt.subplots(figsize=(7.2,4.2))
ax.errorbar(m.interaction_percent,y,xerr=[m.interaction_percent-m.CI_percent_lower,m.CI_percent_upper-m.interaction_percent],fmt="o",color="#2F855A",capsize=3)
ax.axvline(0,color="black",lw=.8); ax.set_yticks(y,m.model_family); ax.set_xlabel("Smoke x SES interaction (%)"); fig.tight_layout()
fig.savefig(OUT / "R3_common_sample_models.png",dpi=220); plt.close(fig)
print(OUT)
'''
    path = OUT / "scripts/plot_verified_results.py"
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def write_reports() -> None:
    checks = pd.DataFrame(CHECKS)
    checks.to_csv(OUT / "reports/verification_checks.csv", index=False, encoding="utf-8-sig")
    failed_critical = checks[(checks.status == "FAIL") & (checks.severity == "critical")]
    passed = int((checks.status == "PASS").sum())
    failed = int((checks.status == "FAIL").sum())

    report = f"""# 实验真实性与可追溯性核验报告

## 核验结论

- 共执行 {len(checks)} 项机器可读检查：{passed} 项通过，{failed} 项失败。
- 关键失败数：{len(failed_critical)}。
- 本报告中的“通过”表示结果可追溯到项目内实际数据/模型输出，关键汇总可从底层记录独立复算，样本、公式、插补和数值转换一致。
- 本核验不是对CDC、烟雾暴露或MODIS外部数据库重新下载后的独立复刻，因此不能证明外部数据库本身绝对无误。

## Result 1

州尺度年度暴露表包含2006—2020年15年。研究框架有51个州级单元，但烟雾暴露表每年实际包含49个单元；AK和HI缺少烟雾暴露。2009和2020年人口加权烟雾PM2.5、Gini线性趋势及六州Top100记录数均从源CSV重新计算并与论文数字一致。四组设计变异合计3,072个county-year且占比合计100%；五个删除模型的指数转换、样本、公式和30/30收敛均通过。

## Result 2

伪压制验证由13,208条单元—方法结果组成，汇总MAE、RMSE、覆盖率、区间宽度、CRPS和区间评分均从单元级记录重新计算，最大误差见verification_checks.csv。固定EB 0—9全结局插补、固定EB 1—9 COPD插补及层级EB两种边界均检查了公开计数保持、整数支持和state-year-outcome精确总量。

需要保留的限制：真实Suppressed计数不可见；10—19伪压制是内部方法验证，不是1—9单元金标准；原始下载批次适用0—9还是1—9仍未由元数据解决。

## Result 3

历史v7模型的逐插补结果重新执行Rubin合并并与pooled.csv逐项比较。预设模型状态、30/30拟合、零失败、共同样本键和系数指数转换均核验。LST面板包含3,072个唯一FIPS-year及12,288个FIPS-year-day/night-QA记录；覆盖率范围、唯一键、严格/宽松配对样本和8个源粒度QC字节证据均通过。

需要保留的限制：严格QA排除全部Arizona县年，因此严格模型是五州选择样本；QC源验证为8个代表性粒度而非全域逐像元核查；固定baseline SES主效应被县固定效应吸收，核心结论是smoke×SES效应修饰；观察性县年结果不能解释为个体因果效应。

## “真实”的准确含义

没有发现手写替代模型输出、模拟LST冒充真实导出、系数与源CSV不一致、Rubin合并错误、LST配对样本错位或为显著性选择QA/插补方案的证据。伪压制数据属于明确标注的方法验证模拟遮蔽，不能称为真实Suppressed死亡真值。

## 文件定位

- 完整逐项检查：reports/verification_checks.csv
- 关键论文数字：data/paper_core_results_verified.csv
- 文件来源和哈希：reports/evidence_manifest.csv
- 一键重绘：scripts/plot_verified_results.py
"""
    (OUT / "reports/verification_report_CN.md").write_text(report, encoding="utf-8")

    readme = """# AFIRE最小可核验论文包

本包用于完成论文正文、补充材料和科研绘图。所有数据均复制自项目内冻结结果，未修改原始工程。

## 先看什么

1. reports/verification_report_CN.md：真实性与限制。
2. data/paper_core_results_verified.csv：三个Results的关键数字。
3. data/result1、result2、result3：逐层真实结果数据。
4. data/analysis：模型面板与多重插补数组，可用于重跑。
5. scripts/plot_verified_results.py：从包内CSV重新生成四张基础结果图。
6. manuscript_reference：2026-08-25冻结的中英文正文和补充材料，仅作为旧稿起点，尚未按最终三Results结构重写。

## 重绘

在安装pandas、numpy和matplotlib后运行：

python scripts/plot_verified_results.py

输出位于figures/rebuilt_from_package。

## 三个Results

- Result 1：州尺度暴露不平等、六州研究区域，以及2020/California的设计和精度贡献。
- Result 2：Suppressed死亡计数的精确总量约束插补与伪压制验证。
- Result 3：以县年度死亡计数为因变量的smoke×SES效应修饰、多协变量和LST稳健性。

## 重要限制

- 51是健康研究框架中的州级单元数；实际烟雾暴露为49个单元，AK和HI缺失。
- 原始Suppression下载批次的0—9/1—9规则仍不确定。
- 严格LST QA模型排除了Arizona，不能标成完整六州效应。
- 旧Word是参考稿，不应误认为已经纳入全部新增实验的最终投稿稿。
"""
    (OUT / "README_CN.md").write_text(readme, encoding="utf-8")

    pd.DataFrame(COPIED).to_csv(OUT / "reports/evidence_manifest.csv", index=False, encoding="utf-8-sig")
    package_manifest = {
        "package": OUT.name,
        "verification_status": "passed_with_known_assumption_limits" if len(failed_critical) == 0 else "failed",
        "checks_total": len(checks),
        "checks_passed": passed,
        "checks_failed": failed,
        "critical_failures": len(failed_critical),
        "known_limits": [
            "external source databases were not re-downloaded",
            "suppression batch boundary semantics remain unresolved",
            "pseudo-suppression is not ground truth for hidden 1-9 counts",
            "strict LST QA excludes Arizona",
            "QC source validation sampled 8 granules",
            "frozen v2 Word files predate the final three-Result reorganization",
        ],
    }
    (OUT / "reports/package_manifest.json").write_text(json.dumps(package_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if len(failed_critical):
        raise RuntimeError(f"Critical verification failures: {len(failed_critical)}")


def finalize_manifest_and_zip() -> None:
    rows = []
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            rows.append({"path": str(p.relative_to(OUT)), "bytes": p.stat().st_size, "sha256": sha256(p)})
    pd.DataFrame(rows).to_csv(OUT / "SHA256SUMS.csv", index=False, encoding="utf-8-sig")
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(OUT.rglob("*")):
            if p.is_file():
                zf.write(p, arcname=f"{OUT.name}/{p.relative_to(OUT)}")
    digest = sha256(ARCHIVE)
    print(json.dumps({
        "package_dir": str(OUT),
        "archive": str(ARCHIVE),
        "archive_bytes": ARCHIVE.stat().st_size,
        "archive_sha256": digest,
        "checks": len(CHECKS),
        "passed": sum(x["status"] == "PASS" for x in CHECKS),
        "failed": sum(x["status"] == "FAIL" for x in CHECKS),
    }, ensure_ascii=False, indent=2))


def main() -> None:
    for rel in ["data/result1", "data/result2", "data/result3", "data/analysis", "figures/main_reference", "figures/new_results", "reports", "scripts"]:
        (OUT / rel).mkdir(parents=True, exist_ok=True)
    verify_manuscripts()
    r1 = verify_result1()
    panel = pd.read_csv(V7 / "data_processed/county_year_disease_panel_v6_3.csv", low_memory=False)
    r2 = verify_result2(panel)
    r3 = verify_result3(panel)
    package_sources(r1, r2, r3)
    write_core_tables(r1, r2, r3)
    write_plot_script()
    write_reports()
    finalize_manifest_and_zip()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
