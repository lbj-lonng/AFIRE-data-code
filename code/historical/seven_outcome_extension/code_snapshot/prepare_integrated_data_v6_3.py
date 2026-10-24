from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get('AFIRE_COUNTY_PROJECT_ROOT', Path(__file__).resolve().parents[1]))
RAW = ROOT / 'data_external' / 'raw'
OUT = ROOT / 'data_external' / 'processed'
DATA = ROOT / 'data_processed'
TABLES = ROOT / 'tables'
LOGS = ROOT / 'logs'
for p in (OUT, TABLES, LOGS):
    p.mkdir(parents=True, exist_ok=True)

BASE = DATA / 'county_year_disease_panel_base_v5.csv'
SES_SOURCE = ROOT / 'data_reference' / 'county_year_ses.csv'
SMOKE_SOURCE = ROOT / 'data_reference' / 'county_year_smoke_pm25.csv'
STUDY_STATES = {'AZ', 'CA', 'CO', 'ID', 'OR', 'WA'}
STATE_FIPS = {4, 6, 8, 16, 41, 53}


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors='coerce')


def zscore(s: pd.Series) -> pd.Series:
    x = num(s)
    sd = x.std(ddof=1)
    if not np.isfinite(sd) or sd <= 0:
        return pd.Series(np.nan, index=s.index)
    return (x - x.mean()) / sd


def parse_cdc_dates(s: pd.Series) -> pd.Series:
    raw = s.astype(str).str.strip()
    result = pd.Series(pd.NaT, index=raw.index, dtype='datetime64[ns]')
    for fmt in ['%d%b%Y', '%Y-%m-%d', '%m/%d/%Y', '%d-%b-%Y', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S']:
        mask = result.isna()
        if not mask.any():
            break
        result.loc[mask] = pd.to_datetime(raw.loc[mask], format=fmt, errors='coerce')
    mask = result.isna()
    if mask.any():
        try:
            result.loc[mask] = pd.to_datetime(raw.loc[mask], format='mixed', errors='coerce')
        except (TypeError, ValueError):
            result.loc[mask] = pd.to_datetime(raw.loc[mask], errors='coerce')
    return result


def build_census() -> pd.DataFrame:
    # Use the dedicated validated Census implementation and existing cache.
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    from census_acquisition import build_standardized_census, validate_standardized_census

    census = build_standardized_census()
    validate_standardized_census(census)
    census.to_csv(OUT / 'census_county_year_six_states_2009_2020.csv', index=False, encoding='utf-8-sig')
    keep = [
        'county_fips', 'year', 'acs_population', 'age65_share',
        'acs_median_household_income', 'acs_poverty_rate',
        'land_area_km2_2020', 'population_density_km2',
        'acs_vintage', 'acs_period_label',
    ]
    return census[[c for c in keep if c in census.columns]].copy()


def build_drought() -> pd.DataFrame:
    """Convert supplied monthly D0-D4 county files into honest drought indicators.

    D0-D4 are retained as cumulative drought-category area percentages. They are
    never renamed or used as temperature. Annual and May-October means are built.
    """
    folder = RAW / 'noaa_nclimdiv_county'
    rows: list[pd.DataFrame] = []
    for path in sorted(folder.glob('*.csv')):
        match = re.search(r'(\d{5})', path.stem)
        if not match:
            continue
        fips = int(match.group(1))
        data = pd.read_csv(path)
        if 'DATE' not in data.columns or not {'D0', 'D1', 'D2', 'D3', 'D4'}.issubset(data.columns):
            continue
        date_text = data['DATE'].astype(str).str.extract(r'((?:19|20)\d{6})', expand=False)
        data['date'] = pd.to_datetime(date_text, format='%Y%m%d', errors='coerce')
        data = data.loc[data['date'].notna()].copy()
        data['year'] = data['date'].dt.year
        data['month'] = data['date'].dt.month
        data = data.loc[data['year'].between(2006, 2020)].copy()
        for col in ['D0', 'D1', 'D2', 'D3', 'D4']:
            data[col] = num(data[col])
        if data.empty:
            continue
        annual = data.groupby('year')[['D0', 'D1', 'D2', 'D3', 'D4']].mean().add_prefix('drought_annual_')
        fire = (
            data.loc[data['month'].between(5, 10)]
            .groupby('year')[['D0', 'D1', 'D2', 'D3', 'D4']]
            .mean()
            .add_prefix('drought_fireseason_')
        )
        merged = annual.join(fire, how='outer').reset_index()
        merged['county_fips'] = fips
        rows.append(merged)
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    out = out.drop_duplicates(['county_fips', 'year']).sort_values(['county_fips', 'year'])
    out.to_csv(OUT / 'county_year_drought_categories_v6_3.csv', index=False, encoding='utf-8-sig')
    return out



def build_true_noaa() -> pd.DataFrame:
    path = RAW / 'noaa_cag_county_year.csv'
    if not path.exists():
        return pd.DataFrame()
    data = pd.read_csv(path)
    if not {'county_fips', 'year'}.issubset(data.columns):
        return pd.DataFrame()
    data['county_fips'] = num(data['county_fips']).astype('Int64')
    data['year'] = num(data['year']).astype('Int64')
    allowed = [
        'temperature_annual_mean', 'temperature_fireseason_mean',
        'precipitation_annual_total', 'precipitation_fireseason_total',
        'pdsi_annual_mean', 'pdsi_fireseason_mean',
    ]
    present = [c for c in allowed if c in data.columns]
    return data[['county_fips', 'year'] + present].drop_duplicates(['county_fips', 'year'])


def build_air(kind: str) -> pd.DataFrame:
    folder = RAW / f'cdc_{kind}'
    value_candidates = ['pm25_pop_pred', 'pm25_mean_pred'] if kind == 'pm25' else ['o3_pop_pred', 'o3_mean_pred']
    rows: list[pd.DataFrame] = []
    for path in sorted(folder.glob(f'{kind}_county_daily_*.csv')):
        data = pd.read_csv(path, low_memory=False)
        if not {'year', 'date', 'statefips', 'countyfips'}.issubset(data.columns):
            continue
        value_col = next((c for c in value_candidates if c in data.columns), None)
        if value_col is None:
            continue
        state = num(data['statefips']).astype('Int64')
        county = num(data['countyfips']).astype('Int64')
        data['county_fips'] = num(state.astype(str).str.zfill(2) + county.astype(str).str.zfill(3)).astype('Int64')
        data['year'] = num(data['year']).astype('Int64')
        data['date_parsed'] = parse_cdc_dates(data['date'])
        data['value'] = num(data[value_col])
        data = data.loc[state.isin(STATE_FIPS) & data['year'].between(2006, 2020)].copy()
        annual = data.groupby(['county_fips', 'year'], as_index=False)['value'].mean().rename(columns={'value': f'{kind}_annual_mean'})
        fire = (
            data.loc[data['date_parsed'].dt.month.between(5, 10)]
            .groupby(['county_fips', 'year'], as_index=False)['value']
            .mean()
            .rename(columns={'value': f'{kind}_fireseason_mean'})
        )
        rows.append(annual.merge(fire, on=['county_fips', 'year'], how='left', validate='one_to_one'))
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    value_cols = [c for c in out.columns if c not in {'county_fips', 'year'}]
    out = out.groupby(['county_fips', 'year'], as_index=False)[value_cols].mean()
    out.to_csv(OUT / f'county_year_{kind}_available_v6_3.csv', index=False, encoding='utf-8-sig')
    return out


def build_ses() -> tuple[pd.DataFrame, pd.DataFrame]:
    ses = pd.read_csv(SES_SOURCE, low_memory=False)
    ses = ses.loc[ses['state_abbr'].isin(STUDY_STATES)].copy()
    ses['county_fips'] = num(ses['county_fips']).astype('Int64')
    ses['period_end'] = num(ses['period_end']).astype('Int64')

    baseline = ses.loc[ses['period'].eq('2006_2010')].copy()
    baseline = baseline.drop_duplicates('county_fips')
    baseline['ses_baseline_std'] = zscore(baseline['ses_disadvantage_z'])
    baseline['poverty_baseline_std'] = zscore(baseline['poverty_rate'])
    baseline_keep = [
        'county_fips', 'period', 'ses_disadvantage_z', 'ses_baseline_std',
        'poverty_rate', 'poverty_baseline_std', 'median_household_income',
        'unemployment_rate', 'less_than_hs_rate', 'nonwhite_rate', 'hispanic_rate',
    ]
    baseline = baseline[baseline_keep]
    baseline.to_csv(OUT / 'county_ses_baseline_2006_2010_v6_3.csv', index=False, encoding='utf-8-sig')

    tv = ses.loc[ses['period_end'].between(2010, 2020)].copy()
    tv['year'] = tv['period_end'].astype(int)
    tv['ses_timevarying_std'] = zscore(tv['ses_disadvantage_z'])
    tv['poverty_timevarying_std'] = zscore(tv['poverty_rate'])
    tv_keep = [
        'county_fips', 'year', 'period', 'ses_disadvantage_z', 'ses_timevarying_std',
        'poverty_rate', 'poverty_timevarying_std', 'median_household_income',
        'unemployment_rate', 'less_than_hs_rate', 'nonwhite_rate', 'hispanic_rate',
    ]
    tv = tv[tv_keep].drop_duplicates(['county_fips', 'year'])
    tv.to_csv(OUT / 'county_year_ses_timevarying_2010_2020_v6_3.csv', index=False, encoding='utf-8-sig')
    return baseline, tv


def build_covariate_panel(census: pd.DataFrame, drought: pd.DataFrame, true_noaa: pd.DataFrame, pm25: pd.DataFrame, ozone: pd.DataFrame) -> pd.DataFrame:
    key = pd.read_csv(BASE, usecols=['county_fips', 'year']).drop_duplicates()
    key['county_fips'] = num(key['county_fips']).astype('Int64')
    key['year'] = num(key['year']).astype('Int64')
    out = key.sort_values(['county_fips', 'year']).copy()
    for part in [census, drought, true_noaa, pm25, ozone]:
        if not part.empty:
            part = part.copy()
            part['county_fips'] = num(part['county_fips']).astype('Int64')
            part['year'] = num(part['year']).astype('Int64')
            out = out.merge(part, on=['county_fips', 'year'], how='left', validate='one_to_one')

    places = RAW / 'cdc_places_smoking_county_year.csv'
    if places.exists():
        p = pd.read_csv(places)
        p['county_fips'] = num(p['county_fips']).astype('Int64')
        p['year'] = num(p['year']).astype('Int64')
        out = out.merge(p.drop_duplicates(['county_fips', 'year']), on=['county_fips', 'year'], how='left', validate='one_to_one')

    smoke = pd.read_csv(SMOKE_SOURCE).rename(columns={'GEOID': 'county_fips'})
    smoke['county_fips'] = num(smoke['county_fips']).astype('Int64')
    smoke['year'] = num(smoke['year']).astype('Int64')
    smoke_cols = [
        'county_fips', 'year', 'county_smoke_pm25_annual_burden', 'county_smoke_days',
        'county_smoke_pm25_mean_smoke_days', 'county_smoke_pm25_max',
    ]
    out = out.merge(smoke[smoke_cols].drop_duplicates(['county_fips', 'year']), on=['county_fips', 'year'], how='left', validate='one_to_one')
    if 'pm25_annual_mean' in out.columns:
        out['nonwildfire_pm25_candidate'] = out['pm25_annual_mean'] - out['county_smoke_pm25_annual_burden']
        out['nonwildfire_negative_flag'] = out['nonwildfire_pm25_candidate'].lt(0)
    out.to_csv(OUT / 'county_year_real_covariates_v6_3.csv', index=False, encoding='utf-8-sig')
    # Backward-compatible filename for original scripts.
    out.to_csv(OUT / 'county_year_real_covariates_v6.csv', index=False, encoding='utf-8-sig')
    return out


def build_analysis_panel(cov: pd.DataFrame, baseline: pd.DataFrame, tv: pd.DataFrame) -> pd.DataFrame:
    base = pd.read_csv(BASE, low_memory=False)
    base['county_fips'] = num(base['county_fips']).astype('Int64')
    base['year'] = num(base['year']).astype('Int64')
    out = base.merge(baseline, on='county_fips', how='left', validate='many_to_one', suffixes=('', '_baseline'))
    out = out.merge(tv, on=['county_fips', 'year'], how='left', validate='many_to_one', suffixes=('', '_tv'))
    out = out.merge(cov, on=['county_fips', 'year'], how='left', validate='many_to_one')
    out.to_csv(DATA / 'county_year_disease_panel_v6_3.csv', index=False, encoding='utf-8-sig')
    return out


def coverage_table(cov: pd.DataFrame) -> pd.DataFrame:
    specs = {
        'age65_share_2009_2020': ('age65_share', 2009, 2020),
        'population_density_km2_2009_2020': ('population_density_km2', 2009, 2020),
        'drought_fireseason_D1_2006_2020': ('drought_fireseason_D1', 2006, 2020),
        'temperature_fireseason_mean_2006_2020': ('temperature_fireseason_mean', 2006, 2020),
        'pm25_annual_mean_2006_2020': ('pm25_annual_mean', 2006, 2020),
        'ozone_annual_mean_2006_2020': ('ozone_annual_mean', 2006, 2020),
        'smoking_prevalence_2018_2020': ('smoking_prevalence', 2018, 2020),
    }
    rows = []
    for name, (var, start, end) in specs.items():
        x = cov.loc[cov['year'].between(start, end)]
        nonmissing = x[var].notna() if var in x.columns else pd.Series(False, index=x.index)
        rows.append({
            'metric': name,
            'variable': var,
            'year_min': start,
            'year_max': end,
            'nonmissing_n': int(nonmissing.sum()),
            'expected_n': int(len(x)),
            'coverage_pct': float(nonmissing.mean() * 100) if len(x) else 0.0,
            'counties_with_data': int(x.loc[nonmissing, 'county_fips'].nunique()) if len(x) else 0,
            'six_state_main_model_eligible': bool(nonmissing.mean() >= 0.95) if len(x) else False,
        })
    frame = pd.DataFrame(rows)
    frame.to_csv(TABLES / 'integrated_data_coverage_v6_3.csv', index=False, encoding='utf-8-sig')
    return frame


def main() -> None:
    census = build_census()
    drought = build_drought()
    true_noaa = build_true_noaa()
    pm25 = build_air('pm25')
    ozone = build_air('ozone')
    baseline, tv = build_ses()
    cov = build_covariate_panel(census, drought, true_noaa, pm25, ozone)
    analysis = build_analysis_panel(cov, baseline, tv)
    coverage = coverage_table(cov)

    status = {
        'status': 'ready_for_available_models',
        'rows_covariates': int(len(cov)),
        'rows_analysis': int(len(analysis)),
        'counties': int(cov['county_fips'].nunique()),
        'years': [int(cov['year'].min()), int(cov['year'].max())],
        'census_included_and_validated': bool(coverage.loc[coverage['variable'].eq('age65_share'), 'coverage_pct'].iloc[0] >= 99),
        'drought_included_as_drought_not_temperature': True,
        'cdc_air_is_partial_three_state_sensitivity_only': bool(coverage.loc[coverage['variable'].eq('pm25_annual_mean'), 'coverage_pct'].iloc[0] < 95),
        'temperature_available': bool('temperature_fireseason_mean' in cov.columns and cov['temperature_fireseason_mean'].notna().mean() >= 0.95),
        'notes': [
            'The supplied NOAA D0-D4 files are used only as drought-category area percentages.',
            'The supplied CDC-Air files are not used in six-state models unless coverage reaches 95%.',
            'NHGIS 2006-2010 is used as fixed baseline SES; time-varying SES uses period_end 2010-2020.',
        ],
    }
    (LOGS / 'integrated_data_status_v6_3.json').write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(status, ensure_ascii=False, indent=2))
    print(coverage.to_string(index=False))


if __name__ == '__main__':
    main()
