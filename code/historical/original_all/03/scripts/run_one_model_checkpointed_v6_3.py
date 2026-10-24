from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm

ROOT = Path(os.environ.get('AFIRE_COUNTY_PROJECT_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'scripts'))
from run_available_models_v6_3 import prepare, rubin_pool
from run_one_model_v6_3 import SPECS

BASE_OUT = ROOT / 'logs' / 'model_results_v6_3'
BASE_OUT.mkdir(parents=True, exist_ok=True)


def prepare_spec(data: pd.DataFrame, draws: np.ndarray, spec: dict):
    subset = data.loc[data['year'].between(spec['year_min'], spec['year_max'])].copy()
    if spec.get('filter_fn') is not None:
        subset = subset.loc[spec['filter_fn'](subset)].copy()
    needed = ['population', 'county_fips', 'year', 'row_id'] + spec['required']
    subset = subset.dropna(subset=needed)
    subset = subset.loc[pd.to_numeric(subset['population'], errors='coerce') > 0].copy()
    if len(subset) < 500 or subset['county_fips'].nunique() < 30:
        raise RuntimeError(
            f"{spec['name']}: insufficient complete observations "
            f"({len(subset)} rows, {subset['county_fips'].nunique()} counties)"
        )
    design_frame = patsy.dmatrix(spec['rhs'], subset, return_type='dataframe')
    design_names = list(design_frame.columns)
    missing_terms = [term for term in spec['terms'] if term not in design_names]
    if missing_terms:
        raise RuntimeError(f"{spec['name']}: missing target terms {missing_terms}")
    design = np.asarray(design_frame, dtype=float)
    term_indices = {term: design_names.index(term) for term in spec['terms']}
    row_indices = subset['row_id'].astype(int).to_numpy()
    outcomes = draws[:, row_indices]
    offset = np.log(subset['population'].to_numpy(float))
    groups = subset['county_fips'].to_numpy(int)

    mean_outcome = outcomes.mean(axis=0)
    poisson = sm.GLM(mean_outcome, design, family=sm.families.Poisson(), offset=offset).fit(maxiter=150)
    expected = np.asarray(poisson.fittedvalues, dtype=float)
    alpha = float(
        np.clip(
            np.sum((mean_outcome - expected) ** 2 - mean_outcome) / max(np.sum(expected ** 2), 1e-12),
            0.001,
            2.0,
        )
    )
    warm = sm.GLM(
        mean_outcome,
        design,
        family=sm.families.NegativeBinomial(alpha=alpha),
        offset=offset,
    ).fit(start_params=np.asarray(poisson.params, dtype=float), maxiter=150)
    return subset, design, term_indices, outcomes, offset, groups, alpha, np.asarray(warm.params, dtype=float)


def fit_imputation(y, design, offset, groups, alpha, warm_params):
    errors = []
    for use_warm, maxiter in [(True, 60), (False, 140)]:
        try:
            kwargs = {'start_params': warm_params} if use_warm else {}
            fit = sm.GLM(
                y,
                design,
                family=sm.families.NegativeBinomial(alpha=alpha),
                offset=offset,
            ).fit(
                maxiter=maxiter,
                cov_type='cluster',
                cov_kwds={'groups': groups},
                **kwargs,
            )
            if not bool(fit.converged):
                raise RuntimeError(f'IRLS did not converge in {maxiter} iterations')
            return fit
        except Exception as exc:
            errors.append(repr(exc))
    raise RuntimeError(' | '.join(errors))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--index', type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.index <= len(SPECS):
        raise SystemExit(f'index must be between 1 and {len(SPECS)}')
    spec = SPECS[args.index - 1]
    name = spec['name']
    prefix = f'{args.index:02d}_{name}'
    spec_dir = BASE_OUT / prefix
    spec_dir.mkdir(parents=True, exist_ok=True)
    outer_status = BASE_OUT / f'{prefix}_status.json'
    print(f'Preparing {name}', flush=True)

    try:
        data, draws = prepare()
        subset, design, term_indices, outcomes, offset, groups, alpha, warm_params = prepare_spec(data, draws, spec)
    except Exception as exc:
        status = {'specification': name, 'status': 'blocked_or_failed', 'reason': repr(exc)}
        outer_status.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
        print(status, flush=True)
        return

    for imputation_index, outcome in enumerate(outcomes, start=1):
        checkpoint = spec_dir / f'imputation_{imputation_index:02d}.json'
        if checkpoint.exists():
            try:
                saved = json.loads(checkpoint.read_text(encoding='utf-8'))
                if saved.get('status') == 'completed':
                    print(f'  imputation {imputation_index:02d}/30 cached', flush=True)
                    continue
            except Exception:
                pass
        print(f'  imputation {imputation_index:02d}/30', flush=True)
        try:
            fit = fit_imputation(outcome, design, offset, groups, alpha, warm_params)
            estimates = {
                term: {
                    'estimate': float(fit.params[index]),
                    'within_variance': float(fit.bse[index] ** 2),
                }
                for term, index in term_indices.items()
            }
            payload = {
                'status': 'completed',
                'specification': name,
                'imputation': imputation_index,
                'converged': bool(fit.converged),
                'estimates': estimates,
            }
        except Exception as exc:
            payload = {
                'status': 'failed',
                'specification': name,
                'imputation': imputation_index,
                'error': repr(exc),
            }
        checkpoint.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    completed = []
    failures = []
    for checkpoint in sorted(spec_dir.glob('imputation_*.json')):
        payload = json.loads(checkpoint.read_text(encoding='utf-8'))
        if payload.get('status') == 'completed':
            for term, values in payload['estimates'].items():
                completed.append({
                    'specification': name,
                    'imputation': int(payload['imputation']),
                    'term': term,
                    'estimate': float(values['estimate']),
                    'within_variance': float(values['within_variance']),
                    'converged': bool(payload.get('converged', True)),
                })
        else:
            failures.append({
                'specification': name,
                'imputation': payload.get('imputation'),
                'error': payload.get('error', 'unknown'),
            })

    per = pd.DataFrame(completed)
    pd.DataFrame(failures).to_csv(BASE_OUT / f'{prefix}_failures.csv', index=False, encoding='utf-8-sig')
    if not per.empty:
        per.to_csv(BASE_OUT / f'{prefix}_per.csv.gz', index=False, compression='gzip')
    successful_imputations = int(per['imputation'].nunique()) if not per.empty else 0
    if successful_imputations < 20:
        status = {
            'specification': name,
            'status': 'incomplete',
            'successful_imputations': successful_imputations,
            'required_minimum': 20,
            'failed_imputations': len(failures),
        }
        outer_status.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
        print(status, flush=True)
        return

    pooled_rows = []
    for term, group in per.groupby('term'):
        result = rubin_pool(group['estimate'], group['within_variance'])
        result.update({
            'specification': name,
            'term': term,
            'n_observations': int(len(subset)),
            'n_counties': int(subset['county_fips'].nunique()),
            'year_min': int(subset['year'].min()),
            'year_max': int(subset['year'].max()),
            'states_included': ','.join(sorted(subset['state_abbr'].astype(str).unique())),
            'nb_alpha_fixed': alpha,
            'successful_imputations': successful_imputations,
            'n_parameters': int(design.shape[1]),
        })
        result['irr'] = math.exp(result['estimate'])
        result['irr_ci_low'] = math.exp(result['ci_low'])
        result['irr_ci_high'] = math.exp(result['ci_high'])
        result['percent_change'] = (result['irr'] - 1) * 100
        result['percent_change_ci_low'] = (result['irr_ci_low'] - 1) * 100
        result['percent_change_ci_high'] = (result['irr_ci_high'] - 1) * 100
        pooled_rows.append(result)
    pooled = pd.DataFrame(pooled_rows)
    pooled.to_csv(BASE_OUT / f'{prefix}_pooled.csv', index=False, encoding='utf-8-sig')
    status = {
        'specification': name,
        'status': 'completed',
        'successful_imputations': successful_imputations,
        'failed_imputations': len(failures),
        'n_observations': int(len(subset)),
        'n_counties': int(subset['county_fips'].nunique()),
    }
    outer_status.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    interaction = pooled.loc[pooled['term'].astype(str).str.contains(':', regex=False)]
    if not interaction.empty:
        row = interaction.iloc[0]
        print(
            f"Completed {name}: interaction={row['percent_change']:.3f}% "
            f"({row['percent_change_ci_low']:.3f}, {row['percent_change_ci_high']:.3f}), "
            f"p={row['p_value']:.5g}",
            flush=True,
        )


if __name__ == '__main__':
    main()
