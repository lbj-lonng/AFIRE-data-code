"""Read-only scientific audit; copy scoped source data without fitting or sampling.

Writes only this new version's audit files and source-data copies. Original arrays
are read in place and never exported into the public submission directory.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
import re
import shutil
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent / 'AFIRE_2009_2020_five_outcomes_20260915_194616'
PROJECT = ROOT.parent.parent
AUTH = PROJECT / 'AFIRE_7outcome_extension_20260911_234642_lTDb'
SD = BASE / 'submission/source_data'
F = SD / 'full_results'
INP = BASE / 'audit/inputs'
AUD = ROOT / 'audit'
DEST = ROOT / 'submission/source_data'
IDS = ['copd', 'chronic_lower_respiratory', 'respiratory_system', 'circulatory_system', 'ischemic_heart_disease']
KEY = ['outcome_id', 'analysis_block', 'model_id', 'contrast_id']
NUM = []
SCOPE = []
MANIFEST = []
USED = {}
FACTS = {}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def touch(path):
    path = Path(path)
    if str(path) not in USED:
        USED[str(path)] = sha(path)
    return path


def read(path):
    return pd.read_csv(touch(path), float_precision='round_trip', dtype={'county_fips': str, 'state_fips': str})


def eq(a, b):
    if pd.isna(a) and pd.isna(b):
        return True
    return bool(a == b)


def check(name, good, observed='', expected='', group='numerical'):
    target = SCOPE if group == 'scope' else NUM
    target.append(dict(check=name, status='PASS' if good else 'FAIL', observed=str(observed), expected=str(expected)))
    return bool(good)


def save_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False, encoding='utf-8-sig')


def audit_health():
    frozen = read(AUTH / 'AFIRE_7outcome_all_results.csv')
    cached = read(INP / 'tables/AFIRE_7outcome_all_results.csv')
    current = read(F / 'health_results.csv')
    check('original_and_cached_health_table_sha256', sha(AUTH / 'AFIRE_7outcome_all_results.csv') == sha(INP / 'tables/AFIRE_7outcome_all_results.csv'), sha(AUTH / 'AFIRE_7outcome_all_results.csv'), sha(INP / 'tables/AFIRE_7outcome_all_results.csv'))
    relevant = frozen.loc[frozen.outcome_id.isin(IDS)].copy()
    for tag, d in [('original', relevant), ('current', current)]:
        check(f'{tag}_health_unique_keys', not d.duplicated(KEY).any(), len(d), 135)
    c = current.set_index(KEY).sort_index()
    r = relevant.set_index(KEY).sort_index()
    check('health_key_set_exact', c.index.equals(r.index), len(c), len(r))
    fields = [v for v in c.columns if v in r.columns and v != 'comparison_family']
    for k in c.index:
        if k not in r.index:
            continue
        for field in fields:
            a, b = c.loc[k, field], r.loc[k, field]
            check('health:' + '|'.join(map(str, k)) + ':' + field, eq(a, b), a, b)
    blocks = current.groupby('analysis_block').size().to_dict()
    check('health_block_counts', blocks == {'A': 5, 'B': 25, 'C': 40, 'D': 25, 'E': 40}, blocks, 'A5 B25 C40 D25 E40')
    a = current[current.analysis_block.eq('A')]
    check('A_saved_family_label', a.comparison_family.eq('original_Holm_family_n7').all(), a.comparison_family.unique(), 'original_Holm_family_n7')
    config = json.loads(touch(BASE / 'scripts/scope_config.yaml').read_text(encoding='utf-8'))
    check('Holm_family_size_unchanged', config['original_holm_family_size'] == 7, config['original_holm_family_size'], 7)
    check('fixed_smoke_iqr', config['smoke_iqr'] == 0.678107947271523, config['smoke_iqr'], 0.678107947271523)
    check('all_health_30_allocations', current.n_imputations.eq(30).all(), current.n_imputations.unique(), 30)
    for block, name in [('A', 'primary'), ('B', 'conditional'), ('C', 'common_sample'), ('D', 'targeted_omissions'), ('E', 'LST_pairs')]:
        split = read(F / f'{name}.csv').set_index(KEY).sort_index()
        expected = current[current.analysis_block.eq(block)].set_index(KEY).sort_index()
        same = split.index.equals(expected.index) and split.columns.equals(expected.columns)
        if same:
            same = all(eq(x, y) for x, y in zip(split.to_numpy().ravel(), expected.to_numpy().ravel()))
        check('split_exact_' + block, same, len(split), len(expected))
    b = current[current.analysis_block.eq('B')]
    FACTS.update(health_rows=len(current), health_fields_compared=fields, conditional_rows=len(b),
                 conditional_negative=int(b.CI_percent_upper.lt(0).sum()),
                 conditional_cross_zero=int((b.CI_percent_lower.le(0) & b.CI_percent_upper.ge(0)).sum()),
                 conditional_positive=int(b.CI_percent_lower.gt(0).sum()))
    return frozen


def audit_descriptive():
    m = read(F / 'mortality_records.csv')
    raw = read(INP / 'mortality_panel.csv')
    raw = raw[raw.year.between(2009, 2020) & raw.cause_id.isin(IDS)].copy()
    raw.county_fips = raw.county_fips.str.zfill(5)
    left = m.sort_values('row_id').reset_index(drop=True)
    right = raw[m.columns].sort_values('row_id').reset_index(drop=True)
    for col in m.columns:
        check('public_mortality_source_' + col, all(eq(x, y) for x, y in zip(left[col], right[col])), len(left), len(right))
    check('mortality_15360', len(m) == 15360, len(m), 15360)
    check('mortality_unique_county_year_cause', not m.duplicated(['county_fips', 'year', 'cause_id']).any(), len(m), 15360)
    check('mortality_5x3072', m.groupby('cause_id').size().eq(3072).all(), m.groupby('cause_id').size().to_dict(), 3072)
    check('mortality_256_counties', m.county_fips.nunique() == 256, m.county_fips.nunique(), 256)
    check('mortality_suppressed_blank_not_zero', m.loc[m.death_suppressed, 'deaths'].isna().all(), int(m.death_suppressed.sum()), 3328)
    check('mortality_public_zero_count', m.deaths.eq(0).sum() == 325, int(m.deaths.eq(0).sum()), 325)
    ex = read(F / 'county_year_exposure.csv')
    check('county_year_exposure_unique_3072', len(ex) == 3072 and not ex.duplicated(['county_fips', 'year']).any(), len(ex), 3072)
    check('county_exposure_derived_without_repeated_cause_weighting', ex.sort_values(['county_fips', 'year']).reset_index(drop=True).equals(raw[ex.columns].drop_duplicates().sort_values(['county_fips', 'year']).reset_index(drop=True)), len(ex), 'unique county-years')
    check('county_fixed_disadvantage', ex.groupby('county_fips').ses_baseline_std.nunique().eq(1).all(), 256, 'all counties fixed')
    check('county_fixed_quintile', ex.groupby('county_fips').baseline_ses_quintile.nunique().eq(1).all(), 256, 'all counties fixed')
    counts = ex[['county_fips', 'state_abbr']].drop_duplicates().groupby('state_abbr').size().to_dict()
    check('county_counts_by_state', counts == {'AZ': 15, 'CA': 58, 'CO': 64, 'ID': 44, 'OR': 36, 'WA': 39}, counts, 'AZ15 CA58 CO64 ID44 OR36 WA39')
    annual = read(F / 'annual.csv').set_index('year')
    def gini(x):
        values = np.sort(np.asarray(x, float))
        return 2 * np.dot(np.arange(1, len(values) + 1), values) / (len(values) * values.sum()) - (len(values) + 1) / len(values)
    for year, g in ex.groupby('year'):
        x = g.county_smoke_pm25_annual_burden_y
        vals = dict(n_counties=len(g), population=g.population.sum(), population_weighted_smoke=np.average(x, weights=g.population), county_mean=x.mean(), county_median=x.median(), county_p10=x.quantile(.1), county_p90=x.quantile(.9), unweighted_county_gini=gini(x))
        for field, value in vals.items():
            check(f'county_annual_{year}_{field}', abs(value - annual.loc[year, field]) < 1e-8, value, annual.loc[year, field])
    cmap = read(F / 'county_map_values.csv').set_index('county_fips')
    means = ex.groupby('county_fips').county_smoke_pm25_annual_burden_y.mean()
    for fips, g in m.groupby('county_fips'):
        vals = dict(n_records=len(g), n_years=g.year.nunique(), n_causes=g.cause_id.nunique(), suppressed_records=g.death_suppressed.sum(), suppressed_record_percent=g.death_suppressed.mean() * 100, smoke_mean=means.loc[fips])
        for field, value in vals.items():
            check(f'county_map_{fips}_{field}', abs(value - cmap.loc[fips, field]) < 1e-12, value, cmap.loc[fips, field])
    geographic = json.loads(touch(SD / 'geography/counties_256_epsg5070.geojson').read_text(encoding='utf-8'))
    geographic_keys = [feature['properties']['county_fips'] for feature in geographic['features']]
    check('geography_256_unique_exact_FIPS', len(geographic_keys) == len(set(geographic_keys)) == 256 and set(geographic_keys) == set(m.county_fips), len(geographic_keys), 256)
    check('geography_no_diagnosis_fields', all(not any('cause' in field or 'outcome' in field for field in feature['properties']) for feature in geographic['features']), 'identifier-only properties', 'no diagnosis values')
    st = read(F / 'state_year_exposure.csv')
    allst = read(F / 'state_year_exposure_with_missing.csv')
    check('observed_state_years_588', len(st) == 588 and st.state_abbr.nunique() == 49 and not st.duplicated(['state_abbr', 'year']).any(), len(st), '49 x 12 = 588')
    check('DC_included', 'DC' in set(st.state_abbr), sorted(set(st.state_abbr))[-3:], 'DC included')
    check('AK_HI_missing_24_not_zero', len(allst[allst.state_abbr.isin(['AK', 'HI'])]) == 24 and allst.loc[allst.state_abbr.isin(['AK', 'HI']), 'smoke_pm25_annual_burden'].isna().all(), 24, 'all missing')
    state_original = read(INP / 'tables/state_year_exposure_verified.csv')
    state_original = state_original[state_original.year.between(2009, 2020)]
    check('state_exposure_original_values_unchanged', st.sort_values(['state_fips', 'year']).reset_index(drop=True).equals(state_original[st.columns].sort_values(['state_fips', 'year']).reset_index(drop=True)), len(st), len(state_original))
    state_ann = read(F / 'state_annual.csv').set_index('year')
    for year, g in st.groupby('year'):
        x = g.smoke_pm25_annual_burden
        vals = dict(n_units=len(g), state_mean=x.mean(), state_median=x.median(), state_p10=x.quantile(.1), state_p90=x.quantile(.9), equal_state_gini=gini(x))
        for field, value in vals.items():
            check(f'state_annual_{year}_{field}', abs(value - state_ann.loc[year, field]) < 1e-12, value, state_ann.loc[year, field])
    bridge = read(F / 'state_county_bridge.csv')
    check('bridge_72_unique', len(bridge) == 72 and not bridge.duplicated(['state_abbr', 'year']).any(), len(bridge), 72)
    for (state, year), g in ex.groupby(['state_abbr', 'year']):
        row = bridge[(bridge.state_abbr == state) & (bridge.year == year)].iloc[0]
        value = np.average(g.county_smoke_pm25_annual_burden_y, weights=g.population)
        check(f'bridge_population_weight_{state}_{year}', abs(value - row.population_weighted_smoke) < 1e-12, value, row.population_weighted_smoke)
    rem = read(F / 'state_death_remainders.csv')
    check('state_death_groups_360', len(rem) == 360, len(rem), 360)
    for k, g in m.groupby(['state_abbr', 'year', 'cause_id']):
        hidden = g.state_deaths.iloc[0] - g.deaths.sum()
        n = int(g.death_suppressed.sum())
        check('remainder_feasible_' + '|'.join(map(str, k)), n <= hidden <= 9 * n, hidden, f'{n} to {9*n}')
    cat = read(F / 'fire_catalogue_subset.csv')
    fa = read(F / 'fire_record_state_assignments.csv')
    original_cat = read(INP / 'state_panels/top100_catalogue.csv')
    original_cat = original_cat[original_cat.FIRE_YEAR_INT.between(2009, 2020)]
    check('fire_catalogue_preserved_no_reranking', cat.reset_index(drop=True).equals(original_cat[cat.columns].reset_index(drop=True)), len(cat), len(original_cat))
    original_assignments = read(INP / 'state_panels/top100_record_state_assignments.csv')
    original_assignments = original_assignments[original_assignments.year.between(2009, 2020)]
    check('fire_original_assignment_rule_preserved', fa.reset_index(drop=True).equals(original_assignments[fa.columns].reset_index(drop=True)), len(fa), len(original_assignments))
    six = fa.loc[fa.in_six_state_region]
    for name, count, wanted in [('fire_records', len(cat), 81), ('fire_assignments', len(fa), 89), ('fire_six_assignments', len(six), 55), ('fire_six_unique_records', six.catalogue_rank.nunique(), 53)]:
        check(name, count == wanted, count, wanted)
        FACTS[name] = int(count)
    check('fire_assignment_records_same_as_catalogue', set(fa.catalogue_rank) == set(cat.Rank), len(set(fa.catalogue_rank)), 81)
    FACTS.update(state_years=len(st), counties=m.county_fips.nunique(), county_years=len(ex), mortality_records=len(m), suppressed_records=int(m.death_suppressed.sum()), public_zero_records=int(m.deaths.eq(0).sum()), state_death_groups=len(rem), bridge_pairs=len(bridge), county_counts=counts)
    return m, raw


def audit_validation():
    v = read(F / 'validation_evaluation_records.csv')
    source = read(INP / 'validation_predictions.csv')
    source = source[source.year.between(2009, 2020) & source.cause_id.isin(IDS)]
    vk = ['state_abbr', 'year', 'cause_id', 'county_fips']
    fullkey = vk + ['method']
    a = v.sort_values(fullkey).reset_index(drop=True)
    b = source[v.columns].sort_values(fullkey).reset_index(drop=True)
    for col in v.columns:
        check('validation_saved_source_' + col, all(eq(x, y) for x, y in zip(a[col], b[col])), len(a), len(b))
    check('validation_unique_method_cells', not v.duplicated(fullkey).any(), len(v), 8512)
    methods = ['equal', 'population', 'loyo_fixed_EB', 'loyo_hierarchical_EB']
    sets = [set(map(tuple, v[v.method.eq(method)][vk].to_numpy())) for method in methods]
    check('validation_four_methods_same_keys', all(s == sets[0] for s in sets), [len(s) for s in sets], [2128] * 4)
    check('validation_298_groups', v.pseudo_group_id.nunique() == 298, v.pseudo_group_id.nunique(), 298)
    check('validation_visible_support_10_19', v.true_visible_count.between(10, 19).all(), [v.true_visible_count.min(), v.true_visible_count.max()], '10 to 19')
    check('validation_saved_100_draws_support_0_19', set(v.n_draws) == {100} and set(v.support) == {'0-19'}, [list(v.n_draws.unique()), list(v.support.unique())], '100; 0-19')
    summaries = read(F / 'validation.csv').set_index(['scope', 'method'])
    metrics = {'MAE': ('absolute_error', 'mean'), 'coverage_95': ('interval_covers_truth', 'mean'), 'mean_interval_width': ('interval_width', 'mean'), 'mean_CRPS': ('CRPS', 'mean'), 'mean_interval_score_95': ('interval_score_95', 'mean')}
    for scope, scoped in [('all_outcomes', v)] + [(oid, v[v.cause_id.eq(oid)]) for oid in IDS]:
        for method in methods:
            g = scoped[scoped.method.eq(method)]
            saved = summaries.loc[(scope, method)]
            vals = {name: float(g[col].mean()) for name, (col, _) in metrics.items()}
            vals['RMSE'] = float(np.sqrt(g.squared_error.mean()))
            vals['n_cells'] = len(g)
            vals['n_groups'] = g.pseudo_group_id.nunique()
            for field, value in vals.items():
                check(f'validation_summary_{scope}_{method}_{field}', abs(value - saved[field]) < 1e-12, value, saved[field])
    FACTS.update(validation_cells=len(sets[0]), validation_groups=v.pseudo_group_id.nunique(), validation_method_rows=len(v), validation_overall=summaries.loc['all_outcomes'].reset_index().to_dict('records'))


def audit_arrays(m, raw):
    array_path = touch(INP / 'five_outcome_existing_allocations.npz')
    provenance = json.loads(touch(BASE / 'audit/allocation_source.json').read_text(encoding='utf-8'))
    check('allocation_subset_archive_identity', sha(array_path) == provenance['subset_cache_sha256'], sha(array_path), provenance['subset_cache_sha256'])
    z = np.load(array_path, allow_pickle=False)
    lookup = {int(r): i for i, r in enumerate(z['row_ids'])}
    counts = z['draws'][:, [lookup[int(r)] for r in m.row_id]]
    archive = touch(Path(provenance['source_path']))
    with tarfile.open(archive, 'r:gz') as tar:
        member = tar.getmember(provenance['member'])
        if not member.isfile() or member.issym() or member.islnk():
            raise RuntimeError('Allocation archive member is not a regular file')
        blob = tar.extractfile(member).read()
    original_hash = hashlib.sha256(blob).hexdigest()
    check('original_archive_member_hash', original_hash == provenance['member_sha256'], original_hash, provenance['member_sha256'])
    original = np.load(io.BytesIO(blob), allow_pickle=False)
    original_lookup = {int(r): i for i, r in enumerate(original['row_ids'])}
    orig_selected = original['draws'][:, [original_lookup[int(r)] for r in m.row_id]]
    check('actual_original_archive_arrays_equal_subset', np.array_equal(counts, orig_selected), counts.shape, orig_selected.shape)
    original_config = json.loads(touch(AUTH / 'config.json').read_text(encoding='utf-8'))
    check('original_allocation_seed_identity', json.loads(str(original['seed_map_json'][0])) == original_config['seed_map'], 'saved seed map compared in memory', 'unchanged original seed map')
    check('allocation_shape_integer_finite', counts.shape == (30, 15360) and np.isfinite(counts).all() and np.equal(counts, np.floor(counts)).all(), counts.shape, '(30, 15360) integer finite')
    supp = m.death_suppressed.to_numpy(bool)
    check('allocation_support_1_9', ((counts[:, supp] >= 1) & (counts[:, supp] <= 9)).all(), int(supp.sum()), 'all 30 saved counts within 1-9')
    check('public_counts_including_zero_fixed', np.array_equal(counts[:, ~supp], np.broadcast_to(m.deaths.to_numpy()[~supp], counts[:, ~supp].shape)), int((~supp).sum()), 'all 30 saved counts unchanged')
    for k, g in m.groupby(['state_abbr', 'year', 'cause_id']):
        ix = m.index.get_indexer(g.index)
        good = g.state_deaths.nunique() == 1 and np.equal(counts[:, ix].sum(axis=1), g.state_deaths.iloc[0]).all()
        check('allocation_state_total_' + '|'.join(map(str, k)), good, g.state_deaths.iloc[0], 'all 30 exact')
    stored = read(F / 'nested_outcome_check.csv').set_index(['child', 'parent'])
    nests = []
    for child, parent in [(IDS[0], IDS[1]), (IDS[1], IDS[2]), (IDS[4], IDS[3])]:
        a = m[m.cause_id.eq(child)].sort_values(['county_fips', 'year'])
        b = m[m.cause_id.eq(parent)].sort_values(['county_fips', 'year'])
        av = z['draws'][:, [lookup[int(i)] for i in a.row_id]]
        bv = z['draws'][:, [lookup[int(i)] for i in b.row_id]]
        viol = av > bv
        public = ~a.death_suppressed.to_numpy(bool) & ~b.death_suppressed.to_numpy(bool)
        row = dict(n_county_years=len(a), n_draw_comparisons=viol.size, draw_violations=int(viol.sum()), any_draw_violations=int(viol.any(axis=0).sum()), mean_count_violations=int((av.mean(axis=0) > bv.mean(axis=0)).sum()), public_comparisons=int(public.sum()), public_violations=int((a.deaths.to_numpy()[public] > b.deaths.to_numpy()[public]).sum()), max_excess=int(np.maximum(av-bv, 0).max()), per_draw_min=int(viol.sum(axis=1).min()), per_draw_max=int(viol.sum(axis=1).max()))
        for field, value in row.items():
            check(f'nested_array_{child}_{parent}_{field}', eq(value, stored.loc[(child, parent), field]), value, stored.loc[(child, parent), field])
        nests.append(dict(child=child, parent=parent, **row))
    paired = read(BASE / 'audit/paired_imputation_identity.csv').set_index(['outcome_id', 'imputation'])
    identity = read(F / 'common_sample_identity.csv').set_index('outcome_id')
    for oid in IDS:
        a = read(AUTH / f'sample_keys/{oid}__C__M2.csv')
        b = read(AUTH / f'sample_keys/{oid}__C__M3PL_joint.csv')
        check('common_sample_ordered_keys_' + oid, a.equals(b) and len(a) == 3062, len(a), '3062 equal ordered records')
        vals = z['draws'][:, [lookup[int(i)] for i in a.row_id]]
        array_hash = hashlib.sha256(np.asarray(vals, dtype='<i8').tobytes()).hexdigest()
        check('common_sample_array_identity_' + oid, array_hash == identity.loc[oid, 'selected_allocation_sha256_i64le'], array_hash, identity.loc[oid, 'selected_allocation_sha256_i64le'])
        for model in ['M2', 'M3PL_joint']:
            fits = read(AUTH / f'per_imputation/{oid}__C__{model}.csv')
            cache = read(INP / f'per_imputation/{oid}__C__{model}.csv')
            check(f'paired_fit_identity_{oid}_{model}', fits.equals(cache), len(fits), 30)
            check(f'paired_fit_status_{oid}_{model}', len(fits) == 30 and fits.status.eq('ok').all() and fits.converged.all() and fits.imputation.tolist() == list(range(1, 31)), len(fits), '30 converged saved fits; no fit executed')
        for i, arr in enumerate(vals, 1):
            got = hashlib.sha256(np.asarray(arr, dtype='<i8').tobytes()).hexdigest()
            check(f'paired_allocation_{oid}_{i}', got == paired.loc[(oid, i), 'sha256'], got, paired.loc[(oid, i), 'sha256'])
    FACTS['nested_array_diagnostics'] = nests


def inspect_and_copy(frozen, copy_files):
    excluded = frozen.loc[~frozen.outcome_id.isin(IDS), ['outcome_id', 'outcome_name']].drop_duplicates()
    tokens = [str(x).casefold() for x in excluded.to_numpy().ravel() if str(x)]
    for src in sorted(SD.rglob('*')):
        if not src.is_file():
            continue
        touch(src)
        rel = src.relative_to(SD)
        old_numbering = src.name.startswith('Table_S') or src.name.startswith('Supplementary_Figure_S')
        old_readme = src.name.lower() == 'readme.md'
        legacy_geo = rel.as_posix() == 'geography/county_join_audit.csv'
        target = AUD / 'baseline_tables' / src.name if old_numbering else AUD / 'baseline_geography' / src.name if legacy_geo else DEST / rel
        decision = 'internal_old_numbering' if old_numbering else 'internal_legacy_geography_values' if legacy_geo else 'omit_old_readme' if old_readme else 'copy_unchanged'
        reasons = []
        if src.suffix.casefold() in {'.npz', '.npy', '.rds', '.pkl', '.pickle'}:
            reasons.append('restricted_array_format')
        if src.suffix.casefold() in {'.csv', '.md', '.json', '.geojson', '.xml', '.txt'}:
            txt = src.read_text(encoding='utf-8-sig', errors='replace')
            hits = sum(token in txt.casefold() for token in tokens)
            check('no_removed_outcome_text:' + str(rel), hits == 0, hits, 0, 'scope')
            if hits:
                reasons.append('removed_outcome_content')
        if src.suffix.casefold() == '.csv':
            data = read(src)
            for col in ['outcome_id', 'cause_id', 'child', 'parent']:
                if col in data.columns:
                    vals = set(data[col].dropna().astype(str))
                    okay = vals.issubset(set(IDS))
                    check('outcome_scope:' + str(rel) + ':' + col, okay, len(vals), 'five-outcome whitelist', 'scope')
                    if not okay:
                        reasons.append('outcome_scope')
            for col in ['year', 'year_min', 'year_max', 'year_start', 'year_end', 'FIRE_YEAR_INT', '年份', '年']:
                if col in data.columns:
                    vals = pd.to_numeric(data[col], errors='coerce').dropna()
                    okay = vals.between(2009, 2020).all()
                    check('observation_year_scope:' + str(rel) + ':' + col, okay, f'{vals.min()} to {vals.max()}', '2009 to 2020', 'scope')
                    if not okay:
                        reasons.append('observation_year_scope')
        if reasons:
            decision = 'NOT_COPIED_REQUIRES_REVIEW:' + ','.join(sorted(set(reasons)))
        eligible = not reasons and not old_readme
        if copy_files and eligible:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if sha(target) != sha(src):
                    raise RuntimeError(f'Existing destination differs; not overwritten: {target}')
            else:
                shutil.copy2(src, target)
            if legacy_geo:
                previous_copy = DEST / rel
                # Recover only the exact copy created by this integration's first audit.
                # Its content is preserved byte-for-byte in audit/baseline_geography.
                if previous_copy.exists():
                    if previous_copy.resolve().is_relative_to(DEST.resolve()) and sha(previous_copy) == sha(src) == sha(target):
                        previous_copy.unlink()
                    else:
                        raise RuntimeError('Unexpected geography file; no removal performed')
        hash_equal = target.exists() and sha(target) == sha(src) if eligible else None
        if copy_files and eligible:
            check('copied_source_hash:' + str(rel), hash_equal, sha(target), sha(src))
        MANIFEST.append(dict(source=str(src), destination=str(target) if eligible else '', relative_source=str(rel), decision=decision, bytes=src.stat().st_size, sha256_before=USED[str(src)], sha256_after='', destination_sha256=sha(target) if target.exists() and eligible else '', copied=copy_files and eligible, source_unchanged=''))
    check('no_restricted_arrays_public', not any(p.suffix.casefold() in {'.npz', '.npy', '.rds', '.pkl', '.pickle'} for p in DEST.rglob('*') if p.is_file()), 'no array files', 'no restricted allocation arrays', 'scope')
    check('legacy_geographic_statistical_values_not_public', not (DEST / 'geography/county_join_audit.csv').exists(), 'historical join table retained in audit only', 'current matching in full_results/county_geographic_join.csv', 'scope')
    for row in MANIFEST:
        row['sha256_after'] = sha(row['source'])
        row['source_unchanged'] = row['sha256_before'] == row['sha256_after']


def write_boundaries():
    text = '''# Statistical boundaries of this integration

This is a reporting and evidence-integration operation. It reads saved values, verifies identities, and reaggregates descriptive counts and existing cell-level validation scores. It does not fit mortality models, train empirical-Bayes weights, draw allocations, recompute IQR/SES, adjust P values, generate confidence intervals, test cross-model differences, or bootstrap.

## Frozen inference

The reference interaction estimates in block A retain the originally saved Holm-adjusted P values from a seven-test family, although five outcomes are reported. The family was frozen after prior exploration, not prospectively preregistered. Retaining the original correction is transparent multiplicity accounting, not proof that outcome-selection/reporting risk has been removed. Blocks B–E retain ordinary two-sided P values and ordinary 95% confidence intervals. These are not Holm simultaneous intervals. The source field `run_source=recomputed` refers to the historical experiment run, not this integration.

The 135 rows are compared by outcome_id + analysis_block + model_id + contrast_id against the original archived experiment. Every common numeric/identity field is compared without rounding. Only the already documented historical family-label change is excluded from literal text comparison; no numerical values are changed.

## Samples and allocation identity

The reference sample has 3,072 county-years; the common-sample comparison has 3,062. Equality of its ordered row IDs, county-year keys, archived fit records, and all 30 saved outcome-specific count vectors is inspected. Common sample size alone is not accepted as proof of pairing. County is the clustering unit. Thirty allocations are not 30 independent studies or independent county observations.

The read-only array checks confirm integer support 1–9 for Suppressed cells, fixed observed counts including zero, and each state-year-outcome total in all 30 saved allocations. A hash-verified, existing five-outcome subset is read in place and compared element-by-element with the corresponding columns read from the original archived member in memory. The original member hash and saved seed map are checked. No counts are generated or written, and restricted arrays are not copied into submission.

## Validation boundary

All four saved validation methods are evaluated on identical 298 groups / 2,128 publicly visible 10–19-count cells. The historical validation used 100 draws and support 0–19; selecting the current evaluation period does not retrain historical weights. Only stored point errors, interval endpoints, CRPS and interval scores are summarized. No new inference is produced. Allocation-interval coverage does not calibrate the actual hidden counts or mortality-model/interaction confidence intervals. Hierarchical EB is not uniformly best across all six performance measures.

## Evidence that must remain visible

All 25 conditional contrasts are retained: 15 ordinary intervals are wholly negative, 10 span zero, and none are wholly positive. Positive interaction does not establish positive smoke associations at all disadvantage levels, protection, additional deaths, or causation. Directed omission results include negative IHD point estimates and multiple intervals spanning zero. CI overlap, or significance in only one model, does not test differences or equivalence.

Three parent-child relations have count-array inconsistencies despite no violation in pairs of observed public counts. Their numerical diagnostics are reproduced directly from the stored arrays. Corresponding draw numbers across outcomes are not draws from a joint posterior. Diagnostics are not posterior violation probabilities. Do not sum violation counts across relations, add nested outcomes as distinct deaths, estimate shares, or derive formal cross-outcome covariance.

The design residual sum-of-squares partition is not death burden, attributable fraction, causal contribution, or evidence that a region/year caused an effect. Fixed weights/dispersion and county clustering do not automatically account for all allocation-weight uncertainty, cross-outcome dependence or cross-county correlation.

## Source-data scope and geography

Public source data include only five retained outcomes and observation records from 2009–2020. Historical training, ACS baseline, map product and retrieval years remain genuine provenance rather than observation years. Census 2020 metadata and license statements are kept intact. Original metadata contain historical/product/retrieval dates, not additional analytical observations. The legacy geography README contains an earlier panel-range description and an obsolete relative link; it is not copied. The old geography/county_join_audit.csv also contains 105 historical records per county and old suppression percentages: it is retained under audit/baseline_geography only, and the exact-FIPS 256-row current table full_results/county_geographic_join.csv is used publicly. Geographic polygons contain identifiers and geometry only, without diagnosis fields or restricted counts.

Original files are hashed before and after the read-only audit. Public redistribution permissions for research-derived source tables still require author confirmation; copying locally is not uploading or licensing the data.
'''
    (AUD / 'statistical_boundaries.md').write_text(text, encoding='utf-8')
    notes = '''# Source data copy notes

- Semantic-named, already scoped files are copied byte-for-byte from the current five-outcome baseline. The original source hashes, destination hashes and copy decisions are in data_source_manifest.csv.
- Historical Table_S*.csv and Supplementary_Figure_S*_data.csv are archived under audit/baseline_tables, not the public source-data tree. New numbered tables and figures are prepared separately.
- Both old README.md files are intentionally omitted because their numbering, relative links and historical descriptive text need current-package wording.
- The old geography/county_join_audit.csv retains stale 105-record denominators and suppression percentages. It is preserved only in audit/baseline_geography; an exact first-pass copy has been removed from the new public tree after byte-identity verification. Nothing is deleted from any historical version. The current full_results/county_geographic_join.csv and county_map_values.csv are retained.
- No .npz/.npy or other allocation array is copied. mortality_records.csv contains original aggregate published values and suppression flags, with hidden cells blank; it does not expose allocation draws.
- Geography preserves official 2020 source ZIPs, shapefiles and metadata verbatim. Copyright/use conditions and historical/product/retrieval timestamps must not be globally replaced. Its old README is excluded, and the new package should document the 2009–2020 display period and unresolved upstream historical-boundary harmonization.
- Existing run_source, run_fingerprint, sample_hash and imputation_version fields retain historical analysis identity. A historical value such as run_source=recomputed does not describe a new analysis in this integration.
- All copies are local. Repository deposit, access rules and licensing are not assumed or changed.
'''
    (AUD / 'data_copy_notes.md').write_text(notes, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--copy', action='store_true', help='Copy validated source files into this new version; never overwrite differing files.')
    args = parser.parse_args()
    AUD.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    frozen = audit_health()
    m, raw = audit_descriptive()
    audit_validation()
    audit_arrays(m, raw)
    inspect_and_copy(frozen, args.copy)
    for path, old_hash in list(USED.items()):
        check('source_unchanged:' + path, sha(path) == old_hash, sha(path), old_hash)
    save_csv(AUD / 'numerical_consistency_check.csv', NUM)
    save_csv(AUD / 'scope_consistency_check.csv', SCOPE)
    save_csv(AUD / 'data_source_manifest.csv', MANIFEST)
    write_boundaries()
    failures = [r for r in NUM + SCOPE if r['status'] != 'PASS']
    summary = dict(started_utc=started, finished_utc=datetime.now(timezone.utc).isoformat(), base=str(BASE), original_experiment=str(AUTH), copy_enabled=args.copy, numerical_checks=len(NUM), scope_checks=len(SCOPE), failures=failures, copied_files=sum(bool(r['copied']) for r in MANIFEST), source_files_hashed=len(USED), python=sys.version, numpy=np.__version__, pandas=pd.__version__, facts=FACTS, prohibited_operations_executed=[])
    (AUD / 'numerical_audit_run.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'facts'}, ensure_ascii=False, indent=2))
    print(json.dumps(FACTS, ensure_ascii=False, indent=2, default=str))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
