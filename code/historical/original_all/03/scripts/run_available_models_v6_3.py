from __future__ import annotations

import json
import math
import os
import warnings
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
from scipy.stats import norm, t as student_t

warnings.filterwarnings('ignore')
ROOT = Path(os.environ.get('AFIRE_COUNTY_PROJECT_ROOT', Path(__file__).resolve().parents[1]))
DATA = ROOT / 'data_processed'
TABLES = ROOT / 'tables'
LOGS = ROOT / 'logs'
TABLES.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)
PANEL = DATA / 'county_year_disease_panel_v6_3.csv'
DRAWS = DATA / 'imputed_deaths_eb_history_v5.npz'


def zscore(s: pd.Series) -> pd.Series:
    x = pd.to_numeric(s, errors='coerce')
    sd = x.std(ddof=1)
    if not np.isfinite(sd) or sd <= 0:
        return pd.Series(np.nan, index=s.index)
    return (x - x.mean()) / sd


def rubin_pool(estimates, within_variances) -> dict:
    q = np.asarray(estimates, dtype=float)
    u = np.asarray(within_variances, dtype=float)
    m = len(q)
    qbar = float(q.mean())
    ubar = float(u.mean())
    between = float(q.var(ddof=1)) if m > 1 else 0.0
    total = ubar + (1 + 1 / m) * between
    se = math.sqrt(max(total, 0.0))
    r = (1 + 1 / m) * between / ubar if ubar > 0 else (np.inf if between > 0 else 0.0)
    df = (m - 1) * (1 + 1 / r) ** 2 if m > 1 and np.isfinite(r) and r > 0 else 1e12
    crit = float(student_t.ppf(0.975, df)) if df < 1e8 else 1.959963984540054
    stat = abs(qbar / se) if se > 0 else np.nan
    p = float(2 * student_t.sf(stat, df)) if se > 0 and df < 1e8 else (float(2 * norm.sf(stat)) if se > 0 else np.nan)
    fmi = float((r + 2 / (df + 3)) / (r + 1)) if np.isfinite(r) and r >= 0 else 1.0
    return {
        'estimate': qbar, 'standard_error': se, 'ci_low': qbar - crit * se,
        'ci_high': qbar + crit * se, 'p_value': p, 'm_used': m,
        'within_variance': ubar, 'between_variance': between,
        'total_variance': total, 'df_rubin': df,
        'fraction_missing_information': fmi,
        'monte_carlo_error': math.sqrt(between / m) if m > 1 else 0.0,
    }


def bh_adjust(p: pd.Series) -> pd.Series:
    x = pd.to_numeric(p, errors='coerce')
    result = pd.Series(np.nan, index=x.index, dtype=float)
    valid = x.notna()
    if not valid.any():
        return result
    vals = x.loc[valid].to_numpy()
    order = np.argsort(vals)
    ranked = vals[order]
    adjusted = ranked * len(ranked) / np.arange(1, len(ranked) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0, 1)
    inverse = np.empty_like(order)
    inverse[order] = np.arange(len(order))
    result.loc[valid] = adjusted[inverse]
    return result


def prepare() -> tuple[pd.DataFrame, np.ndarray]:
    data = pd.read_csv(PANEL, low_memory=False)
    data = data.loc[data['cause_id'].eq('copd')].copy()
    data['county_fips'] = pd.to_numeric(data['county_fips'], errors='coerce')
    data['year'] = pd.to_numeric(data['year'], errors='coerce')
    data = data.dropna(subset=['county_fips', 'year', 'row_id', 'population']).copy()
    data['county_fips'] = data['county_fips'].astype('int64')
    data['year'] = data['year'].astype('int64')
    data['county_model'] = data['county_fips'].astype(str)
    data['year_model'] = data['year'].astype(str)
    data['state_year'] = data['state_abbr'].astype(str) + '_' + data['year_model']
    if 'population_density_km2' in data.columns:
        data['log_population_density'] = np.log1p(pd.to_numeric(data['population_density_km2'], errors='coerce'))
    else:
        data['log_population_density'] = np.nan
    standardize = {
        'age65_std_v63': 'age65_share',
        'density_std_v63': 'log_population_density',
        'drought_d1_fs_std_v63': 'drought_fireseason_D1',
        'drought_d2_fs_std_v63': 'drought_fireseason_D2',
        'pm25_total_std_v63': 'pm25_annual_mean',
        'ozone_std_v63': 'ozone_annual_mean',
        'temp_fs_std_v63': 'temperature_fireseason_mean',
        'smoking_std_v63': 'smoking_prevalence',
    }
    for out, source in standardize.items():
        data[out] = zscore(data[source]) if source in data.columns else np.nan
    draws = np.load(DRAWS)['draws']
    return data, draws


def fit_spec(
    data: pd.DataFrame,
    draws_all: np.ndarray,
    *,
    name: str,
    rhs: str,
    terms: list[str],
    required: list[str],
    year_min: int,
    year_max: int,
    filter_fn: Callable[[pd.DataFrame], pd.Series] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    needed = ['population', 'county_fips', 'year', 'row_id'] + required
    subset = data.loc[data['year'].between(year_min, year_max)].copy()
    if filter_fn is not None:
        subset = subset.loc[filter_fn(subset)].copy()
    subset = subset.dropna(subset=needed)
    subset = subset.loc[pd.to_numeric(subset['population'], errors='coerce') > 0].copy()
    if len(subset) < 500 or subset['county_fips'].nunique() < 30:
        raise RuntimeError(f'{name}: insufficient complete observations ({len(subset)} rows, {subset.county_fips.nunique()} counties)')

    design_frame = patsy.dmatrix(rhs, subset, return_type='dataframe')
    names = list(design_frame.columns)
    missing_terms = [t for t in terms if t not in names]
    if missing_terms:
        raise RuntimeError(f'{name}: missing target terms {missing_terms}; available sample={names[:20]}')
    design = np.asarray(design_frame, dtype=float)
    term_index = {t: names.index(t) for t in terms}
    row_index = subset['row_id'].astype(int).to_numpy()
    draws = draws_all[:, row_index]
    offset = np.log(subset['population'].to_numpy(float))
    groups = subset['county_fips'].to_numpy(int)
    mean_y = draws.mean(axis=0)

    pois = sm.GLM(mean_y, design, family=sm.families.Poisson(), offset=offset).fit(maxiter=150)
    mu = np.asarray(pois.fittedvalues, dtype=float)
    alpha = float(np.clip(np.sum((mean_y - mu) ** 2 - mean_y) / max(np.sum(mu ** 2), 1e-12), 0.001, 2.0))
    warm = sm.GLM(mean_y, design, family=sm.families.NegativeBinomial(alpha=alpha), offset=offset).fit(
        start_params=np.asarray(pois.params, dtype=float), maxiter=150
    )
    mean_parameters = np.asarray(warm.params, dtype=float)

    estimates: list[dict] = []
    failures: list[dict] = []
    for imputation, y in enumerate(draws, start=1):
        try:
            try:
                fit = sm.GLM(y, design, family=sm.families.NegativeBinomial(alpha=alpha), offset=offset).fit(
                    start_params=mean_parameters, maxiter=60, cov_type='cluster', cov_kwds={'groups': groups}
                )
                if not bool(fit.converged):
                    raise RuntimeError('warm-start IRLS did not converge')
            except Exception:
                fit = sm.GLM(y, design, family=sm.families.NegativeBinomial(alpha=alpha), offset=offset).fit(
                    maxiter=120, cov_type='cluster', cov_kwds={'groups': groups}
                )
            for term, idx in term_index.items():
                estimates.append({
                    'specification': name, 'imputation': imputation, 'term': term,
                    'estimate': float(fit.params[idx]), 'within_variance': float(fit.bse[idx] ** 2),
                    'converged': bool(fit.converged),
                })
        except Exception as exc:
            failures.append({'specification': name, 'imputation': imputation, 'error': repr(exc)})

    per = pd.DataFrame(estimates)
    if per.empty:
        raise RuntimeError(f'{name}: all imputation models failed')
    pooled_rows = []
    for term, g in per.groupby('term'):
        r = rubin_pool(g['estimate'], g['within_variance'])
        r.update({
            'specification': name, 'term': term, 'n_observations': int(len(subset)),
            'n_counties': int(subset['county_fips'].nunique()), 'year_min': int(subset['year'].min()),
            'year_max': int(subset['year'].max()), 'nb_alpha_fixed': alpha,
            'successful_imputations': int(g['imputation'].nunique()), 'n_parameters': int(design.shape[1]),
            'states_included': ','.join(sorted(subset['state_abbr'].astype(str).unique())),
        })
        r['irr'] = math.exp(r['estimate'])
        r['irr_ci_low'] = math.exp(r['ci_low'])
        r['irr_ci_high'] = math.exp(r['ci_high'])
        r['percent_change'] = (r['irr'] - 1) * 100
        r['percent_change_ci_low'] = (r['irr_ci_low'] - 1) * 100
        r['percent_change_ci_high'] = (r['irr_ci_high'] - 1) * 100
        pooled_rows.append(r)
    meta = {
        'specification': name, 'status': 'completed', 'n_observations': int(len(subset)),
        'n_counties': int(subset['county_fips'].nunique()), 'states': sorted(subset['state_abbr'].unique().tolist()),
        'year_min': int(subset['year'].min()), 'year_max': int(subset['year'].max()),
    }
    return pd.DataFrame(pooled_rows), per, pd.DataFrame(failures), meta


def main() -> None:
    data, draws = prepare()
    specs = [
        dict(
            name='M1_baseline_SES_fixed_2006_2020',
            rhs='pm25_iqr + pm25_iqr:ses_baseline_std + C(county_model) + C(year_model)',
            terms=['pm25_iqr', 'pm25_iqr:ses_baseline_std'], required=['pm25_iqr', 'ses_baseline_std'],
            year_min=2006, year_max=2020,
        ),
        dict(
            name='M2_Census_adjusted_2009_2020',
            rhs='pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + C(county_model) + C(year_model)',
            terms=['pm25_iqr', 'pm25_iqr:ses_baseline_std'],
            required=['pm25_iqr', 'ses_baseline_std', 'age65_std_v63', 'density_std_v63'], year_min=2009, year_max=2020,
        ),
        dict(
            name='M3_Census_state_year_FE_2009_2020',
            rhs='pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + C(county_model) + C(state_year)',
            terms=['pm25_iqr', 'pm25_iqr:ses_baseline_std'],
            required=['pm25_iqr', 'ses_baseline_std', 'age65_std_v63', 'density_std_v63'], year_min=2009, year_max=2020,
        ),
        dict(
            name='M4_Census_drought_adjusted_2009_2020',
            rhs='pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + drought_d1_fs_std_v63 + C(county_model) + C(year_model)',
            terms=['pm25_iqr', 'pm25_iqr:ses_baseline_std'],
            required=['pm25_iqr', 'ses_baseline_std', 'age65_std_v63', 'density_std_v63', 'drought_d1_fs_std_v63'],
            year_min=2009, year_max=2020,
        ),
        dict(
            name='M5_exclude_2020_Census_drought',
            rhs='pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + drought_d1_fs_std_v63 + C(county_model) + C(year_model)',
            terms=['pm25_iqr', 'pm25_iqr:ses_baseline_std'],
            required=['pm25_iqr', 'ses_baseline_std', 'age65_std_v63', 'density_std_v63', 'drought_d1_fs_std_v63'],
            year_min=2009, year_max=2019,
        ),
        dict(
            name='M6_timevarying_SES_2010_2020',
            rhs='pm25_iqr + ses_timevarying_std + pm25_iqr:ses_timevarying_std + age65_std_v63 + density_std_v63 + drought_d1_fs_std_v63 + C(county_model) + C(year_model)',
            terms=['pm25_iqr', 'pm25_iqr:ses_timevarying_std'],
            required=['pm25_iqr', 'ses_timevarying_std', 'age65_std_v63', 'density_std_v63', 'drought_d1_fs_std_v63'],
            year_min=2010, year_max=2020,
        ),
        dict(
            name='M7_lag1_Census_drought_2010_2020',
            rhs='pm25_lag1_iqr + pm25_lag1_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + drought_d1_fs_std_v63 + C(county_model) + C(year_model)',
            terms=['pm25_lag1_iqr', 'pm25_lag1_iqr:ses_baseline_std'],
            required=['pm25_lag1_iqr', 'ses_baseline_std', 'age65_std_v63', 'density_std_v63', 'drought_d1_fs_std_v63'],
            year_min=2010, year_max=2020,
        ),
        dict(
            name='M8_lead1_placebo_Census_drought_2009_2019',
            rhs='pm25_lead1_iqr + pm25_lead1_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + drought_d1_fs_std_v63 + C(county_model) + C(year_model)',
            terms=['pm25_lead1_iqr', 'pm25_lead1_iqr:ses_baseline_std'],
            required=['pm25_lead1_iqr', 'ses_baseline_std', 'age65_std_v63', 'density_std_v63', 'drought_d1_fs_std_v63'],
            year_min=2009, year_max=2019,
        ),
        dict(
            name='M9_three_state_air_sensitivity_2009_2020',
            rhs='pm25_iqr + pm25_iqr:ses_baseline_std + age65_std_v63 + density_std_v63 + drought_d1_fs_std_v63 + pm25_total_std_v63 + ozone_std_v63 + C(county_model) + C(year_model)',
            terms=['pm25_iqr', 'pm25_iqr:ses_baseline_std'],
            required=['pm25_iqr', 'ses_baseline_std', 'age65_std_v63', 'density_std_v63', 'drought_d1_fs_std_v63', 'pm25_total_std_v63', 'ozone_std_v63'],
            year_min=2009, year_max=2020, filter_fn=lambda d: d['state_abbr'].isin(['ID', 'OR', 'WA']),
        ),
    ]

    pooled_all, per_all, fail_all, status_rows = [], [], [], []
    for i, spec in enumerate(specs, start=1):
        print(f'[{i}/{len(specs)}] {spec["name"]}', flush=True)
        try:
            pooled, per, failures, meta = fit_spec(data, draws, **spec)
            pooled_all.append(pooled); per_all.append(per)
            if not failures.empty: fail_all.append(failures)
            status_rows.append(meta)
            interaction = pooled.loc[pooled['term'].str.contains(':', regex=False)]
            if not interaction.empty:
                r = interaction.iloc[0]
                print(f'  interaction={r.percent_change:.3f}% CI {r.percent_change_ci_low:.3f} to {r.percent_change_ci_high:.3f}; p={r.p_value:.4g}', flush=True)
        except Exception as exc:
            status_rows.append({'specification': spec['name'], 'status': 'failed', 'reason': repr(exc)})
            print(f'  FAILED: {exc}', flush=True)

    pooled = pd.concat(pooled_all, ignore_index=True) if pooled_all else pd.DataFrame()
    if not pooled.empty:
        interaction_mask = pooled['term'].str.contains(':', regex=False)
        pooled.loc[interaction_mask, 'p_fdr_bh_interactions'] = bh_adjust(pooled.loc[interaction_mask, 'p_value'])
        pooled.to_csv(TABLES / 'pooled_available_models_v6_3.csv', index=False, encoding='utf-8-sig')
    per = pd.concat(per_all, ignore_index=True) if per_all else pd.DataFrame()
    if not per.empty:
        per.to_csv(TABLES / 'per_imputation_available_models_v6_3.csv.gz', index=False, compression='gzip')
    failures = pd.concat(fail_all, ignore_index=True) if fail_all else pd.DataFrame(columns=['specification', 'imputation', 'error'])
    failures.to_csv(TABLES / 'model_failures_v6_3.csv', index=False, encoding='utf-8-sig')
    status = pd.DataFrame(status_rows)
    status.to_csv(TABLES / 'model_run_status_v6_3.csv', index=False, encoding='utf-8-sig')
    summary = {
        'completed': int((status.get('status') == 'completed').sum()) if 'status' in status else 0,
        'failed': int((status.get('status') == 'failed').sum()) if 'status' in status else 0,
        'result_file': 'tables/pooled_available_models_v6_3.csv',
        'important_scope_note': 'CDC-Air model is explicitly limited to Idaho, Oregon, and Washington because supplied files are incomplete for Arizona, California, and Colorado.',
    }
    (LOGS / 'model_status_v6_3.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
