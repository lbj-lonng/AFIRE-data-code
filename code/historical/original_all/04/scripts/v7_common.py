from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import yaml
from scipy.stats import norm, t as student_t

ROOT = Path(os.environ.get("AFIRE_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
DATA = ROOT / "data_processed"
RESULTS = ROOT / "results"
MODEL_RESULTS = RESULTS / "models"
TABLES = RESULTS / "tables"
FIGURES = RESULTS / "figures"
REPORTS = RESULTS / "reports"
LOGS = ROOT / "logs"
CONFIG_PATH = ROOT / "config" / "analysis.yml"
PANEL_PATH = DATA / "county_year_disease_panel_v6_3.csv"
DRAWS_PATH = DATA / "imputed_deaths_eb_history_v5.npz"

for directory in [MODEL_RESULTS, TABLES, FIGURES, REPORTS, LOGS]:
    directory.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    label: str
    group: str
    cause_id: str
    family: str
    rhs: str
    exposure_term: str
    interaction_term: str
    required: tuple[str, ...]
    year_min: int
    year_max: int
    include_states: tuple[str, ...] = ()
    exclude_states: tuple[str, ...] = ()
    exclude_years: tuple[int, ...] = ()
    min_rows: int = 500
    min_counties: int = 30
    notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        for key in ["required", "include_states", "exclude_states", "exclude_years"]:
            d[key] = list(d[key])
        return d


def zscore_series(series: pd.Series) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    sd = float(x.std(ddof=1))
    if not np.isfinite(sd) or sd <= 0:
        return pd.Series(np.nan, index=series.index, dtype=float)
    return (x - float(x.mean())) / sd


def add_county_year_standardized_columns(data: pd.DataFrame) -> pd.DataFrame:
    """Standardize county-year covariates once, then map them to all diseases."""
    data = data.copy()
    smoke_candidates = [
        "county_smoke_pm25_annual_burden_y",
        "county_smoke_pm25_annual_burden_x",
        "county_smoke_pm25_annual_burden",
    ]
    smoke_col = next((c for c in smoke_candidates if c in data.columns), None)
    if "nonwildfire_pm25_candidate" not in data.columns and "pm25_annual_mean" in data.columns and smoke_col:
        data["nonwildfire_pm25_candidate"] = (
            pd.to_numeric(data["pm25_annual_mean"], errors="coerce")
            - pd.to_numeric(data[smoke_col], errors="coerce")
        )
    if "population_density_km2" in data.columns:
        data["log_population_density_v7"] = np.log1p(
            pd.to_numeric(data["population_density_km2"], errors="coerce")
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
    keys = ["county_fips", "year"]
    unique = data[keys + [c for c in mapping.values() if c in data.columns]].drop_duplicates(keys)
    for output, source in mapping.items():
        if source not in unique.columns:
            data[output] = np.nan
            continue
        unique[output] = zscore_series(unique[source])
        mapper = unique.set_index(keys)[output]
        data[output] = pd.MultiIndex.from_frame(data[keys]).map(mapper)
    return data


def load_analysis_data() -> tuple[pd.DataFrame, np.ndarray]:
    if not PANEL_PATH.exists():
        raise FileNotFoundError(
            f"缺少分析面板：{PANEL_PATH}\n"
            "请从 v6.3 项目的 data_processed 目录复制 county_year_disease_panel_v6_3.csv。"
        )
    if not DRAWS_PATH.exists():
        raise FileNotFoundError(
            f"缺少多重插补文件：{DRAWS_PATH}\n"
            "请从 v6.3 项目的 data_processed 目录复制 imputed_deaths_eb_history_v5.npz。"
        )
    data = pd.read_csv(PANEL_PATH, low_memory=False)
    required_base = [
        "row_id", "county_fips", "year", "state_abbr", "cause_id", "population",
        "pm25_iqr", "ses_baseline_std",
    ]
    missing = [c for c in required_base if c not in data.columns]
    if missing:
        raise ValueError(f"分析面板缺少必要字段：{missing}")
    for col in ["row_id", "county_fips", "year", "population"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["row_id", "county_fips", "year", "population"]).copy()
    data["row_id"] = data["row_id"].astype("int64")
    data["county_fips"] = data["county_fips"].astype("int64")
    data["year"] = data["year"].astype("int64")
    data["county_model"] = data["county_fips"].astype(str)
    data["year_model"] = data["year"].astype(str)
    data["state_year"] = data["state_abbr"].astype(str) + "_" + data["year_model"]
    data = add_county_year_standardized_columns(data)

    npz = np.load(DRAWS_PATH)
    if "draws" not in npz.files:
        raise ValueError(f"{DRAWS_PATH} 中不存在 draws 数组")
    draws = np.asarray(npz["draws"], dtype=float)
    if draws.ndim != 2:
        raise ValueError(f"draws 应为二维数组，实际形状：{draws.shape}")
    max_row = int(data["row_id"].max())
    if draws.shape[1] <= max_row:
        raise ValueError(
            f"draws列数({draws.shape[1]})不足以索引最大row_id({max_row})；面板和插补文件不匹配。"
        )
    return data, draws


def filter_spec_data(data: pd.DataFrame, spec: ModelSpec) -> pd.DataFrame:
    subset = data.loc[
        data["cause_id"].eq(spec.cause_id)
        & data["year"].between(spec.year_min, spec.year_max)
    ].copy()
    if spec.include_states:
        subset = subset.loc[subset["state_abbr"].isin(spec.include_states)].copy()
    if spec.exclude_states:
        subset = subset.loc[~subset["state_abbr"].isin(spec.exclude_states)].copy()
    if spec.exclude_years:
        subset = subset.loc[~subset["year"].isin(spec.exclude_years)].copy()
    needed = ["row_id", "population", "county_fips", "year"] + list(spec.required)
    missing_columns = [c for c in needed if c not in subset.columns]
    if missing_columns:
        raise ValueError(f"{spec.model_id} 缺少字段：{missing_columns}")
    subset = subset.dropna(subset=needed).copy()
    subset = subset.loc[pd.to_numeric(subset["population"], errors="coerce") > 0].copy()
    if len(subset) < spec.min_rows or subset["county_fips"].nunique() < spec.min_counties:
        raise RuntimeError(
            f"{spec.model_id} 完整记录不足：{len(subset)}行，"
            f"{subset['county_fips'].nunique()}县；最低要求为{spec.min_rows}行、{spec.min_counties}县。"
        )
    return subset


def rubin_pool(estimates: Iterable[float], within_variances: Iterable[float]) -> dict:
    q = np.asarray(list(estimates), dtype=float)
    u = np.asarray(list(within_variances), dtype=float)
    valid = np.isfinite(q) & np.isfinite(u) & (u >= 0)
    q = q[valid]
    u = u[valid]
    if len(q) == 0:
        raise ValueError("没有可用于Rubin合并的有效估计")
    m = len(q)
    qbar = float(q.mean())
    ubar = float(u.mean())
    between = float(q.var(ddof=1)) if m > 1 else 0.0
    total = float(ubar + (1 + 1 / m) * between)
    se = math.sqrt(max(total, 0.0))
    if ubar > 0:
        r = (1 + 1 / m) * between / ubar
    else:
        r = np.inf if between > 0 else 0.0
    if m > 1 and np.isfinite(r) and r > 0:
        df = float((m - 1) * (1 + 1 / r) ** 2)
    else:
        df = 1e12
    crit = float(student_t.ppf(0.975, df)) if df < 1e8 else 1.959963984540054
    statistic = abs(qbar / se) if se > 0 else np.nan
    if se <= 0:
        p_value = np.nan
    elif df < 1e8:
        p_value = float(2 * student_t.sf(statistic, df))
    else:
        p_value = float(2 * norm.sf(statistic))
    if np.isfinite(r) and r >= 0:
        fmi = float((r + 2 / (df + 3)) / (r + 1))
    else:
        fmi = 1.0
    return {
        "estimate": qbar,
        "standard_error": se,
        "ci_low": qbar - crit * se,
        "ci_high": qbar + crit * se,
        "p_value": p_value,
        "m_used": m,
        "within_variance": ubar,
        "between_variance": between,
        "total_variance": total,
        "df_rubin": df,
        "fraction_missing_information": fmi,
        "monte_carlo_error": math.sqrt(between / m) if m > 1 else 0.0,
    }


def bh_adjust(values: pd.Series) -> pd.Series:
    x = pd.to_numeric(values, errors="coerce")
    out = pd.Series(np.nan, index=x.index, dtype=float)
    valid = x.notna()
    if not valid.any():
        return out
    p = x.loc[valid].to_numpy(float)
    order = np.argsort(p)
    ranked = p[order]
    adj = ranked * len(ranked) / np.arange(1, len(ranked) + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    adj = np.clip(adj, 0, 1)
    reverse = np.empty_like(order)
    reverse[order] = np.arange(len(order))
    out.loc[valid] = adj[reverse]
    return out


def effect_scale(row: dict) -> dict:
    estimate = float(row["estimate"])
    low = float(row["ci_low"])
    high = float(row["ci_high"])
    row["irr"] = math.exp(estimate)
    row["irr_ci_low"] = math.exp(low)
    row["irr_ci_high"] = math.exp(high)
    row["percent_change"] = (row["irr"] - 1) * 100
    row["percent_change_ci_low"] = (row["irr_ci_low"] - 1) * 100
    row["percent_change_ci_high"] = (row["irr_ci_high"] - 1) * 100
    return row


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
