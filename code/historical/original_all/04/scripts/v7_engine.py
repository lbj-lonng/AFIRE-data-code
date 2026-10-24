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
from scipy.linalg import qr

from v7_common import (
    MODEL_RESULTS,
    ModelSpec,
    effect_scale,
    filter_spec_data,
    load_analysis_data,
    load_config,
    rubin_pool,
    write_json,
)

warnings.filterwarnings("ignore")


def build_design(subset: pd.DataFrame, spec: ModelSpec):
    design_frame = patsy.dmatrix(spec.rhs, subset, return_type="dataframe")
    original_names = list(design_frame.columns)
    protected_terms = [spec.exposure_term, spec.interaction_term]
    for term in protected_terms:
        if term not in original_names:
            raise RuntimeError(
                f"{spec.model_id} 的目标项 {term!r} 不在设计矩阵中。"
                f"设计矩阵前20项：{original_names[:20]}"
            )
    original = np.asarray(design_frame, dtype=float)
    if not np.isfinite(original).all():
        raise RuntimeError(f"{spec.model_id} 设计矩阵包含NaN或Inf")

    # County FE and state×year FE contain nested state contrasts. Preserve the
    # exposure and interaction columns, then remove only linearly redundant
    # nuisance columns so PPML is identified and numerically stable.
    protected_indices = [original_names.index(term) for term in protected_terms]
    protected = original[:, protected_indices]
    protected_rank = int(np.linalg.matrix_rank(protected))
    if protected_rank != len(protected_indices):
        raise RuntimeError(f"{spec.model_id} 的暴露项和交互项彼此共线")
    q_protected, _ = np.linalg.qr(protected, mode="reduced")
    remaining_indices = [i for i in range(original.shape[1]) if i not in protected_indices]
    remaining = original[:, remaining_indices]
    residual = remaining - q_protected @ (q_protected.T @ remaining)
    if residual.shape[1]:
        _, r_matrix, pivots = qr(residual, mode="economic", pivoting=True)
        diagonal = np.abs(np.diag(r_matrix))
        tolerance = max(residual.shape) * np.finfo(float).eps * (diagonal.max() if diagonal.size else 0.0)
        nuisance_rank = int(np.sum(diagonal > tolerance))
        nuisance_indices = [remaining_indices[int(i)] for i in pivots[:nuisance_rank]]
    else:
        nuisance_indices = []
    selected_indices = sorted(protected_indices + nuisance_indices)
    reduced_frame = design_frame.iloc[:, selected_indices].copy()
    names = list(reduced_frame.columns)
    design = np.asarray(reduced_frame, dtype=float)
    rank = int(np.linalg.matrix_rank(design))
    if rank != design.shape[1]:
        raise RuntimeError(
            f"{spec.model_id} 自动去除冗余列后仍秩不足：rank={rank}, columns={design.shape[1]}。"
        )
    indices = {
        spec.exposure_term: names.index(spec.exposure_term),
        spec.interaction_term: names.index(spec.interaction_term),
    }
    reduced_frame.attrs["original_column_count"] = len(original_names)
    reduced_frame.attrs["dropped_aliased_columns"] = [
        original_names[i] for i in range(len(original_names)) if i not in selected_indices
    ]
    return reduced_frame, design, names, indices


def _cluster_kwargs(groups: np.ndarray) -> dict:
    return {"cov_type": "cluster", "cov_kwds": {"groups": groups, "use_correction": True}}


def fit_poisson_glm(y, design, offset, groups, start_params=None):
    model = sm.GLM(y, design, family=sm.families.Poisson(), offset=offset)
    errors: list[str] = []
    attempts = [
        dict(start_params=start_params, maxiter=300, tol=1e-9),
        dict(maxiter=600, tol=1e-8),
    ]
    for kwargs in attempts:
        if kwargs.get("start_params") is None:
            kwargs.pop("start_params", None)
        try:
            fit = model.fit(**kwargs, **_cluster_kwargs(groups))
            if not bool(getattr(fit, "converged", True)):
                raise RuntimeError("Poisson GLM did not converge")
            params = np.asarray(fit.params, dtype=float)
            cov = np.asarray(fit.cov_params(), dtype=float)
            if not np.isfinite(params).all() or not np.isfinite(cov).all():
                raise RuntimeError("Poisson GLM returned non-finite estimates")
            return fit, "poisson_glm"
        except Exception as exc:
            errors.append(repr(exc))

    # MLE fallback is useful for high-dimensional state×year fixed effects.
    try:
        discrete = sm.Poisson(y, design, offset=offset)
        fit = discrete.fit(
            start_params=start_params,
            method="lbfgs",
            maxiter=1000,
            disp=0,
            cov_type="cluster",
            cov_kwds={"groups": groups, "use_correction": True},
        )
        converged = bool(getattr(fit, "mle_retvals", {}).get("converged", True))
        if not converged:
            raise RuntimeError("Discrete Poisson L-BFGS did not converge")
        params = np.asarray(fit.params, dtype=float)
        cov = np.asarray(fit.cov_params(), dtype=float)
        if not np.isfinite(params).all() or not np.isfinite(cov).all():
            raise RuntimeError("Discrete Poisson returned non-finite estimates")
        return fit, "poisson_discrete_lbfgs"
    except Exception as exc:
        errors.append(repr(exc))
    raise RuntimeError(" | ".join(errors))


def estimate_nb_alpha(mean_y, design, offset) -> tuple[float, np.ndarray]:
    poisson = sm.GLM(mean_y, design, family=sm.families.Poisson(), offset=offset).fit(
        maxiter=300, tol=1e-9
    )
    mu = np.asarray(poisson.fittedvalues, dtype=float)
    numerator = float(np.sum((mean_y - mu) ** 2 - mean_y))
    denominator = max(float(np.sum(mu**2)), 1e-12)
    alpha = float(np.clip(numerator / denominator, 0.001, 2.0))
    nb = sm.GLM(
        mean_y,
        design,
        family=sm.families.NegativeBinomial(alpha=alpha),
        offset=offset,
    ).fit(start_params=np.asarray(poisson.params, dtype=float), maxiter=300, tol=1e-9)
    return alpha, np.asarray(nb.params, dtype=float)


def fit_negative_binomial(y, design, offset, groups, alpha, start_params=None):
    model = sm.GLM(
        y,
        design,
        family=sm.families.NegativeBinomial(alpha=alpha),
        offset=offset,
    )
    errors: list[str] = []
    attempts = [
        dict(start_params=start_params, maxiter=200, tol=1e-8),
        dict(maxiter=500, tol=1e-7),
    ]
    for kwargs in attempts:
        if kwargs.get("start_params") is None:
            kwargs.pop("start_params", None)
        try:
            fit = model.fit(**kwargs, **_cluster_kwargs(groups))
            if not bool(getattr(fit, "converged", True)):
                raise RuntimeError("Negative-binomial IRLS did not converge")
            params = np.asarray(fit.params, dtype=float)
            cov = np.asarray(fit.cov_params(), dtype=float)
            if not np.isfinite(params).all() or not np.isfinite(cov).all():
                raise RuntimeError("Negative-binomial model returned non-finite estimates")
            return fit, "negative_binomial_glm"
        except Exception as exc:
            errors.append(repr(exc))
    raise RuntimeError(" | ".join(errors))


def prepare_model(spec: ModelSpec):
    data, draws_all = load_analysis_data()

    if "nonwildfire_pm25_std_v7" in spec.required:
        precheck = data.loc[
            data["cause_id"].eq(spec.cause_id)
            & data["year"].between(spec.year_min, spec.year_max)
        ].copy()
        if spec.include_states:
            precheck = precheck.loc[precheck["state_abbr"].isin(spec.include_states)]
        if spec.exclude_states:
            precheck = precheck.loc[~precheck["state_abbr"].isin(spec.exclude_states)]
        if spec.exclude_years:
            precheck = precheck.loc[~precheck["year"].isin(spec.exclude_years)]
        candidate = pd.to_numeric(precheck.get("nonwildfire_pm25_candidate"), errors="coerce")
        coverage = float(candidate.notna().mean()) if len(precheck) else 0.0
        negative_share = float(candidate.dropna().lt(0).mean()) if candidate.notna().any() else 1.0
        if coverage < 0.95:
            raise RuntimeError(
                f"{spec.model_id} 非野火PM2.5覆盖率仅{coverage:.2%}，低于95%。"
            )
        if negative_share > 0.01:
            raise RuntimeError(
                f"{spec.model_id} 非野火PM2.5负值比例为{negative_share:.2%}，超过1%，"
                "不能确认单位兼容。"
            )

    subset = filter_spec_data(data, spec)
    design_frame, design, names, target_indices = build_design(subset, spec)
    row_ids = subset["row_id"].astype(int).to_numpy()
    outcomes = draws_all[:, row_ids]
    offset = np.log(subset["population"].to_numpy(float))
    groups = subset["county_fips"].to_numpy(int)
    mean_y = outcomes.mean(axis=0)

    if spec.family == "poisson":
        warm_fit = sm.GLM(mean_y, design, family=sm.families.Poisson(), offset=offset).fit(
            maxiter=300, tol=1e-9
        )
        alpha = None
        warm_params = np.asarray(warm_fit.params, dtype=float)
    elif spec.family == "negative_binomial":
        alpha, warm_params = estimate_nb_alpha(mean_y, design, offset)
    else:
        raise ValueError(f"未知模型族：{spec.family}")

    meta = {
        "model_id": spec.model_id,
        "label": spec.label,
        "group": spec.group,
        "cause_id": spec.cause_id,
        "family": spec.family,
        "rhs": spec.rhs,
        "n_observations": int(len(subset)),
        "n_counties": int(subset["county_fips"].nunique()),
        "n_states": int(subset["state_abbr"].nunique()),
        "states": sorted(subset["state_abbr"].astype(str).unique().tolist()),
        "year_min": int(subset["year"].min()),
        "year_max": int(subset["year"].max()),
        "n_parameters": int(design.shape[1]),
        "design_rank": int(np.linalg.matrix_rank(design)),
        "original_design_columns": int(design_frame.attrs.get("original_column_count", design.shape[1])),
        "dropped_aliased_columns": design_frame.attrs.get("dropped_aliased_columns", []),
        "nb_alpha_fixed": alpha,
        "notes": spec.notes,
    }
    return subset, outcomes, design, target_indices, offset, groups, alpha, warm_params, meta


def fit_one_imputation(
    spec: ModelSpec,
    outcome: np.ndarray,
    design: np.ndarray,
    offset: np.ndarray,
    groups: np.ndarray,
    alpha: float | None,
    warm_params: np.ndarray,
    target_indices: dict[str, int],
) -> dict:
    if spec.family == "poisson":
        fit, estimator = fit_poisson_glm(outcome, design, offset, groups, warm_params)
    else:
        fit, estimator = fit_negative_binomial(
            outcome, design, offset, groups, float(alpha), warm_params
        )
    params = np.asarray(fit.params, dtype=float)
    covariance = np.asarray(fit.cov_params(), dtype=float)
    target_terms = [spec.exposure_term, spec.interaction_term]
    estimates = {term: float(params[target_indices[term]]) for term in target_terms}
    variances = {
        term: float(covariance[target_indices[term], target_indices[term]])
        for term in target_terms
    }
    target_cov = float(
        covariance[target_indices[spec.exposure_term], target_indices[spec.interaction_term]]
    )
    return {
        "status": "completed",
        "estimator": estimator,
        "estimates": estimates,
        "variances": variances,
        "exposure_interaction_covariance": target_cov,
        "converged": True,
    }


def run_model(spec: ModelSpec, retry_failures: bool = True) -> dict:
    config = load_config()
    minimum = int(config.get("minimum_successful_imputations", 25))
    model_dir = MODEL_RESULTS / spec.model_id
    checkpoints = model_dir / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    status_path = model_dir / "status.json"
    print(f"[{spec.model_id}] preparing", flush=True)
    try:
        (
            subset,
            outcomes,
            design,
            target_indices,
            offset,
            groups,
            alpha,
            warm_params,
            meta,
        ) = prepare_model(spec)
    except Exception as exc:
        status = {
            "model_id": spec.model_id,
            "label": spec.label,
            "group": spec.group,
            "status": "blocked",
            "reason": repr(exc),
        }
        write_json(status_path, status)
        print(f"[{spec.model_id}] BLOCKED: {exc}", flush=True)
        return status

    for index, outcome in enumerate(outcomes, start=1):
        checkpoint = checkpoints / f"imputation_{index:02d}.json"
        if checkpoint.exists():
            try:
                previous = json.loads(checkpoint.read_text(encoding="utf-8"))
                if previous.get("status") == "completed":
                    print(f"[{spec.model_id}] {index:02d}/{len(outcomes)} cached", flush=True)
                    continue
                if previous.get("status") == "failed" and not retry_failures:
                    continue
            except Exception:
                pass
        print(f"[{spec.model_id}] {index:02d}/{len(outcomes)}", flush=True)
        try:
            result = fit_one_imputation(
                spec,
                outcome,
                design,
                offset,
                groups,
                alpha,
                warm_params,
                target_indices,
            )
            result.update({"model_id": spec.model_id, "imputation": index})
        except Exception as exc:
            result = {
                "model_id": spec.model_id,
                "imputation": index,
                "status": "failed",
                "error": repr(exc),
            }
        write_json(checkpoint, result)

    completed = []
    failures = []
    for checkpoint in sorted(checkpoints.glob("imputation_*.json")):
        payload = json.loads(checkpoint.read_text(encoding="utf-8"))
        if payload.get("status") == "completed":
            completed.append(payload)
        else:
            failures.append(payload)

    if len(completed) < minimum:
        status = {
            **meta,
            "status": "incomplete",
            "successful_imputations": len(completed),
            "failed_imputations": len(failures),
            "required_minimum": minimum,
        }
        write_json(status_path, status)
        pd.DataFrame(failures).to_csv(model_dir / "failures.csv", index=False, encoding="utf-8-sig")
        print(f"[{spec.model_id}] INCOMPLETE {len(completed)}/{len(outcomes)}", flush=True)
        return status

    per_rows = []
    covariance_rows = []
    for payload in completed:
        imp = int(payload["imputation"])
        for term in [spec.exposure_term, spec.interaction_term]:
            per_rows.append({
                "model_id": spec.model_id,
                "label": spec.label,
                "group": spec.group,
                "cause_id": spec.cause_id,
                "imputation": imp,
                "term": term,
                "estimate": float(payload["estimates"][term]),
                "within_variance": float(payload["variances"][term]),
                "estimator": payload.get("estimator", spec.family),
            })
        covariance_rows.append({
            "model_id": spec.model_id,
            "imputation": imp,
            "exposure_term": spec.exposure_term,
            "interaction_term": spec.interaction_term,
            "covariance": float(payload["exposure_interaction_covariance"]),
        })
    per = pd.DataFrame(per_rows)
    cov = pd.DataFrame(covariance_rows)
    per.to_csv(model_dir / "per_imputation.csv.gz", index=False, compression="gzip")
    cov.to_csv(model_dir / "target_covariance.csv.gz", index=False, compression="gzip")
    pd.DataFrame(failures).to_csv(model_dir / "failures.csv", index=False, encoding="utf-8-sig")

    pooled_rows = []
    for term, group in per.groupby("term", sort=False):
        pooled = rubin_pool(group["estimate"], group["within_variance"])
        pooled.update(meta)
        pooled.update({
            "term": term,
            "successful_imputations": int(group["imputation"].nunique()),
            "failed_imputations": len(failures),
        })
        pooled_rows.append(effect_scale(pooled))
    pooled_frame = pd.DataFrame(pooled_rows)
    pooled_frame.to_csv(model_dir / "pooled.csv", index=False, encoding="utf-8-sig")

    status = {
        **meta,
        "status": "completed",
        "successful_imputations": len(completed),
        "failed_imputations": len(failures),
    }
    write_json(status_path, status)
    interaction = pooled_frame.loc[pooled_frame["term"].eq(spec.interaction_term)]
    if not interaction.empty:
        row = interaction.iloc[0]
        print(
            f"[{spec.model_id}] completed: {row['percent_change']:.3f}% "
            f"({row['percent_change_ci_low']:.3f}, {row['percent_change_ci_high']:.3f}), "
            f"p={row['p_value']:.5g}",
            flush=True,
        )
    return status
