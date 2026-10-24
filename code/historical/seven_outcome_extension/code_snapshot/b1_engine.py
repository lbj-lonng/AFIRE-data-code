#!/usr/bin/env python3
"""AFIRE B1 (1--9) result unification and joint covariate adjustment.

All writes are confined to this analysis directory.  Authoritative project
inputs and historical results are read-only.  The program supports staged and
resumable execution; a model checkpoint is valid only when its full signature
matches the current frozen configuration, sample and imputation array.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import shutil
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / "tmp/matplotlib"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
from scipy.linalg import qr
from scipy.special import gammaln
from scipy.stats import norm, t as student_t


HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = HERE / "00_protocol/config.json"
TERM = "pm25_iqr:ses_baseline_std"
EXPOSURE = "pm25_iqr"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def key_hash(data: pd.DataFrame) -> str:
    keys = data[["county_fips", "year"]].drop_duplicates().sort_values(["county_fips", "year"])
    value = "\n".join(f"{int(fips):05d}-{int(year)}" for fips, year in keys.itertuples(index=False, name=None))
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def bool_series(x: pd.Series) -> pd.Series:
    if x.dtype == bool:
        return x
    return x.astype(str).str.lower().isin(["true", "1", "yes"])


def effect_fields(beta: float, low: float, high: float) -> dict[str, float]:
    return {
        "interaction_percent": 100.0 * math.expm1(beta),
        "CI_percent_lower": 100.0 * math.expm1(low),
        "CI_percent_upper": 100.0 * math.expm1(high),
    }


def zscore_series(series: pd.Series) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    sd = float(x.std(ddof=1))
    if not np.isfinite(sd) or sd <= 0:
        return pd.Series(np.nan, index=series.index, dtype=float)
    return (x - float(x.mean())) / sd


def load_prepared_panel(config: dict) -> pd.DataFrame:
    root = Path(config["project_root"])
    panel = pd.read_csv(root / config["inputs"]["panel"], low_memory=False)
    for col in ["row_id", "county_fips", "year", "population"]:
        panel[col] = pd.to_numeric(panel[col], errors="coerce")
    if panel[["row_id", "county_fips", "year", "population"]].isna().any().any():
        raise RuntimeError("authoritative panel has invalid required identifiers/population")
    panel["row_id"] = panel.row_id.astype(np.int64)
    panel["county_fips"] = panel.county_fips.astype(np.int64)
    panel["year"] = panel.year.astype(np.int64)
    panel["county_model"] = panel.county_fips.astype(str)
    panel["year_model"] = panel.year.astype(str)
    panel["state_year"] = panel.state_abbr.astype(str) + "_" + panel.year_model

    smoke_candidates = [
        "county_smoke_pm25_annual_burden_y",
        "county_smoke_pm25_annual_burden_x",
        "county_smoke_pm25_annual_burden",
    ]
    smoke_col = next((c for c in smoke_candidates if c in panel), None)
    if smoke_col is None:
        raise RuntimeError("smoke source column not found")
    panel["nonwildfire_pm25_candidate"] = (
        pd.to_numeric(panel.pm25_annual_mean, errors="coerce")
        - pd.to_numeric(panel[smoke_col], errors="coerce")
    )
    panel["log_population_density_v7"] = np.log1p(
        pd.to_numeric(panel.population_density_km2, errors="coerce")
    )
    mapping = {
        "age65_std_v7": "age65_share",
        "density_std_v7": "log_population_density_v7",
        "drought_d1_fs_std_v7": "drought_fireseason_D1",
        "temperature_fs_std_v7": "temperature_fireseason_mean",
        "pm25_total_std_v7": "pm25_annual_mean",
        "ozone_std_v7": "ozone_annual_mean",
        "nonwildfire_pm25_std_v7": "nonwildfire_pm25_candidate",
        "smoking_std_v7": "smoking_prevalence",
    }
    unique = panel[["county_fips", "year"] + list(mapping.values()) + ["precipitation_fireseason_total"]].drop_duplicates(["county_fips", "year"])
    index = pd.MultiIndex.from_frame(panel[["county_fips", "year"]])
    for output, source in mapping.items():
        unique[output] = zscore_series(unique[source])
        panel[output] = index.map(unique.set_index(["county_fips", "year"])[output])
    unique["precipitation_fs_std_extension"] = zscore_series(unique.precipitation_fireseason_total)
    panel["precipitation_fs_std_extension"] = index.map(
        unique.set_index(["county_fips", "year"]).precipitation_fs_std_extension
    )

    lst = pd.read_csv(root / config["inputs"]["LST_panel"], low_memory=False)
    lst = lst.loc[
        lst.QA_rule.eq("relaxed") & lst.period.eq("day"),
        ["FIPS", "year", "LST_C", "coverage", "eligible_s070"],
    ].copy()
    lst["county_fips"] = pd.to_numeric(lst.FIPS, errors="raise").astype(np.int64)
    lst["year"] = pd.to_numeric(lst.year, errors="raise").astype(np.int64)
    if lst.duplicated(["county_fips", "year"]).any():
        raise RuntimeError("relaxed daytime LST panel has duplicate county-year keys")
    lst["day_LST_per10"] = pd.to_numeric(lst.LST_C, errors="coerce") / 10.0
    lst["relaxed_day_eligible_s070"] = bool_series(lst.eligible_s070)
    mapper = lst.set_index(["county_fips", "year"])
    panel["day_LST_per10"] = index.map(mapper.day_LST_per10)
    panel["relaxed_day_coverage"] = index.map(mapper.coverage)
    panel["relaxed_day_eligible_s070"] = index.map(mapper.relaxed_day_eligible_s070).fillna(False).astype(bool)
    return panel


def prepare_conditional_poisson(lam: np.ndarray, total: int, lower: int = 1, upper: int = 9) -> dict:
    lam = np.asarray(lam, dtype=float)
    n = len(lam)
    if not lower * n <= total <= upper * n:
        raise ValueError(f"infeasible n={n}, total={total}, support={lower}..{upper}")
    positive = lam[lam > 0]
    fallback = float(np.median(positive)) if len(positive) else 1.0
    lam = np.where(np.isfinite(lam) & (lam > 0), lam, fallback)
    lam = lam / np.exp(np.mean(np.log(lam)))
    ks = np.arange(lower, upper + 1)
    weights = np.exp(np.log(lam)[:, None] * ks[None, :] - gammaln(ks + 1)[None, :])
    dp = np.zeros((n + 1, total + 1), dtype=float)
    dp[n, 0] = 1.0
    for i in range(n - 1, -1, -1):
        for s in range(total + 1):
            dp[i, s] = math.fsum(
                weights[i, k - lower] * dp[i + 1, s - k] for k in ks if k <= s
            )
        scale = dp[i].max()
        if scale > 0:
            dp[i] /= scale
    if not np.isfinite(dp[0, total]) or dp[0, total] <= 0:
        raise ValueError("conditional support has zero/nonfinite mass")
    return {"weights": weights, "dp": dp, "total": int(total), "lower": lower, "upper": upper}


def sample_prepared(prepared: dict, rng: np.random.Generator) -> np.ndarray:
    weights, dp = prepared["weights"], prepared["dp"]
    total, lower, upper = prepared["total"], prepared["lower"], prepared["upper"]
    n = len(weights)
    out = np.empty(n, dtype=int)
    remaining = total
    for i in range(n):
        n_left = n - i - 1
        kmin = max(lower, remaining - upper * n_left)
        kmax = min(upper, remaining - lower * n_left)
        choices = np.arange(kmin, kmax + 1)
        mass = np.array([
            weights[i, k - lower] * dp[i + 1, remaining - k] for k in choices
        ], dtype=float)
        mass /= mass.sum()
        value = int(rng.choice(choices, p=mass))
        out[i] = value
        remaining -= value
    if remaining != 0:
        raise AssertionError("conditional sampler failed exact total")
    return out


def enumerable_test() -> dict:
    lam = np.array([0.7, 1.4, 2.1])
    total = 6
    states = [x for x in itertools.product(range(1, 10), repeat=3) if sum(x) == total]
    raw = np.array([
        np.prod(lam ** np.array(x) / np.exp(gammaln(np.array(x) + 1))) for x in states
    ])
    exact = raw / raw.sum()
    prep = prepare_conditional_poisson(lam, total)
    rng = np.random.default_rng(90817)
    counts = {x: 0 for x in states}
    n = 100_000
    for _ in range(n):
        counts[tuple(sample_prepared(prep, rng))] += 1
    maximum = max(abs(counts[x] / n - p) for x, p in zip(states, exact))
    return {"test": "enumerable_conditional_poisson", "n": n, "maximum_probability_error": maximum, "passed": maximum < 0.01}


def generate_or_load_full_b1(config: dict, panel: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame, dict]:
    root = Path(config["project_root"])
    out_root = Path(config["output_root"])
    output = out_root / "tmp/fixed_EB_B1_1_9_all_outcomes_30.npz"
    check_path = out_root / "01_input_audit/imputation_integrity_check.csv"
    if output.exists() and check_path.exists():
        z = np.load(output)
        draws = np.asarray(z["draws"], dtype=float)
        return draws, pd.read_csv(check_path), {"cache": "reused", "path": str(output), "sha256": sha256(output)}

    if panel.row_id.nunique() != len(panel) or panel.row_id.min() != 0 or panel.row_id.max() != len(panel) - 1:
        raise RuntimeError("row_id must be a complete unique zero-based index")
    draws = np.tile(panel.deaths.to_numpy(float), (config["imputations"], 1))
    existing = np.load(root / config["inputs"]["existing_copd_B1_draws"])
    old_draws = np.asarray(existing["draws"], dtype=float)
    old_rows = np.asarray(existing["row_ids"], dtype=int)
    if old_draws.shape[0] != config["imputations"]:
        raise RuntimeError("existing COPD B1 does not contain exactly 30 imputations")
    draws[:, old_rows] = old_draws

    weights = pd.read_csv(root / config["inputs"]["weight_model"])
    causes = list(config["secondary_outcomes"])
    seed_map: dict[str, int] = {"copd": int(existing["seed"][0])}
    failure_rows: list[dict] = []
    for cause_index, cause in enumerate(causes, start=1):
        c = panel.loc[panel.cause_id.eq(cause)].copy().reset_index(drop=True)
        w = weights.loc[
            weights.cause_id.eq(cause), ["state_abbr", "county_fips", "eb_history_rate"]
        ]
        c = c.merge(w, on=["state_abbr", "county_fips"], how="left", validate="many_to_one")
        if c.eb_history_rate.isna().any():
            raise RuntimeError(f"{cause}: missing historical EB weights")
        seed = int(config["fixed_eb_seed_extension_base"]) + cause_index
        seed_map[cause] = seed
        rng = np.random.default_rng(seed)
        for (state, year), group in c.groupby(["state_abbr", "year"], sort=True):
            suppressed = group.loc[group.death_suppressed, "row_id"].astype(int).to_numpy()
            observed = float(group.deaths.sum(skipna=True))
            state_total = int(round(float(group.state_deaths.iloc[0])))
            hidden = int(round(state_total - observed))
            if len(suppressed) == 0:
                if hidden != 0:
                    failure_rows.append({"cause_id": cause, "state_abbr": state, "year": year, "error": "no suppressed cells but nonzero hidden total"})
                continue
            lam_data = panel.set_index("row_id").loc[suppressed, ["population"]].copy()
            local_weight = c.set_index("row_id").loc[suppressed, "eb_history_rate"]
            prep = prepare_conditional_poisson(
                lam_data.population.to_numpy(float) * local_weight.to_numpy(float), hidden, 1, 9
            )
            for m in range(config["imputations"]):
                draws[m, suppressed] = sample_prepared(prep, rng)
    if failure_rows:
        pd.DataFrame(failure_rows).to_csv(out_root / "logs/imputation_generation_failures.csv", index=False)
        raise RuntimeError(f"{len(failure_rows)} imputation groups failed")

    if not np.isfinite(draws).all() or not np.equal(draws, np.floor(draws)).all():
        raise RuntimeError("full B1 imputation contains missing or noninteger values")
    np.savez_compressed(
        output,
        draws=draws.astype(np.int32),
        row_ids=panel.row_id.to_numpy(np.int32),
        causes=np.array(sorted(panel.cause_id.unique()), dtype="U64"),
        seed_map_json=np.array([json.dumps(seed_map, sort_keys=True)]),
        lower=np.array([1], dtype=np.int8),
        upper=np.array([9], dtype=np.int8),
    )

    integrity_rows: list[dict] = []
    for cause, c in panel.groupby("cause_id", sort=True):
        row_ids = c.row_id.astype(int).to_numpy()
        sup = c.death_suppressed.to_numpy(bool)
        public = ~sup
        cause_draws = draws[:, row_ids]
        public_expected = c.deaths.to_numpy(float)[public]
        public_equal = bool(np.all(cause_draws[:, public] == public_expected[None, :]))
        suppressed_values = cause_draws[:, sup]
        bounds = bool(np.all((suppressed_values >= 1) & (suppressed_values <= 9)))
        integers = bool(np.equal(suppressed_values, np.floor(suppressed_values)).all())
        max_error = 0.0
        for (_, _), group in c.groupby(["state_abbr", "year"], sort=True):
            total = float(group.state_deaths.iloc[0])
            error = np.abs(draws[:, group.row_id.astype(int).to_numpy()].sum(axis=1) - total).max()
            max_error = max(max_error, float(error))
        integrity_rows.append({
            "cause_id": cause,
            "n_rows": len(c),
            "n_suppressed": int(sup.sum()),
            "n_public_zero": int((public & c.deaths.eq(0).to_numpy()).sum()),
            "n_public_positive": int((public & c.deaths.gt(0).to_numpy()).sum()),
            "n_imputations": draws.shape[0],
            "public_counts_unchanged_all_30": public_equal,
            "suppressed_integer_all_30": integers,
            "suppressed_bounds_1_9_all_30": bounds,
            "maximum_state_year_total_error": max_error,
            "exact_state_year_totals_all_30": max_error == 0,
            "county_year_outcome_key_unique": not c.duplicated(["county_fips", "year", "cause_id"]).any(),
            "seed": seed_map[cause],
            "source": "existing verified COPD B1 draws" if cause == "copd" else "exact conditional-Poisson fixed historical-EB extension",
        })
    checks = pd.DataFrame(integrity_rows)
    checks.to_csv(check_path, index=False)
    return draws, checks, {"cache": "generated", "path": str(output), "sha256": sha256(output)}


@dataclass(frozen=True)
class Job:
    model_id: str
    analysis_block: str
    cause_id: str
    family: str
    formula: str
    exposure_term: str
    interaction_term: str
    required: tuple[str, ...]
    year_min: int
    year_max: int
    include_states: tuple[str, ...] = ()
    exclude_states: tuple[str, ...] = ()
    exclude_years: tuple[int, ...] = ()
    sample_mode: str = "model_specific"
    label: str = ""


def build_design(subset: pd.DataFrame, job: Job):
    frame = patsy.dmatrix(job.formula, subset, return_type="dataframe")
    names = list(frame.columns)
    protected_terms = [job.exposure_term, job.interaction_term]
    for term in protected_terms:
        if term not in names:
            raise RuntimeError(f"{job.model_id}: protected term {term} absent")
    matrix = np.asarray(frame, dtype=float)
    if not np.isfinite(matrix).all():
        raise RuntimeError(f"{job.model_id}: nonfinite design")
    protected_indices = [names.index(x) for x in protected_terms]
    protected = matrix[:, protected_indices]
    if np.linalg.matrix_rank(protected) != len(protected_indices):
        raise RuntimeError(f"{job.model_id}: protected terms collinear")
    q_protected, _ = np.linalg.qr(protected, mode="reduced")
    remaining_indices = [i for i in range(matrix.shape[1]) if i not in protected_indices]
    remaining = matrix[:, remaining_indices]
    residual = remaining - q_protected @ (q_protected.T @ remaining)
    if residual.shape[1]:
        _, r_matrix, pivots = qr(residual, mode="economic", pivoting=True)
        diagonal = np.abs(np.diag(r_matrix))
        tolerance = max(residual.shape) * np.finfo(float).eps * (diagonal.max() if diagonal.size else 0.0)
        nuisance_rank = int(np.sum(diagonal > tolerance))
        nuisance_indices = [remaining_indices[int(i)] for i in pivots[:nuisance_rank]]
    else:
        nuisance_indices = []
    selected = sorted(protected_indices + nuisance_indices)
    reduced = frame.iloc[:, selected]
    x = np.asarray(reduced, dtype=float)
    if np.linalg.matrix_rank(x) != x.shape[1]:
        raise RuntimeError(f"{job.model_id}: rank deficient after alias removal")
    reduced_names = list(reduced.columns)
    return x, reduced_names, {
        job.exposure_term: reduced_names.index(job.exposure_term),
        job.interaction_term: reduced_names.index(job.interaction_term),
    }, len(names), [names[i] for i in range(len(names)) if i not in selected]


def cluster_kwargs(groups: np.ndarray) -> dict:
    return {"cov_type": "cluster", "cov_kwds": {"groups": groups, "use_correction": True}}


def estimate_nb_alpha(mean_y: np.ndarray, x: np.ndarray, offset: np.ndarray) -> tuple[float, np.ndarray]:
    poisson = sm.GLM(mean_y, x, family=sm.families.Poisson(), offset=offset).fit(maxiter=300, tol=1e-9)
    mu = np.asarray(poisson.fittedvalues, dtype=float)
    alpha = float(np.clip(np.sum((mean_y - mu) ** 2 - mean_y) / max(np.sum(mu ** 2), 1e-12), 0.001, 2.0))
    nb = sm.GLM(mean_y, x, family=sm.families.NegativeBinomial(alpha=alpha), offset=offset).fit(
        start_params=np.asarray(poisson.params, dtype=float), maxiter=300, tol=1e-9
    )
    return alpha, np.asarray(nb.params, dtype=float)


def fit_one(y: np.ndarray, x: np.ndarray, offset: np.ndarray, groups: np.ndarray,
            family: str, alpha: float | None, warm: np.ndarray):
    if family == "poisson":
        model = sm.GLM(y, x, family=sm.families.Poisson(), offset=offset)
        attempts = [dict(start_params=warm, maxiter=300, tol=1e-9), dict(maxiter=600, tol=1e-8)]
    else:
        model = sm.GLM(y, x, family=sm.families.NegativeBinomial(alpha=float(alpha)), offset=offset)
        attempts = [dict(start_params=warm, maxiter=200, tol=1e-8), dict(maxiter=500, tol=1e-7)]
    errors = []
    for kwargs in attempts:
        try:
            result = model.fit(**kwargs, **cluster_kwargs(groups))
            if not bool(getattr(result, "converged", True)):
                raise RuntimeError("GLM did not converge")
            if not np.isfinite(np.asarray(result.params)).all() or not np.isfinite(np.asarray(result.cov_params())).all():
                raise RuntimeError("nonfinite fit output")
            return result, "poisson_glm" if family == "poisson" else "negative_binomial_glm"
        except Exception as exc:
            errors.append(repr(exc))
    if family == "poisson":
        try:
            result = sm.Poisson(y, x, offset=offset).fit(
                start_params=warm, method="lbfgs", maxiter=1000, disp=0,
                cov_type="cluster", cov_kwds={"groups": groups, "use_correction": True},
            )
            if not bool(getattr(result, "mle_retvals", {}).get("converged", True)):
                raise RuntimeError("discrete Poisson did not converge")
            return result, "poisson_discrete_lbfgs"
        except Exception as exc:
            errors.append(repr(exc))
    raise RuntimeError(" | ".join(errors))


def rubin_pool(estimates: Iterable[float], within_variances: Iterable[float]) -> dict:
    q = np.asarray(list(estimates), dtype=float)
    u = np.asarray(list(within_variances), dtype=float)
    valid = np.isfinite(q) & np.isfinite(u) & (u >= 0)
    q, u = q[valid], u[valid]
    if len(q) == 0:
        raise RuntimeError("no valid imputation estimates")
    m = len(q)
    qbar = float(q.mean())
    ubar = float(u.mean())
    between = float(q.var(ddof=1)) if m > 1 else 0.0
    total = float(ubar + (1 + 1 / m) * between)
    se = math.sqrt(max(total, 0))
    r = (1 + 1 / m) * between / ubar if ubar > 0 else (np.inf if between > 0 else 0)
    df = float((m - 1) * (1 + 1 / r) ** 2) if m > 1 and np.isfinite(r) and r > 0 else 1e12
    crit = float(student_t.ppf(0.975, df)) if df < 1e8 else 1.959963984540054
    stat = abs(qbar / se) if se > 0 else np.nan
    p = float(2 * student_t.sf(stat, df)) if df < 1e8 else float(2 * norm.sf(stat))
    fmi = float((r + 2 / (df + 3)) / (r + 1)) if np.isfinite(r) and r >= 0 else 1.0
    return {
        "beta": qbar, "SE": se, "beta_CI_lower": qbar - crit * se,
        "beta_CI_upper": qbar + crit * se, "P_value": p,
        "within_variance": ubar, "between_imputation_variance": between,
        "total_variance": total, "df_rubin": df,
        "fraction_missing_information": fmi,
        "monte_carlo_error": math.sqrt(between / m) if m > 1 else 0.0,
        "n_imputations": m,
    }


def filter_for_job(data: pd.DataFrame, job: Job, s_joint_keys: set[tuple[int, int]]) -> pd.DataFrame:
    sub = data.loc[
        data.cause_id.eq(job.cause_id) & data.year.between(job.year_min, job.year_max)
    ].copy()
    if job.include_states:
        sub = sub.loc[sub.state_abbr.isin(job.include_states)].copy()
    if job.exclude_states:
        sub = sub.loc[~sub.state_abbr.isin(job.exclude_states)].copy()
    if job.exclude_years:
        sub = sub.loc[~sub.year.isin(job.exclude_years)].copy()
    if job.sample_mode == "joint":
        mask = [(int(f), int(y)) in s_joint_keys for f, y in sub[["county_fips", "year"]].itertuples(index=False, name=None)]
        sub = sub.loc[mask].copy()
    needed = ["row_id", "population", "county_fips", "year"] + list(job.required)
    missing = [x for x in needed if x not in sub]
    if missing:
        raise RuntimeError(f"{job.model_id}: missing columns {missing}")
    if job.sample_mode == "joint" and sub[needed].isna().any().any():
        raise RuntimeError(f"{job.model_id}: S_joint contains model-required missing values")
    sub = sub.dropna(subset=needed)
    sub = sub.loc[sub.population > 0].copy()
    return sub.sort_values(["county_fips", "year"]).reset_index(drop=True)


_WORKER_CONFIG: dict | None = None
_WORKER_DATA: pd.DataFrame | None = None
_WORKER_DRAWS: np.ndarray | None = None
_WORKER_SJOINT: set[tuple[int, int]] | None = None
_WORKER_DRAW_HASH: str | None = None


def init_worker(config_path: str) -> None:
    global _WORKER_CONFIG, _WORKER_DATA, _WORKER_DRAWS, _WORKER_SJOINT, _WORKER_DRAW_HASH
    _WORKER_CONFIG = json.loads(Path(config_path).read_text(encoding="utf-8"))
    _WORKER_DATA = load_prepared_panel(_WORKER_CONFIG)
    zpath = Path(_WORKER_CONFIG["output_root"]) / "tmp/fixed_EB_B1_1_9_all_outcomes_30.npz"
    z = np.load(zpath)
    _WORKER_DRAWS = np.asarray(z["draws"], dtype=float)
    _WORKER_DRAW_HASH = sha256(zpath)
    members = pd.read_csv(Path(_WORKER_CONFIG["output_root"]) / "06_qc/sample_membership.csv")
    members = members.loc[bool_series(members.S_joint)]
    _WORKER_SJOINT = set(zip(members.county_fips.astype(int), members.year.astype(int)))


def fit_job_worker(job_dict: dict) -> dict:
    assert _WORKER_CONFIG is not None and _WORKER_DATA is not None and _WORKER_DRAWS is not None
    assert _WORKER_SJOINT is not None and _WORKER_DRAW_HASH is not None
    job = Job(**job_dict)
    out_root = Path(_WORKER_CONFIG["output_root"])
    checkpoint_path = out_root / "03_model_fits/checkpoints" / f"{job.model_id}.json"
    per_path = out_root / "03_model_fits/per_imputation" / f"{job.model_id}.csv"
    subset = filter_for_job(_WORKER_DATA, job, _WORKER_SJOINT)
    sample_hash = key_hash(subset)
    signature = {
        "protocol_version": _WORKER_CONFIG["protocol_version"],
        "model_id": job.model_id,
        "formula": job.formula,
        "family": job.family,
        "sample_hash": sample_hash,
        "n_rows": len(subset),
        "imputation_scenario": "fixed_EB_B1_1_9",
        "draw_file_sha256": _WORKER_DRAW_HASH,
        "n_imputations": int(_WORKER_DRAWS.shape[0]),
        "offset": "log(population)",
        "cluster": "county_fips",
        "exposure_term": job.exposure_term,
        "interaction_term": job.interaction_term,
    }
    old = json.loads(checkpoint_path.read_text()) if checkpoint_path.exists() else {}
    if old.get("status") == "completed_and_validated" and old.get("signature") == signature and per_path.exists():
        return old

    x, names, indices, original_columns, dropped = build_design(subset, job)
    outcomes = _WORKER_DRAWS[:, subset.row_id.astype(int).to_numpy()]
    offset = np.log(subset.population.to_numpy(float))
    groups = subset.county_fips.to_numpy(int)
    if job.family == "negative_binomial":
        alpha, warm = estimate_nb_alpha(outcomes.mean(axis=0), x, offset)
    elif job.family == "poisson":
        warm_fit = sm.GLM(outcomes.mean(axis=0), x, family=sm.families.Poisson(), offset=offset).fit(maxiter=300, tol=1e-9)
        alpha, warm = None, np.asarray(warm_fit.params, dtype=float)
    else:
        raise RuntimeError(f"unsupported family {job.family}")
    existing_fits = old.get("fits", []) if old.get("signature") == signature else []
    done = {int(x["imputation"]) for x in existing_fits if x.get("status") == "ok"}
    fits = list(existing_fits)
    started = time.time()
    eidx, iidx = indices[job.exposure_term], indices[job.interaction_term]
    for m, y in enumerate(outcomes, start=1):
        if m in done:
            continue
        try:
            fitted, estimator = fit_one(y, x, offset, groups, job.family, alpha, warm)
            params = np.asarray(fitted.params, dtype=float)
            cov = np.asarray(fitted.cov_params(), dtype=float)
            fits.append({
                "imputation": m, "status": "ok", "estimator": estimator,
                "exposure_beta": float(params[eidx]),
                "exposure_variance": float(cov[eidx, eidx]),
                "interaction_beta": float(params[iidx]),
                "interaction_variance": float(cov[iidx, iidx]),
                "exposure_interaction_covariance": float(cov[eidx, iidx]),
            })
        except Exception as exc:
            fits.append({"imputation": m, "status": "failed", "error": repr(exc)})
        write_json(checkpoint_path, {"status": "running", "signature": signature, "fits": fits})
    good = [x for x in fits if x.get("status") == "ok"]
    if len(good) != _WORKER_CONFIG["imputations"]:
        write_json(checkpoint_path, {"status": "failed", "signature": signature, "fits": fits})
        raise RuntimeError(f"{job.model_id}: only {len(good)}/30 valid fits")
    per = pd.DataFrame(good).sort_values("imputation")
    per_path.parent.mkdir(parents=True, exist_ok=True)
    per.to_csv(per_path, index=False)
    pool = rubin_pool(per.interaction_beta, per.interaction_variance)
    pool.update(effect_fields(pool["beta"], pool["beta_CI_lower"], pool["beta_CI_upper"]))
    result = {
        "status": "completed_and_validated", "signature": signature, "fits": good,
        "model_id": job.model_id, "analysis_block": job.analysis_block,
        "label": job.label or job.model_id, "cause_id": job.cause_id,
        "formula": job.formula, "model_family": job.family,
        "link": "log", "offset": "log(population)", "fixed_effects": "as encoded in formula",
        "standard_error_method": "county-clustered sandwich with finite-sample correction",
        "imputation_version": "fixed_EB_B1_1_9", "imputation_source": _WORKER_DRAW_HASH,
        "sample_id": f"{job.sample_mode}_{sample_hash}", "sample_hash": sample_hash,
        "n_county_years": int(len(subset)), "n_counties": int(subset.county_fips.nunique()),
        "n_states": int(subset.state_abbr.nunique()), "states": ",".join(sorted(subset.state_abbr.unique())),
        "year_min": int(subset.year.min()), "year_max": int(subset.year.max()),
        "design_rank": int(np.linalg.matrix_rank(x)), "design_columns": int(x.shape[1]),
        "original_design_columns": original_columns, "dropped_aliased_columns": dropped,
        "dispersion_alpha": alpha, "success_count": len(good), "convergence": "30/30",
        "run_source": "REFIT", "cache_status": "computed_or_resumed",
        "elapsed_seconds": time.time() - started, **pool,
    }
    write_json(checkpoint_path, result)
    return result


def registered_jobs(config: dict) -> list[Job]:
    f = config["formulas"]
    m0 = f["M0"]
    m1 = f["M1"]
    m2 = f["M2"]
    req0 = ("pm25_iqr", "ses_baseline_std")
    req1 = req0 + ("age65_std_v7", "density_std_v7")
    req2 = req1 + ("drought_d1_fs_std_v7", "temperature_fs_std_v7")
    jobs = [
        Job("O01_baseline_SES_fixed_2006_2020", "core", "copd", "negative_binomial", m0, EXPOSURE, TERM, req0, 2006, 2020, label="Baseline SES fixed"),
        Job("O02_Census_adjusted_2009_2020", "core", "copd", "negative_binomial", m1, EXPOSURE, TERM, req1, 2009, 2020, label="Census adjusted"),
        Job("O03_state_year_PPML_2009_2020", "core", "copd", "poisson", m1.replace("C(year_model)", "C(state_year)"), EXPOSURE, TERM, req1, 2009, 2020, label="State-year FE PPML"),
        Job("O04_drought_adjusted_2009_2020", "core", "copd", "negative_binomial", m1.replace(" + C(county_model)", " + drought_d1_fs_std_v7 + C(county_model)"), EXPOSURE, TERM, req1 + ("drought_d1_fs_std_v7",), 2009, 2020, label="Drought adjusted"),
        Job("O05_exclude_2020_drought", "core", "copd", "negative_binomial", m1.replace(" + C(county_model)", " + drought_d1_fs_std_v7 + C(county_model)"), EXPOSURE, TERM, req1 + ("drought_d1_fs_std_v7",), 2009, 2019, label="Drought adjusted, through 2019"),
        Job("O06_timevarying_SES_2010_2020", "core", "copd", "negative_binomial", "pm25_iqr + ses_timevarying_std + pm25_iqr:ses_timevarying_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + C(county_model) + C(year_model)", EXPOSURE, "pm25_iqr:ses_timevarying_std", ("pm25_iqr", "ses_timevarying_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7"), 2010, 2020, label="Time-varying SES"),
        Job("O07_lag1_2010_2020", "core", "copd", "negative_binomial", "pm25_lag1_iqr + pm25_lag1_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + C(county_model) + C(year_model)", "pm25_lag1_iqr", "pm25_lag1_iqr:ses_baseline_std", ("pm25_lag1_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7"), 2010, 2020, label="Lag-1 exposure"),
        Job("O08_lead1_placebo_2009_2019", "core", "copd", "negative_binomial", "pm25_lead1_iqr + pm25_lead1_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + C(county_model) + C(year_model)", "pm25_lead1_iqr", "pm25_lead1_iqr:ses_baseline_std", ("pm25_lead1_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7"), 2009, 2019, label="Lead-1 placebo"),
        Job("O09_three_state_air_2009_2020", "core", "copd", "negative_binomial", "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + pm25_total_std_v7 + ozone_std_v7 + C(county_model) + C(year_model)", EXPOSURE, TERM, req1 + ("drought_d1_fs_std_v7", "pm25_total_std_v7", "ozone_std_v7"), 2009, 2020, include_states=("ID", "OR", "WA"), label="Three-state air pollution"),
        Job("O10_temperature_adjusted_2009_2020", "core_reference", "copd", "negative_binomial", m2, EXPOSURE, TERM, req2, 2009, 2020, label="Temperature-adjusted reference"),
        Job("O11_full_environment_2009_2020", "core", "copd", "negative_binomial", "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + pm25_total_std_v7 + ozone_std_v7 + C(county_model) + C(year_model)", EXPOSURE, TERM, req2 + ("pm25_total_std_v7", "ozone_std_v7"), 2009, 2020, label="Full environment (total PM2.5 sensitivity)"),
        Job("OMIT_B_exclude_2020", "targeted_omission", "copd", "negative_binomial", m2, EXPOSURE, TERM, req2, 2009, 2020, exclude_years=(2020,), label="Exclude 2020"),
        Job("OMIT_C_exclude_CA", "targeted_omission", "copd", "negative_binomial", m2, EXPOSURE, TERM, req2, 2009, 2020, exclude_states=("CA",), label="Exclude California"),
        Job("OMIT_D_exclude_2020_and_CA", "targeted_omission", "copd", "negative_binomial", m2, EXPOSURE, TERM, req2, 2009, 2020, exclude_states=("CA",), exclude_years=(2020,), label="Exclude 2020 and California"),
        Job("OMIT_E_exclude_CA_x_2020_only", "targeted_omission", "copd", "negative_binomial", m2, EXPOSURE, TERM, req2, 2009, 2020, sample_mode="exclude_CA_x_2020", label="Exclude California in 2020 only"),
        Job("F06_period_2009_2016", "period", "copd", "negative_binomial", m2, EXPOSURE, TERM, req2, 2009, 2016, label="2009–2016"),
        Job("F07_period_2017_2020", "period", "copd", "negative_binomial", m2, EXPOSURE, TERM, req2, 2017, 2020, label="2017–2020"),
    ]
    # Correct the one non-rectangular omission after filtering via a dedicated sample mode.
    causes_labels = {
        "respiratory_system": "Respiratory system",
        "chronic_lower_respiratory": "Chronic lower respiratory",
        "asthma": "Asthma",
        "circulatory_system": "Circulatory system",
        "ischemic_heart_disease": "Ischemic heart disease",
        "cerebrovascular_disease": "Cerebrovascular disease",
    }
    for cause, label in causes_labels.items():
        jobs.append(Job(f"D_{cause}", "secondary_outcomes", cause, "negative_binomial", m2, EXPOSURE, TERM, req2, 2009, 2020, label=label))
    req_m3 = req2 + ("nonwildfire_pm25_std_v7", "ozone_std_v7")
    jobs.extend([
        Job("M3P_joint", "joint_adjustment", "copd", "negative_binomial", f["M3P_joint"], EXPOSURE, TERM, req_m3 + ("precipitation_fs_std_extension",), 2009, 2020, sample_mode="joint", label="M3 + precipitation"),
        Job("M3PL_joint", "joint_adjustment", "copd", "negative_binomial", f["M3PL_joint"], EXPOSURE, TERM, req_m3 + ("precipitation_fs_std_extension", "day_LST_per10"), 2009, 2020, sample_mode="joint", label="M3 + precipitation + daytime LST"),
    ])
    return jobs


# Patch non-rectangular omission without changing the generic Job schema.
_original_filter_for_job = filter_for_job
def filter_for_job(data: pd.DataFrame, job: Job, s_joint_keys: set[tuple[int, int]]) -> pd.DataFrame:  # type: ignore[no-redef]
    if job.sample_mode != "exclude_CA_x_2020":
        return _original_filter_for_job(data, job, s_joint_keys)
    surrogate = Job(**{**asdict(job), "sample_mode": "model_specific"})
    sub = _original_filter_for_job(data, surrogate, s_joint_keys)
    return sub.loc[~(sub.state_abbr.eq("CA") & sub.year.eq(2020))].reset_index(drop=True)


def input_paths(config: dict) -> list[tuple[str, Path, str]]:
    root = Path(config["project_root"])
    rows = []
    for name, rel in config["inputs"].items():
        path = root / rel
        if path.is_file():
            rows.append((name, path, "authoritative_or_provenance_input"))
    raw_county = root / "experiment_feasibility_20260906/source_snapshot/all/03/data_raw/health_county"
    raw_state = root / "experiment_feasibility_20260906/source_snapshot/all/03/data_raw/health_state"
    for path in sorted(raw_county.glob("*.csv")):
        rows.append((f"raw_county_{path.stem}", path, "raw_CDC_county_export"))
    for path in sorted(raw_state.glob("*.csv")):
        rows.append((f"raw_state_{path.stem}", path, "raw_CDC_state_export"))
    return rows


def write_input_manifest(config: dict, phase: str) -> pd.DataFrame:
    output = Path(config["output_root"]) / "01_input_audit/input_manifest.csv"
    records = []
    for name, path, role in input_paths(config):
        records.append({
            "input_id": name, "file_path": str(path), "role": role,
            "size_bytes": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns,
            f"sha256_{phase}": sha256(path),
        })
    current = pd.DataFrame(records)
    if phase == "before" or not output.exists():
        current.to_csv(output, index=False)
        return current
    prior = pd.read_csv(output)
    merged = prior.merge(current, on=["input_id", "file_path", "role", "size_bytes", "mtime_ns"], how="outer", validate="one_to_one")
    merged["hash_unchanged"] = merged.sha256_before.eq(merged.sha256_after)
    merged.to_csv(output, index=False)
    return merged


def reconcile_raw_mortality(config: dict, panel: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Verify panel status/counts and state margins directly against archived exports."""
    root = Path(config["project_root"])
    county_dir = root / "experiment_feasibility_20260906/source_snapshot/all/03/data_raw/health_county"
    county_parts = []
    for path in sorted(county_dir.glob("*.csv")):
        d = pd.read_csv(path, low_memory=False)
        needed = ["cause_id", "County Code", "Year", "Deaths"]
        if any(x not in d for x in needed):
            raise RuntimeError(f"unexpected archived county schema: {path}")
        x = d[needed].copy()
        x["county_fips"] = pd.to_numeric(x["County Code"], errors="raise").astype(int)
        x["year"] = pd.to_numeric(x["Year"], errors="raise").astype(int)
        x["raw_suppressed"] = x.Deaths.astype(str).str.strip().eq("Suppressed")
        x["raw_deaths_numeric"] = pd.to_numeric(x.Deaths, errors="coerce")
        x["raw_file"] = path.name
        county_parts.append(x[["cause_id", "county_fips", "year", "raw_suppressed", "raw_deaths_numeric", "raw_file"]])
    raw = pd.concat(county_parts, ignore_index=True)
    merged = panel[["cause_id", "county_fips", "year", "death_suppressed", "deaths", "source_file"]].merge(
        raw, on=["cause_id", "county_fips", "year"], how="outer", indicator=True, validate="one_to_one"
    )
    merged["status_match"] = merged.death_suppressed.eq(merged.raw_suppressed)
    merged["public_count_match"] = np.where(
        ~merged.raw_suppressed.fillna(False),
        np.isclose(merged.deaths, merged.raw_deaths_numeric, equal_nan=False),
        True,
    )
    merged["source_file_match"] = merged.apply(
        lambda r: Path(str(r.source_file)).name == str(r.raw_file), axis=1
    )
    summaries = []
    for cause, g in merged.groupby("cause_id", dropna=False):
        summaries.append({
            "cause_id": cause, "raw_county_rows": len(g),
            "merge_both_rows": int(g._merge.eq("both").sum()),
            "raw_suppressed": int(g.raw_suppressed.fillna(False).sum()),
            "raw_public_zero": int((~g.raw_suppressed.fillna(False) & g.raw_deaths_numeric.eq(0)).sum()),
            "status_matches": int(g.status_match.sum()),
            "public_count_matches": int(g.public_count_match.sum()),
            "source_file_matches": int(g.source_file_match.sum()),
            "all_rows_match": bool(g._merge.eq("both").all() and g.status_match.all() and g.public_count_match.all() and g.source_file_match.all()),
        })
    summary = pd.DataFrame(summaries)

    state_path = root / "experiment_feasibility_20260906/source_snapshot/all/03/data_raw/health_state/cdc_wonder_all_7_causes_state_year_2006_2020.csv"
    state = pd.read_csv(state_path, low_memory=False)
    state_col = next(x for x in state if x.startswith("State_State_"))
    year_col = next(x for x in state if x.startswith("Year_Unnamed:"))
    deaths_col = next(x for x in state if x.startswith("Deaths_Unnamed:"))
    state = state[["cause_id", state_col, year_col, deaths_col]].copy()
    state["state_fips"] = pd.to_numeric(state[state_col].astype(str).str.extract(r"\((\d{2})\)")[0], errors="coerce")
    state["year"] = pd.to_numeric(state[year_col], errors="coerce")
    state["raw_state_deaths"] = pd.to_numeric(state[deaths_col], errors="coerce")
    six_codes = sorted(panel.state_fips.unique())
    state = state.loc[state.state_fips.isin(six_codes)]
    margins = panel[["cause_id", "state_fips", "year", "state_deaths"]].drop_duplicates()
    state_compare = margins.merge(
        state[["cause_id", "state_fips", "year", "raw_state_deaths"]],
        on=["cause_id", "state_fips", "year"], how="outer", indicator=True, validate="one_to_one"
    )
    state_ok = bool(
        state_compare._merge.eq("both").all()
        and np.isclose(state_compare.state_deaths, state_compare.raw_state_deaths, equal_nan=False).all()
    )
    checks = [
        {"check_id": "raw_county_exports_cover_full_panel", "observed": int(merged._merge.eq("both").sum()), "expected": len(panel), "passed": merged._merge.eq("both").all()},
        {"check_id": "raw_county_status_and_public_counts_match_panel", "observed": int(summary.all_rows_match.sum()), "expected": 7, "passed": summary.all_rows_match.all()},
        {"check_id": "raw_state_exports_match_panel_state_totals", "observed": int(state_compare._merge.eq("both").sum()), "expected": len(margins), "passed": state_ok},
    ]
    return summary, checks


def freeze_samples(config: dict, data: pd.DataFrame) -> dict:
    out_root = Path(config["output_root"])
    c = data.loc[data.cause_id.eq("copd") & data.year.between(2009, 2020)].copy()
    if len(c) != 3072:
        raise RuntimeError(f"expected 3072 base COPD county-years, got {len(c)}")
    req_m3 = ["pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7", "drought_d1_fs_std_v7", "temperature_fs_std_v7", "nonwildfire_pm25_std_v7", "ozone_std_v7"]
    c["original_common_M3_complete"] = c[req_m3].notna().all(axis=1) & c.population.gt(0)
    c["precipitation_complete"] = c.precipitation_fs_std_extension.notna()
    c["relaxed_day_LST_eligible"] = c.relaxed_day_eligible_s070 & c.day_LST_per10.notna()
    c["S_joint"] = c.original_common_M3_complete & c.precipitation_complete & c.relaxed_day_LST_eligible
    c["exclusion_reason"] = np.select(
        [~c.original_common_M3_complete, ~c.precipitation_complete, ~c.relaxed_day_LST_eligible],
        ["not_in_original_M3_common_sample", "missing_precipitation", "not_eligible_relaxed_day_LST"],
        default="included_S_joint",
    )
    columns = ["county_fips", "state_abbr", "year", "row_id", "original_common_M3_complete", "precipitation_complete", "relaxed_day_LST_eligible", "relaxed_day_coverage", "S_joint", "exclusion_reason"]
    c[columns].sort_values(["county_fips", "year"]).to_csv(out_root / "06_qc/sample_membership.csv", index=False)
    c.loc[~c.S_joint, columns].sort_values(["state_abbr", "county_fips", "year"]).to_csv(out_root / "06_qc/sample_exclusions.csv", index=False)
    joint = c.loc[c.S_joint]
    if joint.empty:
        raise RuntimeError("S_joint is empty")
    return {
        "sample_id": "S_joint_" + key_hash(joint), "sample_hash": key_hash(joint),
        "n_county_years": len(joint), "n_counties": int(joint.county_fips.nunique()),
        "n_states": int(joint.state_abbr.nunique()), "states": sorted(joint.state_abbr.unique()),
        "n_starting_2009_2020": len(c), "n_original_common_M3": int(c.original_common_M3_complete.sum()),
        "n_relaxed_day_LST_eligible": int(c.relaxed_day_LST_eligible.sum()),
        "n_excluded_from_original_common_by_joint_requirements": int((c.original_common_M3_complete & ~c.S_joint).sum()),
    }


def validate_reused_checkpoint(path: Path, formula: str, sample_hash: str, draw_hash: str) -> tuple[bool, str, dict]:
    if not path.exists():
        return False, "checkpoint_missing", {}
    x = json.loads(path.read_text())
    sig = x.get("signature", {})
    fits = x.get("fits", [])
    checks = {
        "status": x.get("status") == "completed_and_validated",
        "formula": x.get("formula") == formula and sig.get("formula") == formula,
        "sample_hash": str(x.get("sample_hash")) == sample_hash and str(sig.get("sample_hash")) == sample_hash,
        "scenario": x.get("imputation_scenario") == "fixed_EB_B1_1_9" and sig.get("scenario") == "fixed_EB_B1_1_9",
        "draw_hash": sig.get("draw_source_hash") == draw_hash,
        "n_draws": sig.get("n_draws") == 30 and x.get("n_imputations") == 30,
        "fits": len(fits) == 30 and all(z.get("status") == "ok" and np.isfinite(z.get("estimate", np.nan)) and z.get("variance", -1) >= 0 for z in fits),
        "rank": x.get("design_rank") == x.get("design_columns"),
        "convergence": x.get("convergence") == "30/30",
    }
    passed = all(checks.values())
    return passed, "all_reuse_checks_pass" if passed else ";".join(k for k, v in checks.items() if not v), x


def reuse_existing(config: dict, s_joint: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    root, out_root = Path(config["project_root"]), Path(config["output_root"])
    common_source = root / config["inputs"]["existing_common_results"]
    lst_source = root / config["inputs"]["existing_LST_results"]
    shutil.copy2(common_source, out_root / "02_reused_results/common_covariate_models_by_imputation_source.csv")
    shutil.copy2(lst_source, out_root / "02_reused_results/LST_paired_models_by_imputation_source.csv")
    common_all = pd.read_csv(common_source)
    lst_all = pd.read_csv(lst_source)
    common = common_all.loc[
        common_all.imputation_scenario.eq("fixed_EB_B1_1_9") & common_all.model_family.isin(["M0", "M1", "M2", "M2P", "M3"])
    ].copy()
    lst = lst_all.loc[
        lst_all.imputation_scenario.eq("fixed_EB_B1_1_9") & lst_all.QA_rule.isin(["strict", "relaxed"])
        & lst_all.day_or_night.eq("day") & lst_all.model_family.isin(["M2", "M3"])
    ].copy()
    lst["LST_added"] = bool_series(lst.LST_added)
    draw_hash = sha256(root / config["inputs"]["existing_copd_B1_draws"])
    checkpoint_dir = root / config["inputs"]["existing_common_checkpoints"]
    audit = []
    for _, row in common.iterrows():
        cp = checkpoint_dir / f"{row.model_family}__common__fixed_EB_B1_1_9.json"
        passed, reason, _ = validate_reused_checkpoint(cp, row.formula, str(row.sample_hash), draw_hash)
        audit.append({"registry_item": f"common_{row.model_family}", "decision": "REUSED_VALIDATED" if passed else "REFIT_REQUIRED", "reason": reason, "source": str(cp), "sample_hash": row.sample_hash, "n_county_years": row.n_county_years})
        if not passed:
            raise RuntimeError(f"cannot validate reusable common result {row.model_family}: {reason}")
    for _, row in lst.iterrows():
        part = "withLST" if row.LST_added else "noLST"
        cp = checkpoint_dir / f"{row.model_family}__{row.QA_rule}_day__{part}__fixed_EB_B1_1_9.json"
        passed, reason, x = validate_reused_checkpoint(cp, xformula := str(row.formula), str(row.sample_hash), draw_hash)
        audit.append({"registry_item": f"LST_{row.QA_rule}_day_{row.model_family}_{part}", "decision": "REUSED_VALIDATED" if passed else "REFIT_REQUIRED", "reason": reason, "source": str(cp), "sample_hash": row.sample_hash, "n_county_years": row.n_county_years})
        if not passed:
            raise RuntimeError(f"cannot validate reusable LST result {row.model_id}: {reason}; formula={xformula}")
    if s_joint["sample_hash"] != "d15d10108a6a2bac":
        raise RuntimeError("S_joint differs from validated existing common sample; paired reference refits are required but not silently substituted")
    common["reuse_validation"] = "formula+sample+draw+30_fits+rank+convergence_verified"
    lst["reuse_validation"] = "formula+sample+draw+30_fits+rank+convergence_verified"
    return common, lst, pd.DataFrame(audit)


def result_from_reused(row: pd.Series, model_id: str | None = None) -> dict:
    return {
        "model_id": model_id or row.model_family, "analysis_block": row.get("analysis_block", "reused"),
        "label": model_id or row.model_family, "adjustment_family": row.model_family,
        "cause_id": "copd", "formula": row.formula,
        "model_family": "negative_binomial", "link": "log", "offset": "log(population)",
        "fixed_effects": "county + year", "standard_error_method": "county-clustered sandwich with finite-sample correction",
        "imputation_version": "fixed_EB_B1_1_9", "sample_id": f"reused_{row.sample_hash}",
        "sample_hash": str(row.sample_hash), "n_county_years": int(row.n_county_years),
        "n_counties": int(row.n_counties), "n_states": int(row.n_states),
        "year_min": int(row.year_min) if pd.notna(row.get("year_min", np.nan)) else 2009,
        "year_max": int(row.year_max) if pd.notna(row.get("year_max", np.nan)) else 2020,
        "design_rank": int(row.design_rank), "design_columns": int(row.design_columns),
        "success_count": int(row.n_imputations), "convergence": str(row.convergence),
        "run_source": "REUSED_VALIDATED", "cache_status": "reused_existing_checkpoint",
        "beta": float(row.beta), "SE": float(row.SE),
        "beta_CI_lower": float(row.beta_CI_lower), "beta_CI_upper": float(row.beta_CI_upper),
        "P_value": float(row.P_value), "within_variance": float(row.within_variance),
        "between_imputation_variance": float(row.between_imputation_variance),
        "fraction_missing_information": float(row.fraction_missing_information),
        "monte_carlo_error": float(row.monte_carlo_error), "n_imputations": int(row.n_imputations),
        "interaction_percent": float(row.interaction_percent),
        "CI_percent_lower": float(row.CI_percent_lower), "CI_percent_upper": float(row.CI_percent_upper),
    }


def audit_stage(config: dict) -> dict:
    out_root = Path(config["output_root"])
    write_input_manifest(config, "before")
    data = load_prepared_panel(config)
    raw_reconciliation, raw_checks = reconcile_raw_mortality(config, data)
    raw_reconciliation.to_csv(out_root / "01_input_audit/raw_mortality_reconciliation.csv", index=False)
    sampler = enumerable_test()
    draws, integrity, draw_meta = generate_or_load_full_b1(config, data)
    existing = np.load(Path(config["project_root"]) / config["inputs"]["existing_copd_B1_draws"])
    copd_equal = bool(np.array_equal(draws[:, existing["row_ids"].astype(int)], existing["draws"]))
    s_joint = freeze_samples(config, data)
    common, lst, reuse_audit = reuse_existing(config, s_joint)
    checks = raw_checks + [
        {"check_id": "panel_rows", "observed": len(data), "expected": 26880, "passed": len(data) == 26880},
        {"check_id": "county_year_outcome_keys_unique", "observed": int(data.duplicated(["county_fips", "year", "cause_id"]).sum()), "expected": 0, "passed": not data.duplicated(["county_fips", "year", "cause_id"]).any()},
        {"check_id": "seven_outcomes", "observed": data.cause_id.nunique(), "expected": 7, "passed": data.cause_id.nunique() == 7},
        {"check_id": "public_zero_distinct_from_suppressed", "observed": int((~data.death_suppressed & data.deaths.eq(0)).sum()), "expected": ">0 and separate status", "passed": int((~data.death_suppressed & data.deaths.eq(0)).sum()) > 0 and not (data.death_suppressed & data.deaths.eq(0)).any()},
        {"check_id": "all_imputation_integrity_rows_pass", "observed": int(integrity[["public_counts_unchanged_all_30", "suppressed_integer_all_30", "suppressed_bounds_1_9_all_30", "exact_state_year_totals_all_30", "county_year_outcome_key_unique"]].all(axis=1).sum()), "expected": 7, "passed": integrity[["public_counts_unchanged_all_30", "suppressed_integer_all_30", "suppressed_bounds_1_9_all_30", "exact_state_year_totals_all_30", "county_year_outcome_key_unique"]].all().all()},
        {"check_id": "existing_COPD_B1_exactly_preserved", "observed": copd_equal, "expected": True, "passed": copd_equal},
        {"check_id": sampler["test"], "observed": sampler["maximum_probability_error"], "expected": "<0.01", "passed": sampler["passed"]},
        {"check_id": "S_joint_frozen", "observed": s_joint["sample_id"], "expected": "calculated before new results", "passed": True},
        {"check_id": "reuse_checkpoints_valid", "observed": int(reuse_audit.decision.eq("REUSED_VALIDATED").sum()), "expected": len(reuse_audit), "passed": reuse_audit.decision.eq("REUSED_VALIDATED").all()},
    ]
    pd.DataFrame(checks).to_csv(out_root / "06_qc/data_integrity_checks.csv", index=False)
    reuse_audit.to_csv(out_root / "06_qc/reuse_and_refit_audit.csv", index=False)
    common.to_csv(out_root / "02_reused_results/common_B1_validated.csv", index=False)
    lst.to_csv(out_root / "02_reused_results/LST_day_B1_validated.csv", index=False)
    write_json(out_root / "06_qc/frozen_sample.json", s_joint)
    if not all(x["passed"] for x in checks):
        raise RuntimeError("audit gate failed")
    return {"s_joint": s_joint, "draws": draw_meta, "reused_rows": len(reuse_audit)}


def models_stage(config: dict) -> list[dict]:
    out_root = Path(config["output_root"])
    checks = pd.read_csv(out_root / "06_qc/data_integrity_checks.csv")
    if not bool_series(checks.passed).all():
        raise RuntimeError("model stage blocked by failed input audit")
    jobs = registered_jobs(config)
    status_rows = []
    for job in jobs:
        status_rows.append({
            "model_id": job.model_id, "analysis_block": job.analysis_block,
            "formula": job.formula, "cause_id": job.cause_id,
            "imputation_version": "fixed_EB_B1_1_9",
            "decision": "REFIT_REQUIRED",
            "reason": "no fully verifiable formal B1 artifact; O10 refit also required for exposure-interaction covariance" if job.model_id == "O10_temperature_adjusted_2009_2020" else "formal B1 result absent from validated registry",
            "is_new_model": job.model_id in config["scope"]["new_models"],
        })
    # Reused common and LST result rows are appended to the registry at table stage.
    pd.DataFrame(status_rows).to_csv(out_root / "06_qc/model_registry.csv", index=False)
    max_workers = max(1, min(int(config.get("max_workers", 4)), 4, os.cpu_count() or 1))
    results: list[dict] = []
    failures = []
    effective_config_path = str(Path(config.get("_config_path", DEFAULT_CONFIG)).resolve())
    with ProcessPoolExecutor(max_workers=max_workers, initializer=init_worker,
                             initargs=(effective_config_path,)) as pool:
        future_to_job = {pool.submit(fit_job_worker, asdict(job)): job for job in jobs}
        for future in as_completed(future_to_job):
            job = future_to_job[future]
            try:
                result = future.result()
                results.append(result)
                print(f"[completed] {job.model_id}: {result['interaction_percent']:.6f}%", flush=True)
            except Exception as exc:
                failures.append({"model_id": job.model_id, "error": repr(exc), "traceback": traceback.format_exc()})
                print(f"[failed] {job.model_id}: {exc}", file=sys.stderr, flush=True)
    if failures:
        pd.DataFrame(failures).to_csv(out_root / "logs/model_failures.csv", index=False)
        raise RuntimeError(f"{len(failures)} required model jobs failed")
    write_json(out_root / "03_model_fits/refit_results.json", results)
    return results


def load_refit_results(config: dict) -> pd.DataFrame:
    path = Path(config["output_root"]) / "03_model_fits/refit_results.json"
    if not path.exists():
        records = []
        for p in sorted((Path(config["output_root"]) / "03_model_fits/checkpoints").glob("*.json")):
            x = json.loads(p.read_text())
            if x.get("status") == "completed_and_validated":
                records.append(x)
        return pd.DataFrame(records)
    return pd.DataFrame(json.loads(path.read_text()))


def compute_marginal_effects(config: dict, model_id: str = "O10_temperature_adjusted_2009_2020") -> pd.DataFrame:
    out_root = Path(config["output_root"])
    per = pd.read_csv(out_root / "03_model_fits/per_imputation" / f"{model_id}.csv")
    rows = []
    for ses in [-2.0, -1.0, 0.0, 1.0, 2.0]:
        q = per.exposure_beta + ses * per.interaction_beta
        u = per.exposure_variance + ses * ses * per.interaction_variance + 2 * ses * per.exposure_interaction_covariance
        if (u < -1e-12).any():
            raise RuntimeError(f"negative marginal variance for SES={ses}")
        pool = rubin_pool(q, np.maximum(u, 0))
        pool.update(effect_fields(pool["beta"], pool["beta_CI_lower"], pool["beta_CI_upper"]))
        rows.append({"model_id": model_id, "ses_sd": ses, "interpretation": "mortality-rate change per one fixed smoke IQR at the specified baseline-SES SD", **pool})
    out = pd.DataFrame(rows)
    out.to_csv(out_root / "04_tables/COPD_marginal_associations_B1.csv", index=False)
    return out


def standardize_output_row(row: pd.Series | dict) -> dict:
    x = dict(row)
    return {k: v for k, v in x.items() if k != "fits"}


def tables_stage(config: dict) -> dict:
    root, out_root = Path(config["project_root"]), Path(config["output_root"])
    refit = load_refit_results(config)
    if len(refit) != len(registered_jobs(config)) or not refit.status.eq("completed_and_validated").all():
        raise RuntimeError(f"expected {len(registered_jobs(config))} completed refit jobs, found {len(refit)}")
    common = pd.read_csv(out_root / "02_reused_results/common_B1_validated.csv")
    lst = pd.read_csv(out_root / "02_reused_results/LST_day_B1_validated.csv")
    lst["LST_added"] = bool_series(lst.LST_added)

    common_rows = [result_from_reused(r) for _, r in common.iterrows()]
    relaxed_m3_with = lst.loc[
        lst.QA_rule.eq("relaxed") & lst.model_family.eq("M3") & lst.LST_added
    ].iloc[0]
    common_rows.append(result_from_reused(relaxed_m3_with, "M3L"))
    for mid in ["M3P_joint", "M3PL_joint"]:
        common_rows.append(standardize_output_row(refit.loc[refit.model_id.eq(mid)].iloc[0]))
    common_table = pd.DataFrame(common_rows)
    order = ["M0", "M1", "M2", "M2P", "M3", "M3L", "M3P_joint", "M3PL_joint"]
    common_table["order"] = common_table.model_id.map({x: i for i, x in enumerate(order)})
    common_table = common_table.sort_values("order").drop(columns="order")
    frozen = json.loads((out_root / "06_qc/frozen_sample.json").read_text())
    if not (common_table.n_county_years.eq(frozen["n_county_years"]).all() and common_table.sample_hash.astype(str).eq(frozen["sample_hash"]).all()):
        raise RuntimeError("common model table does not use one identical S_joint key set")
    common_table.to_csv(out_root / "04_tables/common_sample_covariate_results_B1.csv", index=False)
    common_table.loc[common_table.model_id.isin(["M3P_joint", "M3PL_joint"])].to_csv(out_root / "04_tables/joint_adjustment_results_B1.csv", index=False)

    lst_rows = []
    for _, r in lst.sort_values(["QA_rule", "model_family", "LST_added"]).iterrows():
        x = result_from_reused(r, str(r.model_id))
        x.update({"QA_rule": r.QA_rule, "day_or_night": "day", "LST_added": bool(r.LST_added), "LST_definition": r.LST_definition})
        lst_rows.append(x)
    lst_table = pd.DataFrame(lst_rows)
    for _, group in lst_table.groupby(["QA_rule", "adjustment_family"]):
        if len(group) != 2 or group.sample_hash.nunique() != 1 or group.n_county_years.nunique() != 1:
            raise RuntimeError("LST paired result key mismatch")
    lst_table.to_csv(out_root / "04_tables/LST_paired_results_B1.csv", index=False)

    primary_ids = set(config["scope"]["core_registered_models"] + config["scope"]["period_models"])
    primary = refit.loc[refit.model_id.isin(primary_ids)].copy()
    # Add five targeted samples, with full linked to the refitted O10 artifact.
    full = refit.loc[refit.model_id.eq("O10_temperature_adjusted_2009_2020")].copy()
    full.loc[:, "model_id"] = "OMIT_A_full"
    full.loc[:, "analysis_block"] = "targeted_omission"
    primary = pd.concat([primary, full, refit.loc[refit.analysis_block.isin(["targeted_omission", "secondary_outcomes"])]], ignore_index=True)
    hier = pd.read_csv(root / config["inputs"]["hierarchical_B1_results"])
    h = hier.loc[hier.scenario.eq("hierarchical_EB_B1_1_9")].iloc[0]
    primary = pd.concat([primary, pd.DataFrame([{
        "model_id": "O10_hierarchical_EB_B1_method_sensitivity", "analysis_block": "imputation_method_sensitivity",
        "label": "Hierarchical EB 1–9 sensitivity", "cause_id": "copd", "formula": config["formulas"]["M2"],
        "model_family": "negative_binomial", "imputation_version": "hierarchical_EB_B1_1_9",
        "sample_id": "reference_M2_e944bdd3083e646d", "sample_hash": "e944bdd3083e646d",
        "n_county_years": 3072, "n_counties": 256, "n_states": 6,
        "n_imputations": int(h.m), "success_count": int(h.m), "convergence": "reported completed",
        "run_source": "REUSED_VALIDATED_METHOD_SENSITIVITY", "beta": h.beta, "SE": h.SE,
        "beta_CI_lower": h.beta_CI_lower, "beta_CI_upper": h.beta_CI_upper,
        "P_value": np.nan, "within_variance": h.within_variance,
        "between_imputation_variance": h.between_imputation_variance,
        "fraction_missing_information": h.fraction_missing_information,
        "monte_carlo_error": h.monte_carlo_error, "interaction_percent": h.interaction_percent,
        "CI_percent_lower": h.CI_percent_lower, "CI_percent_upper": h.CI_percent_upper,
    }])], ignore_index=True)
    primary = primary.drop(columns=[c for c in ["fits"] if c in primary], errors="ignore")
    primary.to_csv(out_root / "04_tables/primary_B1_results.csv", index=False)

    # Descriptive cross-model changes only: no fabricated cross-model variance.
    comparisons = []
    indexed = common_table.set_index("model_id")
    for a, b, kind in [
        ("M3", "M3P_joint", "add precipitation to M3"),
        ("M3P_joint", "M3PL_joint", "add daytime LST after precipitation"),
        ("M3", "M3L", "add daytime LST to M3"),
    ]:
        ra, rb = indexed.loc[a], indexed.loc[b]
        comparisons.append({
            "comparison": kind, "from_model": a, "to_model": b,
            "same_sample": ra.sample_hash == rb.sample_hash,
            "sample_hash": ra.sample_hash, "n_county_years": ra.n_county_years,
            "beta_from": ra.beta, "beta_to": rb.beta, "beta_change": rb.beta - ra.beta,
            "percent_from": ra.interaction_percent, "percent_to": rb.interaction_percent,
            "percentage_point_change": rb.interaction_percent - ra.interaction_percent,
            "CI_from": f"{ra.CI_percent_lower:.9g}, {ra.CI_percent_upper:.9g}",
            "CI_to": f"{rb.CI_percent_lower:.9g}, {rb.CI_percent_upper:.9g}",
            "difference_inference": "descriptive only; cross-model covariance not estimated",
        })
    # Sample change: O10 full versus M2 on S_joint.
    o10 = refit.loc[refit.model_id.eq("O10_temperature_adjusted_2009_2020")].iloc[0]
    m2 = indexed.loc["M2"]
    comparisons.append({
        "comparison": "sample restriction: O10 original sample to S_joint, no formula change",
        "from_model": "O10_temperature_adjusted_2009_2020", "to_model": "M2",
        "same_sample": False, "sample_hash": f"{o10.sample_hash} -> {m2.sample_hash}",
        "n_county_years": f"{o10.n_county_years} -> {m2.n_county_years}",
        "beta_from": o10.beta, "beta_to": m2.beta, "beta_change": m2.beta - o10.beta,
        "percent_from": o10.interaction_percent, "percent_to": m2.interaction_percent,
        "percentage_point_change": m2.interaction_percent - o10.interaction_percent,
        "CI_from": f"{o10.CI_percent_lower:.9g}, {o10.CI_percent_upper:.9g}",
        "CI_to": f"{m2.CI_percent_lower:.9g}, {m2.CI_percent_upper:.9g}",
        "difference_inference": "descriptive sample-change comparison only",
    })
    comparisons_df = pd.DataFrame(comparisons)
    comparisons_df.to_csv(out_root / "04_tables/model_change_comparisons.csv", index=False)
    marginal = compute_marginal_effects(config)

    # Old 0--9 versus B1 matches are all read-only reuse; no new B0 fits.
    old = pd.read_csv(root / config["inputs"]["old_pooled_models"])
    job_terms = {j.model_id: j.interaction_term for j in registered_jobs(config)}
    old_rows = []
    for _, r in primary.loc[primary.imputation_version.eq("fixed_EB_B1_1_9")].iterrows():
        old_id = r.model_id
        mapped_id = old_id
        mapped_term = job_terms.get(old_id, TERM)
        if old_id == "OMIT_A_full":
            mapped_id = "O10_temperature_adjusted_2009_2020"
        elif old_id == "OMIT_B_exclude_2020":
            mapped_id = "Y2020_leave_out"
        elif old_id == "OMIT_C_exclude_CA":
            mapped_id = "LCA_leave_out"
        elif old_id in ["OMIT_D_exclude_2020_and_CA", "OMIT_E_exclude_CA_x_2020_only"]:
            continue
        candidates = old.loc[old.model_id.eq(mapped_id) & old.term.eq(mapped_term)]
        if len(candidates) == 1:
            b = candidates.iloc[0]
            old_rows.append({"analysis_block": r.analysis_block, "model_id": old_id, "B0_beta": b.estimate, "B1_beta": r.beta, "absolute_beta_change": r.beta - b.estimate, "B0_percent": b.percent_change, "B1_percent": r.interaction_percent, "percentage_point_change": r.interaction_percent - b.percent_change, "B0_CI_lower": b.percent_change_ci_low, "B0_CI_upper": b.percent_change_ci_high, "B1_CI_lower": r.CI_percent_lower, "B1_CI_upper": r.CI_percent_upper, "comparison_status": "historical stress-test comparison; not equal plausibility"})
    omission_old = pd.read_csv(root / config["inputs"]["old_targeted_omission"])
    omission_map = {
        "D_exclude_2020_and_CA": "OMIT_D_exclude_2020_and_CA",
        "E_exclude_CA_2020_only": "OMIT_E_exclude_CA_x_2020_only",
    }
    for source_id, target_id in omission_map.items():
        b = omission_old.loc[omission_old.scenario.eq(source_id)].iloc[0]
        r = primary.loc[primary.model_id.eq(target_id)].iloc[0]
        old_rows.append({"analysis_block": "targeted_omission", "model_id": target_id, "B0_beta": b.beta_interaction, "B1_beta": r.beta, "absolute_beta_change": r.beta - b.beta_interaction, "B0_percent": b.interaction_percent, "B1_percent": r.interaction_percent, "percentage_point_change": r.interaction_percent - b.interaction_percent, "B0_CI_lower": b.CI_lower, "B0_CI_upper": b.CI_upper, "B1_CI_lower": r.CI_percent_lower, "B1_CI_upper": r.CI_percent_upper, "comparison_status": "historical stress-test comparison; not equal plausibility"})
    old_common = pd.read_csv(root / config["inputs"]["existing_common_results"])
    for mid in ["M0", "M1", "M2", "M2P", "M3"]:
        b = old_common.loc[old_common.imputation_scenario.eq("fixed_EB_B0_0_9") & old_common.model_family.eq(mid)].iloc[0]
        r = indexed.loc[mid]
        old_rows.append({"analysis_block": "common_covariate", "model_id": mid, "B0_beta": b.beta, "B1_beta": r.beta, "absolute_beta_change": r.beta - b.beta, "B0_percent": b.interaction_percent, "B1_percent": r.interaction_percent, "percentage_point_change": r.interaction_percent - b.interaction_percent, "B0_CI_lower": b.CI_percent_lower, "B0_CI_upper": b.CI_percent_upper, "B1_CI_lower": r.CI_percent_lower, "B1_CI_upper": r.CI_percent_upper, "comparison_status": "historical stress-test comparison; not equal plausibility"})
    old_lst = pd.read_csv(root / config["inputs"]["existing_LST_results"])
    old_lst["LST_added"] = bool_series(old_lst.LST_added)
    for _, r in lst_table.iterrows():
        b = old_lst.loc[
            old_lst.imputation_scenario.eq("fixed_EB_B0_0_9")
            & old_lst.QA_rule.eq(r.QA_rule)
            & old_lst.day_or_night.eq("day")
            & old_lst.model_family.eq(r.adjustment_family)
            & bool_series(old_lst.LST_added).eq(bool(r.LST_added))
        ].iloc[0]
        old_rows.append({"analysis_block": "LST_paired", "model_id": r.model_id, "QA_rule": r.QA_rule, "LST_added": r.LST_added, "B0_beta": b.beta, "B1_beta": r.beta, "absolute_beta_change": r.beta - b.beta, "B0_percent": b.interaction_percent, "B1_percent": r.interaction_percent, "percentage_point_change": r.interaction_percent - b.interaction_percent, "B0_CI_lower": b.CI_percent_lower, "B0_CI_upper": b.CI_percent_upper, "B1_CI_lower": r.CI_percent_lower, "B1_CI_upper": r.CI_percent_upper, "comparison_status": "historical stress-test comparison; identical QA/sample keys"})
    pd.DataFrame(old_rows).to_csv(out_root / "04_tables/old_vs_B1_results.csv", index=False)

    # Complete registry and reuse/refit audit.
    registry = pd.DataFrame([{
        "model_id": j.model_id, "analysis_block": j.analysis_block,
        "formula": j.formula, "cause_id": j.cause_id,
        "imputation_version": "fixed_EB_B1_1_9",
        "decision": "REFIT_COMPLETED_VALIDATED",
        "reason": "30/30 B1 fits, full signature and rank validated",
        "is_new_model": j.model_id in config["scope"]["new_models"],
    } for j in registered_jobs(config)])
    reused_audit = pd.read_csv(out_root / "06_qc/reuse_and_refit_audit.csv")
    reused_registry = pd.DataFrame({
        "model_id": reused_audit.registry_item, "analysis_block": "reused_common_or_LST_pair",
        "formula": "see validated source checkpoint", "cause_id": "copd",
        "imputation_version": "fixed_EB_B1_1_9", "decision": reused_audit.decision,
        "reason": reused_audit.reason, "is_new_model": False,
    })
    registry = pd.concat([registry, reused_registry], ignore_index=True)
    registry.to_csv(out_root / "06_qc/model_registry.csv", index=False)
    refit_audit = pd.DataFrame([{
        "registry_item": r.model_id, "decision": "REFIT_COMPLETED_VALIDATED",
        "reason": "30/30 fits; full B1 input, sample, formula, rank, clustered variance and Rubin pooling recorded",
        "source": str(out_root / "03_model_fits/checkpoints" / f"{r.model_id}.json"),
        "sample_hash": r.sample_hash, "n_county_years": r.n_county_years,
    } for _, r in refit.iterrows()])
    existing_reuse = pd.read_csv(out_root / "06_qc/reuse_and_refit_audit.csv")
    existing_reuse = existing_reuse.loc[existing_reuse.decision.eq("REUSED_VALIDATED")].drop_duplicates("registry_item")
    pd.concat([existing_reuse, refit_audit], ignore_index=True).to_csv(out_root / "06_qc/reuse_and_refit_audit.csv", index=False)
    return {"primary_rows": len(primary), "common_rows": len(common_table), "LST_rows": len(lst_table), "marginal_rows": len(marginal)}


def figure_forest(data: pd.DataFrame, label_col: str, path_stub: Path, title: str,
                  group_col: str | None = None) -> None:
    d = data.copy().reset_index(drop=True)
    y = np.arange(len(d))[::-1]
    colors = ["#D55E00" if (group_col is None or str(v).lower() in ["relaxed", "joint"]) else "#4D4D4D" for v in (d[group_col] if group_col else [""] * len(d))]
    fig_h = max(3.4, 0.42 * len(d) + 1.4)
    fig, ax = plt.subplots(figsize=(7.2, fig_h))
    for i, (_, r) in enumerate(d.iterrows()):
        ax.errorbar(r.interaction_percent, y[i], xerr=[[r.interaction_percent-r.CI_percent_lower], [r.CI_percent_upper-r.interaction_percent]], fmt="o", color=colors[i], ecolor=colors[i], capsize=2, markersize=4, linewidth=1)
    ax.axvline(0, color="#777777", linewidth=0.8)
    ax.set_yticks(y, d[label_col])
    ax.set_xlabel("Smoke × baseline SES interaction (%)")
    ax.set_title(title, loc="left", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)
    fig.tight_layout()
    for suffix in ["png", "pdf", "svg"]:
        fig.savefig(path_stub.with_suffix("." + suffix), dpi=300 if suffix == "png" else None, bbox_inches="tight")
    plt.close(fig)


def figures_stage(config: dict) -> None:
    out_root = Path(config["output_root"])
    common = pd.read_csv(out_root / "04_tables/common_sample_covariate_results_B1.csv")
    common_labels = {
        "M0": "M0 | smoke × SES",
        "M1": "M1 | + age ≥65, density",
        "M2": "M2 | + drought, air temperature",
        "M2P": "M2P | M2 + precipitation",
        "M3": "M3 | M2 + background PM₂.₅, ozone",
        "M3L": "M3L | M3 + daytime LST",
        "M3P_joint": "M3P_joint | M3 + precipitation",
        "M3PL_joint": "M3PL_joint | M3 + precipitation + LST",
    }
    common["display"] = common.model_id.map(common_labels)
    common["branch"] = np.where(common.model_id.isin(["M3P_joint", "M3PL_joint"]), "joint", "base")
    figure_forest(common, "display", out_root / "05_figures/Covariate_joint_adjustment_B1", "B1 common-sample covariate adjustment", "branch")
    lst = pd.read_csv(out_root / "04_tables/LST_paired_results_B1.csv")
    lst["display"] = (
        lst.QA_rule.str.title() + " | " + lst.adjustment_family.astype(str)
        + " | " + np.where(bool_series(lst.LST_added), "+ daytime LST", "no LST")
    )
    figure_forest(lst.sort_values(["QA_rule", "adjustment_family", "LST_added"]), "display", out_root / "05_figures/LST_QA_paired_B1", "B1 paired daytime-LST adjustment", "QA_rule")


def reports_stage(config: dict) -> None:
    out_root = Path(config["output_root"])
    primary = pd.read_csv(out_root / "04_tables/primary_B1_results.csv")
    common = pd.read_csv(out_root / "04_tables/common_sample_covariate_results_B1.csv")
    lst = pd.read_csv(out_root / "04_tables/LST_paired_results_B1.csv")
    changes = pd.read_csv(out_root / "04_tables/model_change_comparisons.csv")
    integrity = pd.read_csv(out_root / "01_input_audit/imputation_integrity_check.csv")
    audit = pd.read_csv(out_root / "06_qc/reuse_and_refit_audit.csv")
    sample = json.loads((out_root / "06_qc/frozen_sample.json").read_text())
    o10 = primary.loc[primary.model_id.eq("O10_temperature_adjusted_2009_2020")].iloc[0]
    m3 = common.set_index("model_id").loc["M3"]
    m3p = common.set_index("model_id").loc["M3P_joint"]
    m3pl = common.set_index("model_id").loc["M3PL_joint"]
    reused = int(audit.decision.eq("REUSED_VALIDATED").sum())
    refit = int(audit.decision.eq("REFIT_COMPLETED_VALIDATED").sum())
    new = 2
    lines = [
        "# AFIRE B1统一与共同样本联合调整：最终实验报告", "",
        "## 执行结论", "",
        f"本轮已将任务范围内的正式死亡模型统一到fixed empirical Bayes 1–9主版本。完整七结局插补面板通过公开计数不变、Suppressed为1–9整数、逐份精确恢复州—年—结局总量和键唯一检查（{len(integrity)}/7个结局通过）。",
        f"COPD O10参考模型为 {o10.interaction_percent:.4f}%（95% CI {o10.CI_percent_lower:.4f}%至{o10.CI_percent_upper:.4f}%；SE={o10.SE:.6f}；30/30）。这是每1个固定烟霾IQR、每1 SD基线社会经济劣势的死亡率比之比百分比变化。",
        "", "## 复用与补跑", "",
        f"- 经公式、具体样本键、B1输入哈希、30份估计、设计秩和收敛核验后，复用{reused}个既有模型结果条目。",
        f"- 补跑并通过{refit}个正式模型任务，其中新增模型仅{new}个（M3P_joint、M3PL_joint）；其余是原注册结果的B1补齐或为边际协方差所需的O10刷新。",
        "- 本轮冻结清单内没有BLOCKED或未完成模型；未列入清单的疾病、QA组合、时段和交互不属于本轮缺失结果。",
        "- 0–9模型没有新拟合，只在已有完全匹配结果存在时作为历史宽边界压力测试对照。",
        "", "## S_joint与联合调整", "",
        f"S_joint在查看新模型结果前冻结：{sample['n_county_years']}个county-year、{sample['n_counties']}县、{sample['n_states']}州；样本哈希 `{sample['sample_hash']}`。相对于原M3共同样本，联合变量和宽松昼间LST没有再排除记录（额外排除{sample['n_excluded_from_original_common_by_joint_requirements']}行）。",
        f"- M3（背景污染，不含降水/LST）：{m3.interaction_percent:.4f}%（95% CI {m3.CI_percent_lower:.4f}%至{m3.CI_percent_upper:.4f}%）。",
        f"- M3P_joint（M3+降水）：{m3p.interaction_percent:.4f}%（95% CI {m3p.CI_percent_lower:.4f}%至{m3p.CI_percent_upper:.4f}%）。",
        f"- M3PL_joint（M3+降水+昼间LST）：{m3pl.interaction_percent:.4f}%（95% CI {m3pl.CI_percent_lower:.4f}%至{m3pl.CI_percent_upper:.4f}%）。",
        f"M3→M3P_joint变化{m3p.interaction_percent-m3.interaction_percent:+.4f}个百分点；M3P_joint→M3PL_joint变化{m3pl.interaction_percent-m3p.interaction_percent:+.4f}个百分点。三者使用同一county-year键，因此这里的差异来自协变量设定而非样本变化；差异仅作描述，不构造无跨模型协方差支持的差值检验。",
        "", "## LST质量与样本分支", "",
    ]
    for (qa, family), g in lst.groupby(["QA_rule", "adjustment_family"]):
        a = g.loc[~bool_series(g.LST_added)].iloc[0]
        b = g.loc[bool_series(g.LST_added)].iloc[0]
        lines.append(f"- {qa}昼间/{family}：{int(a.n_county_years)}行、{int(a.n_counties)}县、{int(a.n_states)}州；加入LST前{a.interaction_percent:.4f}%（{a.CI_percent_lower:.4f}, {a.CI_percent_upper:.4f}），加入后{b.interaction_percent:.4f}%（{b.CI_percent_lower:.4f}, {b.CI_percent_upper:.4f}），同键变化{b.interaction_percent-a.interaction_percent:+.4f}个百分点。")
    lines += [
        "", "## 变化来源", "",
        "S_joint上的M3、M3P_joint、M3PL_joint完全同键，所以联合调整比较不受样本切换混淆。O10原样本与S_joint M2的单独比较记录的是样本限制效应；LST配对表逐分支核实了不含/含LST模型键完全一致。严格QA与宽松QA跨分支差异不能解释为LST调整效应。",
        "", "## 正文和图表更新范围", "",
        "需把任务范围内仍引用fixed EB 0–9的COPD O10、七结局、2020/California既定删除、分期、共同样本M0–M3/M2P、昼间LST配对以及COPD边际关联替换为本目录B1表。州级暴露、Gini和不依赖死亡插补的数据不更新。新联合模型属于补充稳健性分析，不替代O10。",
        "", "## 结论边界", "",
        "数据支持：在固定1–9插补、固定尺度和同一S_joint内，可描述联合控制降水、背景污染及县级火季昼间LST后smoke×SES关联估计的变化；严格/宽松昼间LST配对可作为质量与样本敏感性并列报告。",
        "数据不支持：把交互写成SES本身的主效应；把协变量调整解释为中介或机制贡献；宣称已经消除所有混杂；按P值选择QA或插补方案；把0–9与1–9当作同等合理主方案。",
        "", "## 证据说明", "",
        "本轮关于该CDC批次1–9规则采用任务明确提供并冻结的核查结论；项目内先前元数据不足的历史报告仍原样保留。本轮没有修改、覆盖或重新标记任何旧插补文件。",
    ]
    (out_root / "07_report/FINAL_EXPERIMENT_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    notes = [
        "# MANUSCRIPT UPDATE NOTES（不覆盖论文）", "",
        "## 中文结果段落候选", "",
        f"在fixed empirical Bayes 1–9主插补版本中，COPD温度调整参考模型的烟霾PM2.5×基线社会经济劣势交互为{o10.interaction_percent:.3f}%（95% CI {o10.CI_percent_lower:.3f}%–{o10.CI_percent_upper:.3f}%；30次插补）。该量表示每增加1个固定烟霾IQR时，每增加1 SD基线社会经济劣势所对应的死亡率比之比百分比变化，而非社会经济劣势的独立主效应。",
        "",
        f"在预先冻结的共同样本（{sample['n_county_years']}个县—年、{sample['n_counties']}县、{sample['n_states']}州）中，M3、M3+降水和M3+降水+昼间LST的交互估计分别为{m3.interaction_percent:.3f}%（95% CI {m3.CI_percent_lower:.3f}%–{m3.CI_percent_upper:.3f}%）、{m3p.interaction_percent:.3f}%（{m3p.CI_percent_lower:.3f}%–{m3p.CI_percent_upper:.3f}%）和{m3pl.interaction_percent:.3f}%（{m3pl.CI_percent_lower:.3f}%–{m3pl.CI_percent_upper:.3f}%）。这些模型使用相同县—年键，因此估计变化可归于调整集合差异，但不能解释为因果机制或被“解释”的不平等比例。",
        "", "## English results paragraph candidate", "",
        f"Under the fixed empirical-Bayes 1–9 primary imputation, the smoke-PM2.5-by-baseline-socioeconomic-disadvantage interaction in the temperature-adjusted COPD reference model was {o10.interaction_percent:.3f}% (95% CI, {o10.CI_percent_lower:.3f}% to {o10.CI_percent_upper:.3f}%; 30 imputations). This contrast is the percent change in the mortality rate-ratio per one fixed smoke IQR and one SD of baseline disadvantage; it is not the main effect of socioeconomic disadvantage.",
        "",
        f"In the prespecified common sample ({sample['n_county_years']} county-years; {sample['n_counties']} counties; {sample['n_states']} states), the interaction estimates were {m3.interaction_percent:.3f}% ({m3.CI_percent_lower:.3f}% to {m3.CI_percent_upper:.3f}%) for M3, {m3p.interaction_percent:.3f}% ({m3p.CI_percent_lower:.3f}% to {m3p.CI_percent_upper:.3f}%) after additionally adjusting for precipitation, and {m3pl.interaction_percent:.3f}% ({m3pl.CI_percent_lower:.3f}% to {m3pl.CI_percent_upper:.3f}%) after additionally adjusting for daytime land-surface temperature. Because the county-year keys were identical, these are adjustment-set comparisons, not sample-composition comparisons; they should not be interpreted as mediation or mechanistic decompositions.",
    ]
    (out_root / "07_report/MANUSCRIPT_UPDATE_NOTES.md").write_text("\n".join(notes) + "\n", encoding="utf-8")


def finalize(config: dict, started: float) -> dict:
    out_root = Path(config["output_root"])
    manifest = write_input_manifest(config, "after")
    if not manifest.hash_unchanged.fillna(False).all():
        raise RuntimeError("one or more authoritative input hashes changed during execution")
    # Independent delivery-level checks, separate from per-model checkpoints.
    registry = pd.read_csv(out_root / "06_qc/model_registry.csv")
    audit = pd.read_csv(out_root / "06_qc/reuse_and_refit_audit.csv")
    per_files = list((out_root / "03_model_fits/per_imputation").glob("*.csv"))
    checkpoints = list((out_root / "03_model_fits/checkpoints").glob("*.json"))
    common = pd.read_csv(out_root / "04_tables/common_sample_covariate_results_B1.csv")
    lst = pd.read_csv(out_root / "04_tables/LST_paired_results_B1.csv")
    integrity = pd.read_csv(out_root / "01_input_audit/imputation_integrity_check.csv")
    lst_pair_ok = True
    for _, group in lst.groupby(["QA_rule", "adjustment_family"]):
        lst_pair_ok = lst_pair_ok and len(group) == 2 and group.sample_hash.nunique() == 1 and group.n_county_years.nunique() == 1 and set(bool_series(group.LST_added)) == {False, True}
    final_checks = pd.DataFrame([
        {"check_id": "registry_unique_and_complete", "observed": f"{len(registry)} rows/{registry.model_id.nunique()} unique", "expected": "38 rows/38 unique", "passed": len(registry) == 38 and registry.model_id.nunique() == 38},
        {"check_id": "reuse_refit_audit_complete", "observed": len(audit), "expected": 38, "passed": len(audit) == 38},
        {"check_id": "refit_per_imputation_files", "observed": len(per_files), "expected": 25, "passed": len(per_files) == 25},
        {"check_id": "refit_per_imputation_rows", "observed": sum(len(pd.read_csv(p)) for p in per_files), "expected": 750, "passed": sum(len(pd.read_csv(p)) for p in per_files) == 750},
        {"check_id": "validated_refit_checkpoints", "observed": len(checkpoints), "expected": 25, "passed": len(checkpoints) == 25 and all(json.loads(p.read_text()).get("status") == "completed_and_validated" and len(json.loads(p.read_text()).get("fits", [])) == 30 for p in checkpoints)},
        {"check_id": "eight_common_models_identical_keys", "observed": f"{len(common)} rows/{common.sample_hash.nunique()} hash/{common.n_county_years.nunique()} n", "expected": "8 rows/1 hash/1 n", "passed": len(common) == 8 and common.sample_hash.nunique() == 1 and common.n_county_years.nunique() == 1},
        {"check_id": "four_LST_pairs_identical_within_pair", "observed": len(lst), "expected": "8 rows in 4 valid pairs", "passed": len(lst) == 8 and lst_pair_ok},
        {"check_id": "seven_outcome_imputation_integrity", "observed": len(integrity), "expected": 7, "passed": len(integrity) == 7 and integrity.public_counts_unchanged_all_30.all() and integrity.suppressed_bounds_1_9_all_30.all() and integrity.exact_state_year_totals_all_30.all()},
        {"check_id": "authoritative_input_hashes_unchanged", "observed": int(manifest.hash_unchanged.sum()), "expected": len(manifest), "passed": manifest.hash_unchanged.fillna(False).all()},
    ])
    final_checks.to_csv(out_root / "06_qc/final_validation.csv", index=False)
    if not final_checks.passed.all():
        raise RuntimeError("final independent validation failed")

    required = [
        "00_protocol/EXPERIMENT_PROTOCOL.md", "01_input_audit/input_manifest.csv",
        "01_input_audit/imputation_integrity_check.csv", "04_tables/primary_B1_results.csv",
        "04_tables/common_sample_covariate_results_B1.csv", "04_tables/joint_adjustment_results_B1.csv",
        "04_tables/LST_paired_results_B1.csv", "04_tables/model_change_comparisons.csv",
        "04_tables/old_vs_B1_results.csv", "06_qc/sample_membership.csv",
        "06_qc/sample_exclusions.csv", "06_qc/model_registry.csv",
        "06_qc/reuse_and_refit_audit.csv", "06_qc/data_integrity_checks.csv",
        "06_qc/final_validation.csv",
        "07_report/FINAL_EXPERIMENT_REPORT.md", "07_report/MANUSCRIPT_UPDATE_NOTES.md",
        "05_figures/Covariate_joint_adjustment_B1.pdf", "05_figures/Covariate_joint_adjustment_B1.svg",
        "05_figures/Covariate_joint_adjustment_B1.png", "05_figures/LST_QA_paired_B1.pdf",
        "05_figures/LST_QA_paired_B1.svg", "05_figures/LST_QA_paired_B1.png",
    ]
    missing = [x for x in required if not (out_root / x).exists()]
    if missing:
        raise RuntimeError(f"required outputs missing: {missing}")
    refit_results = load_refit_results(config)
    final = {
        "analysis_id": config["analysis_id"], "protocol_version": config["protocol_version"],
        "status": "completed_and_validated", "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_seconds_current_invocation": time.time() - started,
        "summed_refit_elapsed_seconds": float(pd.to_numeric(refit_results.elapsed_seconds, errors="coerce").sum()),
        "runtime_note": "Summed model time is the sum across concurrently executed model jobs, not wall-clock time.",
        "paper_modified": False,
        "authoritative_inputs_unchanged": True,
        "input_manifest_sha256": sha256(out_root / "01_input_audit/input_manifest.csv"),
        "analysis_code_sha256": sha256(out_root / "run_pipeline.py"),
        "frozen_config_sha256": sha256(out_root / "00_protocol/config.json"),
        "protocol_sha256": sha256(out_root / "00_protocol/EXPERIMENT_PROTOCOL.md"),
        "registered_result_tasks": len(registry),
        "refit_completed": int(registry.decision.eq("REFIT_COMPLETED_VALIDATED").sum()),
        "reused_validated": int(registry.decision.eq("REUSED_VALIDATED").sum()),
        "blocked": int(registry.decision.eq("BLOCKED").sum()),
        "new_models": config["scope"]["new_models"],
        "outputs": {x: sha256(out_root / x) for x in required},
        "known_limits": [
            "1–9 suppression rule is frozen from the batch-specific audit conclusion supplied for this task; prior project metadata-uncertainty reports remain preserved.",
            "Fixed EB allocations are uncertainty reconstructions, not known true suppressed county counts.",
            "Cross-model coefficient changes are descriptive because cross-model covariance was not estimated.",
            "Relaxed daytime LST is a prespecified supplementary branch and is not selected by P value.",
        ],
    }
    write_json(out_root / "run_manifest.json", final)
    return final


def status(config: dict) -> None:
    out_root = Path(config["output_root"])
    checkpoints = list((out_root / "03_model_fits/checkpoints").glob("*.json"))
    states: dict[str, int] = {}
    for p in checkpoints:
        try:
            state = json.loads(p.read_text()).get("status", "unknown")
        except Exception:
            state = "invalid_json"
        states[state] = states.get(state, 0) + 1
    print(json.dumps({"output_root": str(out_root), "checkpoint_status": states,
                      "run_manifest_exists": (out_root / "run_manifest.json").exists()}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--stage", choices=["all", "audit", "models", "tables", "figures", "report", "finalize", "status"], default="all")
    parser.add_argument("--status", action="store_true", help="print resumable checkpoint status and exit")
    parser.add_argument("--resume", action="store_true", help="reuse only signature-matching validated checkpoints")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    config["_config_path"] = str(args.config.resolve())
    started = time.time()
    if args.status or args.stage == "status":
        status(config)
        return
    stages = ["audit", "models", "tables", "figures", "report", "finalize"] if args.stage == "all" else [args.stage]
    print(json.dumps({"project_root": config["project_root"], "output_root": config["output_root"], "stages": stages, "primary_imputation": config["primary_imputation"], "new_models": config["scope"]["new_models"]}, ensure_ascii=False, indent=2), flush=True)
    for stage in stages:
        print(f"== stage: {stage} ==", flush=True)
        if stage == "audit": audit_stage(config)
        elif stage == "models": models_stage(config)
        elif stage == "tables": tables_stage(config)
        elif stage == "figures": figures_stage(config)
        elif stage == "report": reports_stage(config)
        elif stage == "finalize":
            result = finalize(config, started)
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
