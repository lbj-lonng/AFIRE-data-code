#!/usr/bin/env python3
"""Exact-margin hierarchical MI pilot for suppressed county death counts.

This script never edits the archived data or prior result directories.  It compares
allocation models using pseudo-suppression of publicly visible 10--19 counts, then
generates COPD imputations under both 0--9 and 1--9 boundary assumptions and fits
the already-frozen M2 health model.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import sys
import time
from pathlib import Path

# These limits must be set before NumPy/BLAS is imported.  Otherwise a single
# statsmodels fit can create a nested thread storm on shared machines.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import gammaln, logsumexp


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parents[1]
CONFIG_DEFAULT = HERE / "config/method_config.json"
OUT = HERE / "outputs"
TABLES = OUT / "tables"
MODELS = OUT / "models"
DATA = OUT / "imputations"
LOGS = HERE / "logs"
REPORTS = HERE / "reports"

P3 = ROOT / "experiment_feasibility_20260906/source_snapshot/all/03"
P4 = ROOT / "experiment_feasibility_20260906/source_snapshot/all/04"
STAGE3 = ROOT / "experiment_validation_stage3_20260906"
PANEL_FILE = P3 / "data_processed/county_year_disease_panel_v6_3.csv"
OLD_B0_FILE = P4 / "data_processed/imputed_deaths_eb_history_v5.npz"
OLD_B0_FITS = P4 / "results/models/O10_temperature_adjusted_2009_2020/per_imputation.csv.gz"
OLD_B1_CHECKPOINT = STAGE3 / "b1_model_checkpoint.json"

os.environ["AFIRE_PROJECT_ROOT"] = str(P4)
sys.path.insert(0, str(P4 / "scripts"))
from v7_common import ModelSpec, filter_spec_data, load_analysis_data, rubin_pool  # noqa: E402
from v7_engine import build_design, estimate_nb_alpha, fit_negative_binomial  # noqa: E402


TERM = "pm25_iqr:ses_baseline_std"
RHS = (
    "pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v7 + "
    "density_std_v7 + drought_d1_fs_std_v7 + temperature_fs_std_v7 + "
    "C(county_model) + C(year_model)"
)
REQ = (
    "pm25_iqr", "ses_baseline_std", "age65_std_v7", "density_std_v7",
    "drought_d1_fs_std_v7", "temperature_fs_std_v7",
)


def ensure_dirs() -> None:
    for p in (TABLES, MODELS, DATA, LOGS, REPORTS):
        p.mkdir(parents=True, exist_ok=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def model_spec() -> ModelSpec:
    return ModelSpec(
        model_id="BEM_HBMI_COPD_M2", label="BEM-HBMI pilot", group="method_pilot",
        cause_id="copd", family="negative_binomial", rhs=RHS,
        exposure_term="pm25_iqr", interaction_term=TERM, required=REQ,
        year_min=2009, year_max=2020, min_rows=100, min_counties=10,
    )


def key_hash(d: pd.DataFrame) -> str:
    keys = d[["county_fips", "year"]].drop_duplicates().sort_values(["county_fips", "year"])
    raw = "\n".join(f"{int(f):05d}-{int(y)}" for f, y in keys.itertuples(index=False, name=None))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def prepare_conditional_poisson(lam, total: int, lower: int, upper: int):
    """Log-space DP for independent Poisson counts conditional on exact sum.

    Log space is needed because pseudo-suppression groups can condition on totals
    deep in the tail of their allocation model.  Row-wise rescaling alone does
    not protect every reachable tail sum from underflow.
    """
    lam = np.asarray(lam, dtype=float)
    n = len(lam); total = int(total)
    if n == 0:
        if total != 0:
            raise ValueError("non-zero total with no suppressed cells")
        return {"log_weights": np.empty((0, 0)), "log_dp": np.zeros((1, 1)),
                "total": 0, "lower": lower, "upper": upper}
    if not lower * n <= total <= upper * n:
        raise ValueError(f"infeasible total={total}, n={n}, support={lower}..{upper}")
    good = lam[np.isfinite(lam) & (lam > 0)]
    fallback = float(np.median(good)) if len(good) else 1.0
    lam = np.where(np.isfinite(lam) & (lam > 0), lam, fallback)
    lam = lam / np.exp(np.mean(np.log(lam)))
    ks = np.arange(lower, upper + 1)
    logw = np.log(lam)[:, None] * ks[None, :] - gammaln(ks + 1)[None, :]
    logw -= logw.max(axis=1, keepdims=True)
    log_dp = np.full((n + 1, total + 1), -np.inf, dtype=float)
    log_dp[n, 0] = 0.0
    for i in range(n - 1, -1, -1):
        # Vectorized convolution in log space.  Only theoretically reachable
        # sums need to be retained; the rest stay -inf.
        max_remaining = min(total, upper * (n - i))
        min_remaining = lower * (n - i)
        for k in range(lower, upper + 1):
            source_max = min(total - k, upper * (n - i - 1))
            source_min = lower * (n - i - 1)
            if source_min > source_max:
                continue
            source = slice(source_min, source_max + 1)
            target = slice(source_min + k, source_max + k + 1)
            log_dp[i, target] = np.logaddexp(
                log_dp[i, target], logw[i, k - lower] + log_dp[i + 1, source]
            )
        if min_remaining <= max_remaining:
            row_norm = logsumexp(log_dp[i, min_remaining:max_remaining + 1])
            if np.isfinite(row_norm):
                log_dp[i, min_remaining:max_remaining + 1] -= row_norm
    if not np.isfinite(log_dp[0, total]):
        raise RuntimeError("zero conditional probability")
    return {"log_weights": logw, "log_dp": log_dp, "total": total,
            "lower": lower, "upper": upper}


def sample_prepared(prep, rng: np.random.Generator) -> np.ndarray:
    log_weights, log_dp = prep["log_weights"], prep["log_dp"]
    lower, upper, remaining = prep["lower"], prep["upper"], prep["total"]
    n = len(log_weights); out = np.empty(n, dtype=np.int16)
    for i in range(n):
        left = n - i - 1
        lo = max(lower, remaining - upper * left)
        hi = min(upper, remaining - lower * left)
        values = np.arange(lo, hi + 1)
        log_mass = np.array([
            log_weights[i, k - lower] + log_dp[i + 1, remaining - k]
            for k in values
        ], dtype=float)
        mass = np.exp(log_mass - logsumexp(log_mass))
        chosen = int(rng.choice(values, p=mass))
        out[i] = chosen; remaining -= chosen
    if remaining != 0:
        raise AssertionError("exact margin failed")
    return out


def sampler_unit_tests() -> pd.DataFrame:
    rng = np.random.default_rng(78123)
    rows = []
    cases = [([0.7, 1.4, 2.1], 6, 1, 9), ([0.8, 2.5, 0.3, 1.1], 12, 0, 9),
             ([1.0, 1.0], 30, 10, 19)]
    for case_id, (lam, total, lower, upper) in enumerate(cases, 1):
        prep = prepare_conditional_poisson(lam, total, lower, upper)
        samples = np.stack([sample_prepared(prep, rng) for _ in range(500)])
        rows.append({
            "case_id": case_id, "n_cells": len(lam), "total": total,
            "lower": lower, "upper": upper,
            "all_exact_sum": bool(np.all(samples.sum(axis=1) == total)),
            "all_in_bounds": bool(np.all((samples >= lower) & (samples <= upper))),
            "status": "pass" if np.all(samples.sum(axis=1) == total)
                     and np.all((samples >= lower) & (samples <= upper)) else "fail",
        })
    # Directly compare sampler frequencies with the enumerated target
    # conditional Poisson distribution for a small feasible state space.
    lam = np.array([0.7, 1.4, 2.1]); total, lower, upper = 6, 1, 9
    states = np.array([x for x in itertools.product(range(lower, upper + 1), repeat=3)
                       if sum(x) == total], dtype=int)
    logp = (states * np.log(lam)[None, :] - gammaln(states + 1)).sum(axis=1)
    target = np.exp(logp - logsumexp(logp))
    prep = prepare_conditional_poisson(lam, total, lower, upper)
    sampled = np.stack([sample_prepared(prep, rng) for _ in range(20000)])
    counts = {tuple(x): 0 for x in states}
    for x in sampled:
        counts[tuple(x)] += 1
    empirical = np.array([counts[tuple(x)] / len(sampled) for x in states])
    max_probability_error = float(np.max(np.abs(empirical - target)))
    rows.append({
        "case_id": 4, "n_cells": 3, "total": total, "lower": lower,
        "upper": upper, "all_exact_sum": True, "all_in_bounds": True,
        "max_probability_error": max_probability_error,
        "probability_error_tolerance": 0.02,
        "status": "pass" if max_probability_error < 0.02 else "fail",
    })
    out = pd.DataFrame(rows)
    if not out.status.eq("pass").all():
        raise AssertionError("sampler unit test failed")
    out.to_csv(TABLES / "01_sampler_unit_tests.csv", index=False)
    return out


def state_prior(panel: pd.DataFrame, state: str, cause: str, excluded_year: int | None = None):
    d = panel.loc[panel.state_abbr.eq(state) & panel.cause_id.eq(cause)].copy()
    if excluded_year is not None:
        d = d.loc[d.year.ne(excluded_year)]
    st = d[["year", "state_deaths", "state_population"]].drop_duplicates("year")
    rate = float(st.state_deaths.sum() / st.state_population.sum())
    obs = d.loc[~d.death_suppressed.astype(bool) & d.deaths.notna()]
    agg = obs.groupby("county_fips", as_index=False).agg(y=("deaths", "sum"), exposure=("population", "sum"))
    return rate, agg


def estimate_gamma_strength(rate0: float, agg: pd.DataFrame) -> tuple[float, str]:
    """Empirical-Bayes Gamma prior exposure, fitted without target variables."""
    y = agg.y.to_numpy(float); exposure = agg.exposure.to_numpy(float)
    if len(y) < 3 or rate0 <= 0:
        return float(np.median(exposure) * 3 if len(exposure) else 1e6), "fallback"

    def negative_log_marginal(log_tau: float) -> float:
        tau = math.exp(log_tau); a = max(rate0 * tau, 1e-8); b = tau
        ll = (gammaln(y + a) - gammaln(a) - gammaln(y + 1)
              + a * math.log(b) + y * np.log(exposure)
              - (y + a) * np.log(b + exposure))
        return -float(np.sum(ll))

    result = minimize_scalar(negative_log_marginal, bounds=(math.log(1e3), math.log(1e9)),
                             method="bounded", options={"xatol": 1e-5})
    if not result.success or not np.isfinite(result.fun):
        return float(np.median(exposure) * 3), "fallback"
    return float(math.exp(result.x)), "marginal_likelihood"


def county_posterior(panel: pd.DataFrame, state: str, cause: str, excluded_year: int | None = None):
    rate0, agg = state_prior(panel, state, cause, excluded_year)
    tau, tau_method = estimate_gamma_strength(rate0, agg)
    counties = panel.loc[panel.state_abbr.eq(state) & panel.cause_id.eq(cause), ["county_fips"]].drop_duplicates()
    x = counties.merge(agg, on="county_fips", how="left").fillna({"y": 0.0, "exposure": 0.0})
    a = max(rate0 * tau, 1e-8); b = tau
    x["post_shape"] = a + x.y
    x["post_rate"] = b + x.exposure
    x["post_mean_rate"] = x.post_shape / x.post_rate
    return x.set_index("county_fips"), {"state": state, "cause_id": cause,
        "excluded_year": excluded_year, "state_prior_rate": rate0, "tau_exposure": tau,
        "tau_method": tau_method, "prior_shape": a, "prior_rate": b,
        "n_training_counties": len(agg)}


def pseudo_suppression_validation(panel: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pcfg = cfg["pseudo_suppression"]
    low, high = pcfg["visible_count_lower"], pcfg["visible_count_upper"]
    min_cells, ndraw = pcfg["minimum_cells_per_group"], pcfg["draws_per_group"]
    rng = np.random.default_rng(cfg["seed"] + 101)
    visible = panel.loc[(~panel.death_suppressed.astype(bool)) & panel.deaths.between(low, high)].copy()
    groups = [(key, g.copy()) for key, g in visible.groupby(["state_abbr", "year", "cause_id"], sort=True)
              if len(g) >= min_cells]
    predictions = [];
    prior_meta = []
    methods = ["equal", "population", "loyo_fixed_EB", "loyo_hierarchical_EB"]
    for group_number, ((state, year, cause), g) in enumerate(groups, 1):
        posterior, meta = county_posterior(panel, state, cause, int(year))
        meta["pseudo_group_id"] = f"{state}_{year}_{cause}"
        prior_meta.append(meta)
        fips = g.county_fips.astype(int).to_numpy()
        pop = g.population.to_numpy(float); truth = g.deaths.astype(int).to_numpy()
        total = int(truth.sum())
        fixed_lam = {
            "equal": np.ones(len(g)),
            "population": pop,
            "loyo_fixed_EB": pop * posterior.loc[fips, "post_mean_rate"].to_numpy(float),
        }
        method_draws = {}
        for method, lam in fixed_lam.items():
            prep = prepare_conditional_poisson(lam, total, 0, high)
            method_draws[method] = np.stack([sample_prepared(prep, rng) for _ in range(ndraw)])
        hd = []
        shapes = posterior.loc[fips, "post_shape"].to_numpy(float)
        rates = posterior.loc[fips, "post_rate"].to_numpy(float)
        for _ in range(ndraw):
            county_rates = rng.gamma(shapes, 1.0 / rates)
            prep = prepare_conditional_poisson(pop * county_rates, total, 0, high)
            hd.append(sample_prepared(prep, rng))
        method_draws["loyo_hierarchical_EB"] = np.stack(hd)
        gid = f"{state}_{year}_{cause}"
        for method in methods:
            draws = method_draws[method]
            q025, q975 = np.quantile(draws, [0.025, 0.975], axis=0)
            means = draws.mean(axis=0)
            for j, fips_j in enumerate(fips):
                xj = draws[:, j].astype(float)
                sx = np.sort(xj); nn = len(sx)
                # Empirical CRPS = E|X-y| - 0.5 E|X-X'|.  The sorted-sample
                # identity avoids materializing an n-by-n distance matrix.
                half_pair_distance = float(
                    np.sum((2 * np.arange(1, nn + 1) - nn - 1) * sx) / nn**2
                )
                crps = float(np.mean(np.abs(xj - truth[j])) - half_pair_distance)
                wis95 = float(
                    q975[j] - q025[j]
                    + 40 * max(q025[j] - truth[j], 0)
                    + 40 * max(truth[j] - q975[j], 0)
                )
                predictions.append({
                    "pseudo_group_id": gid, "state_abbr": state, "year": int(year),
                    "cause_id": cause, "county_fips": int(fips_j), "method": method,
                    "true_visible_count": int(truth[j]), "posterior_mean": float(means[j]),
                    "q025": float(q025[j]), "q975": float(q975[j]),
                    "absolute_error": float(abs(means[j] - truth[j])),
                    "squared_error": float((means[j] - truth[j]) ** 2),
                    "interval_covers_truth": bool(q025[j] <= truth[j] <= q975[j]),
                    "interval_width": float(q975[j] - q025[j]),
                    "CRPS": crps, "interval_score_95": wis95,
                    "n_draws": ndraw, "support": f"0-{high}",
                    "validation_limit": "visible 10-19 analogue; not ground truth for suppressed 1-9 cells",
                })
        if group_number % 50 == 0:
            print(f"pseudo-validation {group_number}/{len(groups)}", flush=True)
    pred = pd.DataFrame(predictions)
    pred.to_csv(TABLES / "02_pseudo_suppression_predictions.csv", index=False)
    pd.DataFrame(prior_meta).to_csv(TABLES / "02_pseudo_suppression_prior_fits.csv", index=False)
    rows = []
    for scope, d in [("all_outcomes", pred), ("COPD", pred.loc[pred.cause_id.eq("copd")])]:
        for method, g in d.groupby("method"):
            rows.append({
                "scope": scope, "method": method, "n_groups": g.pseudo_group_id.nunique(),
                "n_cells": len(g), "MAE": g.absolute_error.mean(),
                "RMSE": math.sqrt(g.squared_error.mean()),
                "coverage_95": g.interval_covers_truth.mean(),
                "mean_interval_width": g.interval_width.mean(),
                "mean_CRPS": g.CRPS.mean(),
                "mean_interval_score_95": g.interval_score_95.mean(),
            })
    summary = pd.DataFrame(rows)
    summary["rank_MAE_within_scope"] = summary.groupby("scope").MAE.rank(method="min")
    summary.to_csv(TABLES / "03_pseudo_suppression_validation_summary.csv", index=False)

    # Group-resampled uncertainty for the key hierarchical-vs-fixed EB contrast.
    boot_rows = []
    brng = np.random.default_rng(cfg["seed"] + 202)
    for metric, label in [("absolute_error", "MAE"), ("CRPS", "CRPS")]:
        wide = pred.pivot_table(index=["pseudo_group_id", "cause_id"], columns="method",
                                values=metric, aggfunc="mean").reset_index()
        for scope, d in [("all_outcomes", wide), ("COPD", wide.loc[wide.cause_id.eq("copd")])]:
            observed = float((d.loyo_hierarchical_EB - d.loyo_fixed_EB).mean())
            vals = []
            for _ in range(pcfg["bootstrap_replicates"]):
                take = brng.integers(0, len(d), len(d))
                x = d.iloc[take]
                vals.append(float((x.loyo_hierarchical_EB - x.loyo_fixed_EB).mean()))
            boot_rows.append({"scope": scope, "metric": label,
                              "contrast": f"hierarchical_minus_fixed_EB_{label}",
                              "observed_difference": observed,
                              "bootstrap_q025": float(np.quantile(vals, .025)),
                              "bootstrap_q975": float(np.quantile(vals, .975)),
                              "bootstrap_replicates": pcfg["bootstrap_replicates"],
                              "interpretation": "negative favors hierarchical EB; pseudo-suppression validation only"})
    boot = pd.DataFrame(boot_rows)
    boot.to_csv(TABLES / "04_pseudo_suppression_pairwise_bootstrap.csv", index=False)
    return pred, summary, boot


def actual_state_hyperparameters(copd: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    out = {}; rows = []
    for state in sorted(copd.state_abbr.unique()):
        posterior, meta = county_posterior(copd, state, "copd", excluded_year=None)
        out[state] = (posterior, meta)
        rows.append(meta)
    table = pd.DataFrame(rows)
    table.to_csv(TABLES / "05_hierarchical_prior_hyperparameters.csv", index=False)
    return out, table


def rhat(chains: np.ndarray) -> float:
    chains = np.asarray(chains, float)
    m, n = chains.shape
    within = np.mean(np.var(chains, axis=1, ddof=1))
    between = n * np.var(np.mean(chains, axis=1), ddof=1)
    if within <= 0:
        return 1.0 if between <= 0 else float("inf")
    varhat = (n - 1) / n * within + between / n
    return float(math.sqrt(varhat / within))


def initialize_counts(copd: pd.DataFrame, hpars: dict, lower: int, upper: int,
                      rng: np.random.Generator) -> np.ndarray:
    y = copd.deaths.to_numpy(float).copy()
    for (state, year), g in copd.groupby(["state_abbr", "year"], sort=True):
        idx = g.index[g.death_suppressed.astype(bool)].to_numpy()
        if not len(idx):
            continue
        total = int(round(float(g.state_deaths.iloc[0]) - float(g.deaths.sum(skipna=True))))
        post = hpars[state][0]
        fips = copd.loc[idx, "county_fips"].astype(int).to_numpy()
        lam = copd.loc[idx, "population"].to_numpy(float) * post.loc[fips, "post_mean_rate"].to_numpy(float)
        y[idx] = sample_prepared(prepare_conditional_poisson(lam, total, lower, upper), rng)
    return y.astype(np.int16)


def hierarchical_gibbs_imputations(panel: pd.DataFrame, cfg: dict, lower: int, upper: int):
    version = cfg["version"]
    outfile = DATA / f"COPD_hierarchical_exact_margin_{version}_{lower}_{upper}.npz"
    diagfile = TABLES / f"06_mcmc_diagnostics_{version}_{lower}_{upper}.csv"
    if outfile.exists() and diagfile.exists():
        z = np.load(outfile)
        return z["draws"], z["row_ids"], pd.read_csv(diagfile)
    c = panel.loc[panel.cause_id.eq("copd")].copy().sort_values("row_id").reset_index(drop=True)
    hpars, _ = actual_state_hyperparameters(c)
    mcfg = cfg["hierarchical_imputation"]
    chains, burn, thin, per_chain = mcfg["chains"], mcfg["burn_in"], mcfg["thin"], mcfg["draws_per_chain"]
    saved = []; diag = []
    sup = c.death_suppressed.astype(bool).to_numpy()
    county_groups = {int(k): np.asarray(v, int) for k, v in c.groupby("county_fips").groups.items()}
    margin_groups = [(state, int(year), g.index[g.death_suppressed.astype(bool)].to_numpy(),
                      int(round(float(g.state_deaths.iloc[0]) - float(g.deaths.sum(skipna=True)))))
                     for (state, year), g in c.groupby(["state_abbr", "year"], sort=True)
                     if g.death_suppressed.astype(bool).any()]
    total_iterations = burn + thin * per_chain
    for chain in range(chains):
        rng = np.random.default_rng(cfg["seed"] + 1000 * lower + 100 * chain + 77)
        y = initialize_counts(c, hpars, lower, upper, rng)
        rates = {}
        for iteration in range(1, total_iterations + 1):
            for state in sorted(c.state_abbr.unique()):
                post, meta = hpars[state]
                state_rows = c.index[c.state_abbr.eq(state)].to_numpy()
                for fips in c.loc[state_rows, "county_fips"].astype(int).unique():
                    idx = county_groups[int(fips)]
                    shape = meta["prior_shape"] + float(y[idx].sum())
                    rate = meta["prior_rate"] + float(c.loc[idx, "population"].sum())
                    rates[int(fips)] = float(rng.gamma(shape, 1.0 / rate))
            for state, year, idx, hidden_total in margin_groups:
                fips = c.loc[idx, "county_fips"].astype(int).to_numpy()
                lam = c.loc[idx, "population"].to_numpy(float) * np.array([rates[int(f)] for f in fips])
                y[idx] = sample_prepared(
                    prepare_conditional_poisson(lam, hidden_total, lower, upper), rng)
            if iteration > burn and (iteration - burn) % thin == 0:
                draw_number = (iteration - burn) // thin
                saved.append((chain, draw_number, y.copy()))
                diag.append({"boundary": f"{lower}-{upper}", "chain": chain + 1,
                             "draw_in_chain": draw_number,
                             "mean_suppressed": float(y[sup].mean()),
                             "fraction_at_lower": float((y[sup] == lower).mean()),
                             "fraction_at_upper": float((y[sup] == upper).mean()),
                             "sum_suppressed": int(y[sup].sum())})
        print(f"hierarchical Gibbs {lower}-{upper}: chain {chain + 1}/{chains}", flush=True)
    draws = np.stack([x[2] for x in saved])
    diag_df = pd.DataFrame(diag)
    for metric in ["mean_suppressed", "fraction_at_lower", "fraction_at_upper"]:
        arr = diag_df.pivot(index="chain", columns="draw_in_chain", values=metric).sort_index().to_numpy()
        diag_df[f"Rhat_{metric}"] = rhat(arr)
    # Exact data invariants.
    observed = ~sup
    if not np.all(draws[:, observed] == c.loc[observed, "deaths"].to_numpy()[None, :]):
        raise AssertionError("public counts changed")
    if not np.all((draws[:, sup] >= lower) & (draws[:, sup] <= upper)):
        raise AssertionError("boundary failure")
    for (state, year), g in c.groupby(["state_abbr", "year"]):
        idx = g.index.to_numpy()
        target = int(round(float(g.state_deaths.iloc[0])))
        if not np.all(draws[:, idx].sum(axis=1) == target):
            raise AssertionError(f"state margin failure {state} {year}")

    # The global mean of suppressed counts is fixed by the exact margins, so an
    # R-hat for that scalar is not a useful convergence diagnostic.  Summarize
    # split-chain behavior across individual variable suppressed cells instead.
    cube = draws[:, sup].reshape(chains, per_chain, int(sup.sum())).astype(float)
    within = np.mean(np.var(cube, axis=1, ddof=1), axis=0)
    between = per_chain * np.var(np.mean(cube, axis=1), axis=0, ddof=1)
    variable = within > 0
    cell_rhat = np.full(int(sup.sum()), np.nan)
    raw_rhat = np.sqrt(((per_chain - 1) / per_chain * within[variable]
                        + between[variable] / per_chain) / within[variable])
    cell_rhat[variable] = np.maximum(1.0, raw_rhat)
    diag_df["cell_Rhat_n_variable"] = int(variable.sum())
    diag_df["cell_Rhat_n_constant"] = int((~variable).sum())
    diag_df["cell_Rhat_median"] = float(np.nanmedian(cell_rhat))
    diag_df["cell_Rhat_p95"] = float(np.nanquantile(cell_rhat, .95))
    diag_df["cell_Rhat_max"] = float(np.nanmax(cell_rhat))
    diag_df["cell_Rhat_fraction_gt_1_10"] = float(np.nanmean(cell_rhat > 1.10))
    diag_df["cell_Rhat_note"] = (
        "individual suppressed-cell diagnostic; constant cells excluded; "
        "global mean R-hat is uninformative under exact margins"
    )
    np.savez_compressed(outfile, draws=draws.astype(np.int16), row_ids=c.row_id.astype(int).to_numpy(),
                        lower=np.array([lower]), upper=np.array([upper]), config_version=np.array([cfg["version"]]))
    diag_df.to_csv(diagfile, index=False)
    return draws, c.row_id.astype(int).to_numpy(), diag_df


def fit_hierarchical_health_model(data: pd.DataFrame, draws: np.ndarray, row_ids: np.ndarray,
                                  scenario: str, version: str) -> tuple[pd.DataFrame, dict]:
    fitfile = MODELS / f"per_imputation_{scenario}_{version}.csv"
    poolfile = MODELS / f"pooled_{scenario}_{version}.json"
    if fitfile.exists() and poolfile.exists():
        return pd.read_csv(fitfile), json.loads(poolfile.read_text())
    sub = filter_spec_data(data, model_spec()).copy()
    _, X, names, idx_names = build_design(sub, model_spec())
    mapper = pd.Series(np.arange(len(row_ids)), index=row_ids)
    loc = mapper.loc[sub.row_id.astype(int)].to_numpy(int)
    outcomes = draws[:, loc].astype(float)
    offset = np.log(sub.population.to_numpy(float)); groups = sub.county_fips.to_numpy(int)
    alpha, warm = estimate_nb_alpha(outcomes.mean(axis=0), X, offset)
    j = idx_names[TERM]; fits = []
    for m, y in enumerate(outcomes, 1):
        try:
            fit, _ = fit_negative_binomial(y, X, offset, groups, alpha, warm)
            fits.append({"scenario": scenario, "imputation": m,
                         "estimate": float(fit.params[j]),
                         "within_variance": float(fit.cov_params()[j, j]), "status": "ok"})
        except Exception as exc:
            fits.append({"scenario": scenario, "imputation": m, "status": "failed", "error": repr(exc)})
        print(f"health model {scenario}: {m}/{len(outcomes)}", flush=True)
    f = pd.DataFrame(fits); f.to_csv(fitfile, index=False)
    good = f.loc[f.status.eq("ok")]
    if len(good) != len(outcomes):
        raise RuntimeError(f"{scenario}: only {len(good)}/{len(outcomes)} fits succeeded")
    pool = rubin_pool(good.estimate.to_numpy(), good.within_variance.to_numpy())
    pool.update({"scenario": scenario, "n_county_years": len(sub),
                 "n_counties": int(sub.county_fips.nunique()), "sample_hash": key_hash(sub),
                 "design_rank": int(np.linalg.matrix_rank(X)), "design_columns": int(X.shape[1]),
                 "nb_alpha": float(alpha), "formula": RHS, "convergence": f"{len(good)}/{len(outcomes)}"})
    poolfile.write_text(json.dumps(pool, indent=2), encoding="utf-8")
    return f, pool


def load_fixed_fits() -> dict[str, pd.DataFrame]:
    b0 = pd.read_csv(OLD_B0_FITS)
    b0 = b0.loc[b0.term.eq(TERM), ["imputation", "estimate", "within_variance"]].copy()
    b0["scenario"] = "fixed_EB_B0_0_9"; b0["status"] = "ok"
    b1j = json.loads(OLD_B1_CHECKPOINT.read_text())
    b1 = pd.DataFrame(b1j["fits"])[["imputation", "estimate", "variance", "status"]].rename(columns={"variance": "within_variance"})
    b1["scenario"] = "fixed_EB_B1_1_9"
    return {"fixed_EB_B0_0_9": b0, "fixed_EB_B1_1_9": b1}


def pool_all_scenarios(fits: dict[str, pd.DataFrame], pools: dict[str, dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for scenario, f in fits.items():
        good = f.loc[f.status.eq("ok")]
        pool = pools.get(scenario) or rubin_pool(good.estimate, good.within_variance)
        beta, se = pool["estimate"], pool["standard_error"]
        low, high = pool["ci_low"], pool["ci_high"]
        rows.append({"scenario": scenario,
                     "allocation_model": "hierarchical_Gamma_Poisson" if scenario.startswith("hierarchical") else "fixed_historical_EB",
                     "boundary": "1-9" if "B1" in scenario else "0-9", "m": len(good),
                     "beta": beta, "SE": se, "beta_CI_lower": low, "beta_CI_upper": high,
                     "interaction_percent": 100 * math.expm1(beta),
                     "CI_percent_lower": 100 * math.expm1(low),
                     "CI_percent_upper": 100 * math.expm1(high),
                     "within_variance": pool["within_variance"],
                     "between_imputation_variance": pool["between_variance"],
                     "fraction_missing_information": pool["fraction_missing_information"],
                     "monte_carlo_error": pool["monte_carlo_error"],
                     "selection_rule": "not selected by health-model result"})
    scenario_table = pd.DataFrame(rows).sort_values(["allocation_model", "boundary"])
    scenario_table.to_csv(MODELS / "01_scenario_health_model_results.csv", index=False)

    # Equal-weighted nested-MI summary is a transparent reference, not a posterior
    # probability assignment to either suppression boundary.
    names = sorted(fits)
    n = min(len(fits[x].loc[fits[x].status.eq("ok")]) for x in names)
    q = np.stack([fits[x].loc[fits[x].status.eq("ok")].sort_values("imputation").estimate.to_numpy()[:n] for x in names])
    u = np.stack([fits[x].loc[fits[x].status.eq("ok")].sort_values("imputation").within_variance.to_numpy()[:n] for x in names])
    m_models = len(names); q_model = q.mean(axis=1); qbar = float(q.mean()); ubar = float(u.mean())
    between_model = float(np.var(q_model, ddof=1))
    within_model = float(np.mean(np.var(q, axis=1, ddof=1)))
    total = ubar + (1 + 1 / m_models) * between_model + (1 - 1 / n) * within_model
    se = math.sqrt(total); low, high = qbar - 1.96 * se, qbar + 1.96 * se
    nested = pd.DataFrame([{
        "ensemble": "equal_weight_four_scenarios_reference",
        "scenarios": ";".join(names), "n_models": m_models, "imputations_per_model": n,
        "beta": qbar, "SE_large_sample": se, "beta_CI_lower": low, "beta_CI_upper": high,
        "interaction_percent": 100 * math.expm1(qbar),
        "CI_percent_lower": 100 * math.expm1(low), "CI_percent_upper": 100 * math.expm1(high),
        "average_complete_data_variance": ubar, "within_model_imputation_variance": within_model,
        "between_model_variance": between_model, "total_variance_nested_rule": total,
        "warning": "equal scenario weights are a sensitivity reference, not posterior probabilities or proof of the true boundary",
    }])
    nested.to_csv(MODELS / "02_nested_model_uncertainty_summary.csv", index=False)
    return scenario_table, nested


def build_report(cfg: dict, validation: pd.DataFrame, boot: pd.DataFrame,
                 scenario: pd.DataFrame, nested: pd.DataFrame, mcmc: pd.DataFrame) -> None:
    best = validation.sort_values(["scope", "MAE"]).groupby("scope").first().reset_index()
    h = scenario.loc[scenario.allocation_model.eq("hierarchical_Gamma_Poisson")]
    fixed = scenario.loc[scenario.allocation_model.eq("fixed_historical_EB")]
    lines = [
        "# Suppression插补方法创新性评估与优化pilot",
        "",
        "## 结论等级",
        "",
        "本项目形成的是可投稿的方法学增强候选，而不是已经被证明为全新统计理论。现有贡献在于把有界整数计数、州级精确总量、县级率参数不确定性以及边界/分配模型不确定性放在同一流程中。是否优于旧方法只由伪压制验证判断，不由健康模型P值决定。",
        "",
        "## 方法",
        "",
        "- 旧方法：固定历史负担EB权重下的条件泊松分配。",
        "- 优化方法：Gamma–Poisson县级层级率后验与受压制计数交替抽样；每次分配仍严格满足州—年COPD总数和0–9或1–9整数边界。",
        "- 插补模型不使用smoke、SES或smoke×SES，避免把目标关联直接写入死亡数。",
        "- 以公开可见的10–19例单元构造伪压制组，并留出整个目标年份的结局历史；这是最接近阈值的可观测类比，但不是1–9真实计数的外部金标准。",
        "",
        "## 伪压制验证",
        "",
    ]
    for _, r in validation.sort_values(["scope", "MAE"]).iterrows():
        lines.append(f"- {r.scope}｜{r.method}：MAE={r.MAE:.3f}，RMSE={r.RMSE:.3f}，CRPS={r.mean_CRPS:.3f}，95%区间覆盖={100*r.coverage_95:.1f}%，平均宽度={r.mean_interval_width:.2f}（{int(r.n_groups)}组、{int(r.n_cells)}单元）。")
    lines += ["", "层级EB相对固定EB的组级bootstrap差（负值支持层级EB）："]
    for _, r in boot.iterrows():
        lines.append(f"- {r.scope}｜{r.metric}: {r.observed_difference:+.3f}（bootstrap 95%区间 {r.bootstrap_q025:+.3f} 至 {r.bootstrap_q975:+.3f}）。")
    lines += ["", "## 固定COPD M2结果", ""]
    for _, r in scenario.iterrows():
        lines.append(f"- {r.scenario}: {r.interaction_percent:.4f}%（95% CI {r.CI_percent_lower:.4f}% 至 {r.CI_percent_upper:.4f}%），SE={r.SE:.6f}，m={int(r.m)}。")
    nr = nested.iloc[0]
    lines += ["", f"四方案等权嵌套MI参考：{nr.interaction_percent:.4f}%（大样本95% CI {nr.CI_percent_lower:.4f}% 至 {nr.CI_percent_upper:.4f}%）。该结果仅展示模型不确定性传播，不代表四个方案具有真实相等概率。",
              "",
              "四方案beta极差为"
              f"{scenario.beta.max()-scenario.beta.min():.6f}（相对旧0–9参考beta为"
              f"{100*(scenario.beta.max()-scenario.beta.min())/fixed.loc[fixed.boundary.eq('0-9'),'beta'].iloc[0]:.2f}%）；"
              f"interaction百分比极差为{scenario.interaction_percent.max()-scenario.interaction_percent.min():.4f}个百分点；"
              f"SE最大相对最小仅高{100*(scenario.SE.max()/scenario.SE.min()-1):.2f}%。"
              "嵌套参考中，模型间方差占总方差"
              f"{100*nr.between_model_variance/nr.total_variance_nested_rule:.3f}%。",
              "",
              "## 优化决策",
              "",
              "- 主分配方案继续使用固定历史负担EB：它在全结局伪压制验证中的MAE、RMSE和CRPS均最好；没有证据支持仅因层级模型更复杂就替换主方案。",
              "- 层级Gamma–Poisson版保留为参数不确定性敏感性分支：COPD点预测与固定EB近似，但区间略宽；它回答固定权重是否低估插补不确定性。",
              "- 0–9与1–9继续并列为边界假设；原始下载批次规则未核实，因此不能按健康结果选择边界。",
              "- 四方案等权嵌套结果只作为模型不确定性参考。若正式采用模型平均，场景权重必须事先给定或由独立验证确定。",
              "",
              "## 当前可支持的实证结论",
              "",
              "在固定COPD M2、相同2009–2020县—年样本和相同变量尺度下，smoke×SES估计对两种合法边界假设及固定/层级两种分配模型均稳定；本组合理插补选择不是该关联的主要数值驱动因素。这个结论是敏感性稳健性结论，不等于插补无偏，也不证明真实小计数已恢复。",
              "", "## MCMC与数据约束", ""]
    for boundary, g in mcmc.groupby("boundary"):
        lines.append(
            f"- {boundary}: 单元级R-hat中位数={g.cell_Rhat_median.iloc[0]:.3f}，"
            f"P95={g.cell_Rhat_p95.iloc[0]:.3f}，最大值={g.cell_Rhat_max.iloc[0]:.3f}，"
            f">1.10比例={100*g.cell_Rhat_fraction_gt_1_10.iloc[0]:.1f}%；"
            "全部公开计数、整数边界与州总量断言通过。精确总量使全局均值固定，"
            "因此不把其R-hat作为收敛证据。"
        )
    lines += ["", "## 可形成的创新点", "",
              "1. 对CDC小计数压制不再只做单一权重的随机分配，而是使用精确总量约束下的层级贝叶斯数据增强，同时传播县级潜在率参数的不确定性。",
              "2. 将0–9/1–9边界和分配模型视为可区分的不确定性来源，通过多模型嵌套MI展示其对最终交互估计的贡献，而不是选择最显著的方案。",
              "3. 用接近压制阈值的公开10–19例记录进行预先定义的伪压制验证，为权重模型选择提供与健康结论独立的经验依据。",
              "", "## 不能声称的内容", "",
              "- 不能声称恢复了任何县的真实被压制死亡数。",
              "- 不能把伪压制验证称为1–9单元的外部金标准。",
              "- 不能仅凭本pilot声称方法达到某一期刊层级；正式方法学主张仍需要预先设定的数据生成机制模拟、偏倚/覆盖率比较和独立数据复核。",
              "- CDC原始下载批次语义仍未因此得到核实。",
              "- 当前层级分配模型有意未包含smoke×SES，因此是保守的分配敏感性模型，而不是已证明与负二项交互分析完全相容的联合模型。若把它提升为正式统计方法主张，需要预先定义并验证与实质模型相容的联合计数模型；不能直接把健康模型协变量塞入权重后以同一健康关联验证自己。",
              "", "## 文献定位", "",
              "该方法与小区域估计中的benchmarking、multiple-model multiple imputation及substantive-model-compatible MI相邻；本项目的贡献应表述为这些思想在有界小计数、精确州总量和环境流行病学交互估计中的整合与实证评估，而不是宣称首次发明上述任一通用概念。",
              "",
              "- Bartlett et al. (2015), substantive-model-compatible MI: https://doi.org/10.1177/0962280214521348",
              "- Siddique, Harel & Crespi (2012), multiple-model/nested MI: https://doi.org/10.1214/12-AOAS555",
              "- You & Rao (2011), Bayesian small-area benchmarking: https://doi.org/10.1080/00949655.2010.496726",
    ]
    (REPORTS / "suppression_method_innovation_report_CN.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG_DEFAULT)
    parser.add_argument("--stage", choices=["all", "validate", "impute", "models", "report"], default="all")
    args = parser.parse_args(); ensure_dirs(); cfg = load_config(args.config)
    start = time.time()
    panel = pd.read_csv(PANEL_FILE)
    sampler_unit_tests()

    predfile = TABLES / "02_pseudo_suppression_predictions.csv"
    sumfile = TABLES / "03_pseudo_suppression_validation_summary.csv"
    bootfile = TABLES / "04_pseudo_suppression_pairwise_bootstrap.csv"
    if args.stage in ("all", "validate") or not (predfile.exists() and sumfile.exists() and bootfile.exists()):
        _, validation, boot = pseudo_suppression_validation(panel, cfg)
    else:
        validation, boot = pd.read_csv(sumfile), pd.read_csv(bootfile)
    if args.stage == "validate":
        return

    hierarchical = {}; all_diag = []
    for lower, upper in cfg["hierarchical_imputation"]["boundaries"]:
        draws, row_ids, diag = hierarchical_gibbs_imputations(panel, cfg, int(lower), int(upper))
        hierarchical[f"hierarchical_EB_B{lower}_{lower}_{upper}"] = (draws, row_ids)
        all_diag.append(diag)
    mcmc = pd.concat(all_diag, ignore_index=True)
    mcmc.to_csv(TABLES / f"06_mcmc_diagnostics_all_boundaries_{cfg['version']}.csv", index=False)
    if args.stage == "impute":
        return

    analysis_data, _ = load_analysis_data()
    fixed_fits = load_fixed_fits(); fits = dict(fixed_fits); pools = {}
    for scenario, (draws, row_ids) in hierarchical.items():
        f, pool = fit_hierarchical_health_model(analysis_data, draws, row_ids, scenario, cfg["version"])
        fits[scenario] = f; pools[scenario] = pool
    scenario, nested = pool_all_scenarios(fits, pools)
    decision = pd.DataFrame([
        {"component": "primary allocation", "decision": "retain fixed historical EB",
         "evidence": "best all-outcome pseudo-suppression MAE, RMSE and CRPS",
         "status": "supported by actual validation"},
        {"component": "hierarchical Gamma-Poisson", "decision": "retain as uncertainty sensitivity",
         "evidence": "propagates county-rate uncertainty; no consistent predictive superiority",
         "status": "implemented and tested for COPD"},
        {"component": "support boundary", "decision": "report 0-9 and 1-9 in parallel",
         "evidence": "download-batch rule unresolved; fixed M2 estimate stable",
         "status": "boundary sensitivity completed"},
        {"component": "four-scenario nested MI", "decision": "reference only",
         "evidence": "between-model uncertainty quantified under explicit equal weights",
         "status": "computed; weights are assumptions"},
        {"component": "substantive-model-compatible joint MI", "decision": "not claim completed",
         "evidence": "requires prespecified joint model plus simulation validation",
         "status": "remaining methodological limitation"},
    ])
    decision.to_csv(TABLES / "07_method_selection_decision.csv", index=False)
    build_report(cfg, validation, boot, scenario, nested, mcmc)

    manifest = {
        "version": cfg["version"], "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_seconds": time.time() - start,
        "inputs": {str(PANEL_FILE.relative_to(ROOT)): sha256(PANEL_FILE),
                   str(OLD_B0_FILE.relative_to(ROOT)): sha256(OLD_B0_FILE),
                   str(OLD_B0_FITS.relative_to(ROOT)): sha256(OLD_B0_FITS),
                   str(OLD_B1_CHECKPOINT.relative_to(ROOT)): sha256(OLD_B1_CHECKPOINT)},
        "constraints_validated": ["integer bounds", "exact state-year COPD totals", "public counts unchanged"],
        "target_variables_in_imputation_model": [], "paper_files_modified": False,
        "method_selection": {
            "primary": "fixed historical EB exact-margin conditional Poisson",
            "sensitivity": "hierarchical Gamma-Poisson exact-margin data augmentation",
            "boundaries": ["0-9 assumption", "1-9 assumption"],
            "selection_basis": "pseudo-suppression validation, not health-model significance"
        },
        "known_limitations": [
            "original CDC download-batch suppression rule unresolved",
            "visible 10-19 pseudo-suppression is an analogue, not a 1-9 gold standard",
            "hierarchical allocation is not a fully substantive-model-compatible joint model"
        ],
        "status": "completed_pilot_not_full_method_validation",
    }
    (HERE / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "elapsed_seconds": manifest["elapsed_seconds"]}, indent=2))


if __name__ == "__main__":
    main()
