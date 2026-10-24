"""Write metadata documentation only; never edit frozen numerical source data."""
from pathlib import Path
import csv
import hashlib
import json
import re
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
SUB = ROOT / 'submission'
SD = SUB / 'source_data'
OUTDATA = SUB / 'supplementary_data'


def readcsv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def writecsv(path, fields, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def bibliography():
    refs = json.loads((ROOT / 'scripts/references.json').read_text(encoding='utf-8'))
    lines = ['% Verified Supplementary References; BibTeX keys are independent of SI citation numbering.',
             '% Verification and primary-source URLs: audit/reference_verification.csv.',
             '% Access date is not an assumed publication year. No missing DOI/year is fabricated.', '']
    fields = ('author', 'title', 'journal', 'publisher', 'year', 'volume', 'number', 'pages', 'isbn', 'doi', 'url', 'urldate', 'note')
    for ref in refs:
        lines.append('@%s{%s,' % (ref['type'], ref['bibtex_key']))
        for field in fields:
            if ref.get(field):
                value = str(ref[field])
                if field not in ('doi', 'url'):
                    value = value.replace('&', r'\&')
                lines.append('  %s = {%s},' % (field, value))
        lines.extend(['}', ''])
    (SUB / 'Supplementary_References.bib').write_text('\n'.join(lines), encoding='utf-8')


D = {}


def define(names, meaning, unit='not applicable', status='VERIFIED_LOCAL'):
    for name in names.split('|'):
        D[name] = (meaning, unit, status)


define('county_fips|centroid_county_fips', 'County or county-equivalent FIPS identifier. Treat as a five-character string; legacy numeric serialization may omit leading zero or append .0. For joins only, normalize an integral value to 5 digits; never treat it as a continuous number.', 'identifier')
define('state_fips|FIPS', 'State or equivalent FIPS identifier. Preserve/normalize to a two-character string with leading zeros.', 'identifier')
define('state_abbr', 'Two-letter state or District of Columbia abbreviation.', 'identifier')
define('state|states', 'State name/abbreviation, or comma-separated model-support list. In geography/state_join_audit.csv, state contains the two-letter abbreviation.', 'text')
define('county', 'Saved county name and state label.', 'text')
define('year|FIRE_YEAR_INT', 'Observation year or catalogue record fire year; study reporting interval is 2009–2020.', 'calendar year')
define('year_min|year_max|year_start|year_end', 'First/last supported observation year as identified by the field suffix; not the ACS baseline or publication year.', 'calendar year')
define('years|exposure_period', 'Observation-period label for 2009–2020.', 'text')
define('baseline_period', 'Archived ACS baseline-period label. This is a covariate provenance period, not an extension of the 2009–2020 outcome/exposure window.', 'text')
define('smoke_mean', 'Temporal mean of saved annual smoke PM2.5 concentrations for the county or jurisdiction represented by the row; equal annual weighting. State and county upstream aggregation should not be assumed identical.', 'micrograms per cubic metre')
define('smoke_pm25_annual_burden|county_smoke_pm25_annual_burden_y', 'Saved annual smoke PM2.5 concentration (annual daily sum divided by 365.25 in the archived processing). Historical burden field name does not mean total exposure mass or number of days.', 'micrograms per cubic metre')
define('population_weighted_smoke', 'Annual mean smoke PM2.5 weighted by annual county population across the counties represented by the row; state-year rows use within-state weights.', 'micrograms per cubic metre')
define('county_mean|county_median|county_p10|county_p90', 'Unweighted county distribution statistic indicated by the suffix. annual.csv describes annual concentrations; within_state_county_distribution.csv describes county temporal means.', 'micrograms per cubic metre')
define('state_mean|state_median|state_p10|state_p90', 'Equal-jurisdiction annual smoke PM2.5 distribution statistic among the 49 exposure-supported jurisdictions; not population weighted.', 'micrograms per cubic metre')
define('mean|median|minimum|maximum|p10|p90', 'Descriptive distribution statistic indicated by the field name, for saved county temporal-mean smoke within the named state or baseline-disadvantage quintile.', 'micrograms per cubic metre')
define('unweighted_county_gini|equal_state_gini', 'Unweighted county or equal-jurisdiction Gini coefficient of the exposure distribution, respectively; no inferential CI was generated.', 'dimensionless')
define('across_year_weight|within_state_weight|point_weight', 'Explicit saved aggregation/display weighting rule. County-population weighting of baseline poverty, equal annual means and equal state points are distinct operations.', 'text')
define('population|population_sum', 'Annual county population or sum across the represented units; when years are pooled this is a sum of county-year populations, not distinct people. Model offset uses the corresponding annual population.', 'persons or sum of county-year persons as row scope indicates')
define('ses|ses_baseline_std', 'Archived fixed baseline county-disadvantage composite in standardized six-state county units; higher is more disadvantaged. The full upstream component/weight/missingness specification is not fully authenticated.', 'fixed baseline standard-deviation units', 'PARTIAL_UPSTREAM')
define('ses_sd', 'Fixed baseline disadvantage value at which the conditional smoke association is evaluated (−2, −1, 0, +1 or +2).', 'fixed baseline standard-deviation units')
define('ses_min|ses_max', 'Minimum/maximum observed fixed baseline disadvantage in the saved model sample.', 'fixed baseline standard-deviation units')
define('quintile|baseline_ses_quintile', 'Frozen county baseline-disadvantage quintile; 1 is least and 5 most disadvantaged. Not re-ranked by model or omission sample.', 'ordered category 1–5')
define('poverty_rate', 'Saved state baseline poverty proportion, assembled with the archived county total-population weighting; not the county disadvantage composite. Archived extraction identity is incomplete.', 'proportion (0–1)', 'PARTIAL_UPSTREAM')
define('poverty_percent', '100 times the saved state baseline poverty proportion.', 'percent', 'PARTIAL_UPSTREAM')
define('economic_field|economic_direction', 'Saved definition and orientation of the ecological state-level poverty variable.', 'text')
define('difference_saved_minus_current', 'Archived state annual smoke minus current county-population-weighted state aggregation; diagnostic difference, not a refitted or harmonized replacement.', 'micrograms per cubic metre')
define('ratio_saved_over_current', 'Archived state annual smoke divided by current county-population-weighted state aggregation.', 'dimensionless ratio')
define('outcome_id|cause_id|child|parent', 'One of the five retained mortality-outcome identifiers; child/parent denote the expected ICD containment relation, not independent outcomes.', 'identifier')
define('outcome_name|name_en|short_en', 'Saved Chinese outcome name, English full name or English abbreviation, respectively. Use outcome_dictionary.csv for exact mapping.', 'text')
define('icd10|icd10_range', 'Retained ICD-10 range: COPD J40–J44; CLRD J40–J47; RESP J00–J98; CIRC I00–I99; IHD I20–I25. Nested outcomes must not be summed.', 'ICD-10 code range')
define('deaths', 'Original public county death count when unsuppressed; empty in suppressed cells. Public zero is an observed zero. No allocated suppressed count is supplied in this field.', 'death count')
define('death_suppressed', 'True indicates an originally suppressed county-year-outcome count, not a zero.', 'boolean')
define('public_deaths', 'Sum of publicly reported county death counts in the represented state-year-outcome group.', 'death count')
define('state_deaths', 'Reported state death count or sum over the represented state-year-outcome groups.', 'death count')
define('hidden_deaths', 'State-total remainder after subtracting public county counts, or its aggregate across the stated scope. It is a group-level conservation total, not identified county cell truth.', 'death count')
define('suppressed|suppressed_records', 'Number of county-year-outcome records marked suppressed within the row scope.', 'record count')
define('public_zero', 'Number of records with a reported public zero; these are distinct from suppressed/missing records.', 'record count')
define('record_percent|suppressed_record_percent', '100 times suppressed record count divided by total record count within the row scope.', 'percent of records')
define('hidden_percent', '100 times aggregate hidden death remainder divided by corresponding state death total.', 'percent of deaths')
define('row_id', 'Archived source row identifier; not a person or patient identifier.', 'identifier')
define('analysis_block', 'A reference interactions; B conditional associations; C common-sample adjustment models; D targeted omissions; E paired LST branches.', 'category A–E')
define('model_id|mode|task_id|contrast_id', 'Saved model/branch/task/contrast identity. Unique health result key is outcome_id + analysis_block + model_id + contrast_id.', 'identifier')
define('formula', 'Saved regression right-hand-side formula. County/year fixed effects and archived standardizations are retained; inspect Supplementary Methods for offset, distribution and uncertainty.', 'formula text')
define('run_fingerprint|sample_hash|sample_id', 'Archived run or sample identity for traceability; does not establish all upstream provenance.', 'identifier/hash')
define('imputation_version', 'Frozen allocation procedure version (fixed_EB_B1_1_9). Historical imputation terminology denotes the existing constrained allocated datasets, not a new allocation performed for this Supplement.', 'identifier')
define('exposure_unit', 'Exact saved effect scale. Smoke IQR is fixed at 0.678107947271523 micrograms per cubic metre; interaction also uses one fixed baseline disadvantage SD.', 'scale text')
define('run_source', 'Status label from the earlier experiment. A value such as recomputed is historical and does not mean this Supplement integration re-estimated any model.', 'text')
define('fit_status', 'Saved fit completion/failure status; blanks in other fields must be interpreted with this status.', 'text')
define('n_imputations', 'Number of frozen allocated datasets used for pooled health estimates (30); not independent patients, counties, or scientific replicates.', 'allocated-dataset count')
define('design_rank|design_columns|original_design_columns|FE_projection_rank|FE_projection_columns|full_projection_rank|full_projection_columns', 'Saved numerical matrix rank or column count indicated by the field name; FE refers to the county/year fixed-effect projection.', 'matrix count')
define('dropped_aliases', 'Saved collinear/aliased design terms removed from the source fit, serialized as a list.', 'list')
define('dispersion_alpha', 'Saved negative-binomial dispersion parameter.', 'model parameter')
define('alpha_at_bound', 'Saved flag indicating the dispersion estimate reached an optimization bound.', 'boolean')
define('design_condition_number', 'Saved design matrix condition number; a numerical conditioning diagnostic, not a causal-validity test.', 'dimensionless')
define('beta', 'Saved pooled log effect: conditional log(RR) in block B and log(RRR) interaction in A/C/D/E, on the fixed exposure scale.', 'natural-log effect')
define('SE', 'Saved pooled standard error of beta using the archived county-cluster variance and Rubin procedure.', 'natural-log effect')
define('beta_CI_lower|beta_CI_upper', 'Saved lower/upper ordinary two-sided 95% confidence limit on the beta scale, not a multiplicity-adjusted simultaneous limit.', 'natural-log effect')
define('P_value', 'Saved unadjusted two-sided P value for the represented coefficient/contrast. Conditional and sensitivity analyses do not acquire Holm significance from block A.', 'probability')
define('P_adjusted', 'Saved Holm-adjusted P value for block A under the original family of seven tests. Five outcomes are now displayed, but the family was not recomputed as five. Empty elsewhere is not zero.', 'probability')
define('comparison_family', 'Saved multiple-testing-family label. original_Holm_family_n7 preserves the original seven-test correction while reporting only the five retained outcomes.', 'text')
define('within_variance|between_imputation_variance|total_variance', 'Saved within-allocation, between-allocation or total Rubin variance of beta, respectively.', 'squared natural-log effect')
define('df_rubin', 'Saved degrees of freedom for Rubin pooling.', 'degrees of freedom')
define('fraction_missing_information', 'Saved pooling fraction of missing information; this is not the observed suppressed-record fraction.', 'dimensionless')
define('monte_carlo_error', 'Saved Monte Carlo error diagnostic for the pooled beta estimate.', 'natural-log effect')
define('MC_error_over_SE', 'Saved Monte Carlo error divided by the pooled beta standard error.', 'dimensionless ratio')
define('percent_estimate|interaction_percent', '100 × [exp(beta) − 1]. This is percent RR change in conditional block B and percent RRR change in interaction blocks A/C/D/E; historical interaction_percent also exists in B and must not override that distinction.', 'percent change in RR or RRR as block indicates')
define('percent_CI_lower|percent_CI_upper|CI_percent_lower|CI_percent_upper', 'Saved ordinary two-sided 95% beta limits transformed by 100 × [exp(limit) − 1]; same RR/RRR distinction as the estimate.', 'percent change in RR or RRR as block indicates')
define('elapsed_seconds', 'Saved source fitting elapsed time; not execution duration of Supplement assembly.', 'seconds')
define('within_observed_support', 'Conditional disadvantage evaluation point lies inside the saved observed support.', 'boolean')
define('missing_value_definition|missing_reason', 'Saved explanation of missing/not-applicable values. Blank, NA or unavailable values are not numerical zero.', 'text')
define('reference_n|joint_n', 'Number of county-year keys in the compared reference/joint common-sample fits; both 3,062 in the documented common-sample comparison.', 'county-year count')
define('keys_order_equal|actual_allocation_values_equal', 'Saved exact identity check for ordered keys or selected allocated values in the common-sample comparison; only diagnostics, not the restricted arrays, are included.', 'boolean')
define('imputations_equal', 'Number of corresponding allocated datasets found equal in the saved comparison, despite the historical field name.', 'allocated-dataset count')
define('selected_allocation_sha256_i64le', 'SHA-256 of selected allocated values in archived little-endian signed-64-bit representation; a checksum, not a public allocation array.', 'SHA-256')
define('status', 'Saved pass/fail or completion status for the check identified by the table.', 'text')
define('group', 'Disjoint diagnostic partition of the frozen reference design, as named in the record.', 'text')
define('death_events_MI_mean', 'Mean allocated death total across the frozen datasets for the indicated diagnostic partition; not unique individuals or an independently observed count.', 'mean death count')
define('smoke_scale|SES_scale', 'Saved fixed smoke-IQR or baseline-disadvantage-SD transformation used in the design decomposition.', 'scale text')
define('population_weighted', 'Whether the design decomposition used population weights; distinct from descriptive population-weighted exposure summaries.', 'boolean')
define('centering|projection_method', 'Saved centering/residualization or least-squares method description; projections were made in the full reference sample before partitioning.', 'text')
define('rcond|numerical_tolerance|max_normal_equation_residual', 'Saved least-squares cutoff, numerical tolerance or maximum normal-equation residual; numerical QA on the archived transformed design, not an epidemiological effect.', 'numerical diagnostic on transformed design')
define('smoke_design_ss|interaction_county_centered_ss|smoke_FE_residual_ss|interaction_FE_residual_ss|residualized_interaction_ss', 'Saved sum of squared transformed design terms under the projection named by the field. These characterize design information and are not death contributions or formal causal influence.', 'squared fixed-scale design units')
define('smoke_design_ss_share|interaction_county_centered_ss_share|smoke_FE_residual_ss_share|interaction_FE_residual_ss_share|residualized_interaction_ss_share', 'Fraction of the corresponding full-reference-sample design sum of squares in this disjoint partition.', 'proportion (0–1)')
define('relation', 'Expected ICD child–parent containment relation for an allocation diagnostic. Outcomes overlap and relation counts cannot be added as independent evidence.', 'text')
define('n_draw_comparisons', 'Number of county-year by allocation-index comparisons per relation (3,072 × 30 = 92,160).', 'comparison count')
define('draw_violations', 'Number of matched array-index comparisons with child count greater than parent count; not a joint posterior probability.', 'comparison count')
define('any_draw_violations', 'Number of county-years with at least one child-greater-than-parent allocation-index comparison.', 'county-year count')
define('mean_count_violations', 'Number of county-years whose allocation-mean child count exceeds the allocation-mean parent count.', 'county-year count')
define('public_comparisons|public_violations', 'Number of pairs with both public counts available, or number of child-greater-than-parent violations among these public pairs.', 'county-year comparison count')
define('max_excess', 'Largest saved child-minus-parent allocated count excess in the relation.', 'death count')
define('per_draw_min|per_draw_max', 'Minimum/maximum number of child–parent violating county-years across the 30 allocation indices.', 'county-year count per allocation index')
define('scope', 'Summary population/outcome scope. all_outcomes in the current validation export means the five retained outcomes, not the historical seven-test family.', 'text')
define('method', 'Saved pseudo-masking allocation comparator identifier; see Methods for its weighting rule.', 'identifier')
define('pseudo_group_id', 'Pseudo-masking state-year-outcome group identifier.', 'identifier')
define('true_visible_count', 'Originally public count in the visible 10–19 pseudo-masking analogue; not true suppressed-cell ground truth.', 'death count')
define('posterior_mean|q025|q975', 'Saved allocation mean or 2.5th/97.5th empirical percentile in the visible-count validation exercise; finite-draw diagnostics, not suppressed-cell truth.', 'death count')
define('absolute_error|MAE', 'Absolute error for an evaluated cell, or mean absolute error over the stated scope, against visible pseudo-masking truth.', 'death count')
define('squared_error', 'Squared error against the visible pseudo-masking count.', 'squared death count')
define('RMSE', 'Root mean squared error against visible pseudo-masking counts.', 'death count')
define('interval_covers_truth', 'Whether the saved pseudo-masking interval includes its originally visible count.', 'boolean')
define('interval_width|mean_interval_width', 'Saved validation interval width or its mean across the stated cells.', 'death count')
define('coverage_95', 'Empirical coverage proportion of nominal 95% intervals for the visible-count analogue, not validated coverage of true suppressed cells.', 'proportion (0–1)')
define('CRPS|mean_CRPS', 'Saved continuous ranked probability score or its average for the finite-draw visible-count validation.', 'death count')
define('interval_score_95|mean_interval_score_95', 'Saved nominal-95% interval score or its average for visible-count validation.', 'death count')
define('n_draws', 'Number of saved validation draws (100); distinct from 30 allocated datasets used for mortality-model pooling.', 'draw count')
define('support', 'Allowed count support for the saved exercise. Validation support 0–19 differs from suppressed-count allocation support 1–9.', 'count interval text')
define('validation_limit', 'Explicit interpretation boundary of the visible-count analogue.', 'text')
define('Rank|catalogue_rank', 'Rank retained from the archived fire catalogue, not a fresh complete-universe ranking or a unique event number. Gaps after period filtering are expected.', 'ordinal catalogue label')
define('IncidentName|incident_name|normalized_name', 'Archived incident name or normalized candidate-duplicate name; identical normalized name and year flags candidates, not confirmed duplicates.', 'text')
define('SizeMetricAcres|GIS_ACRES', 'Archived catalogue size metric/GIS area in acres. Identity of the full source query, snapshot and original ranking is only partly documented; not a re-estimated area.', 'acres', 'PARTIAL_UPSTREAM')
define('Latitude|Longitude', 'Saved geographic location latitude/longitude, respectively; not proof of a uniquely authenticated ignition point.', 'decimal degrees', 'PARTIAL_UPSTREAM')
define('centroid_state|centroid_county|centroid_county_state', 'Administrative unit label assigned to the saved fire geometry centroid; not a city-of-origin determination.', 'text')
define('intersect_states|intersect_counties', 'Semicolon-separated administrative units intersecting the saved fire perimeter geometry. One record may contribute to multiple state assignments.', 'list of labels')
define('location_match_method', 'Saved spatial matching method, such as polygon_intersection.', 'text')
define('city_or_place|city_or_place_note', 'Saved place/city matching result and limitation. Not determined is missing evidence, not a zero location or an inferred city.', 'text')
define('fire_key|UNQE_FIRE_ID|GlobalID', 'Archived fire/perimeter record identifier. These fields do not by themselves resolve incident/perimeter-version duplication.', 'identifier')
define('in_six_state_region', 'Whether a jurisdiction or assignment belongs to AZ, CA, CO, ID, OR or WA; not itself an observation-eligibility rule.', 'boolean')
define('potential_duplicate_name_year', 'True if Rank occurs in the frozen fire_potential_duplicates.csv, based on normalized incident name and year. Candidate flag only; no records were deduplicated.', 'boolean')
define('eligible', 'Saved eligibility for the ecological state poverty–smoke comparison; Supplementary Data 1 retains only true rows.', 'boolean')
define('exposure_available|exposure_present', 'Whether smoke exposure exists for the row; Alaska/Hawaii are missing exposure, not zero exposure and not proof of no wildfire.', 'boolean')
define('data_matched|geometry_matched|geometry_valid|inset', 'Saved administrative-key match, geometry validity, or inset-display flag as named. Matching a 2020 display geometry does not verify historical boundary harmonization.', 'boolean')
define('projection', 'Saved map projection name or EPSG identifier. County study display uses EPSG:5070; state insets can use other documented projections.', 'CRS identifier/text')
define('epsg', 'EPSG coordinate-reference-system code, not an observation value.', 'CRS identifier')
define('n', 'Number of source records in suppression/state-death tables, or number of counties in the quintile descriptive table; use the row scope and file name.', 'record/counties count as table indicates')
define('n_observations|n_county_years', 'Number of county-year observations supporting the saved model or diagnostic, not number of deaths or independent participants.', 'county-year count')
define('n_counties|n_intersect_counties', 'Number of represented counties or intersected counties, respectively.', 'county count')
define('n_states|n_units', 'Number of supported states/jurisdictions; state annual summaries contain 49 exposure-supported jurisdictions including DC.', 'jurisdiction count')
define('n_observed_years|n_years', 'Number of supported observation years.', 'year count')
define('n_records', 'Number of county-year-outcome records in the row scope (60 per complete county: 12 years × 5 outcomes).', 'record count')
define('n_causes', 'Number of retained mortality outcome definitions represented.', 'outcome count')
define('n_groups', 'Number of state-year-outcome pseudo-masking groups in the saved validation.', 'group count')
define('n_cells', 'Number of evaluated county-year-outcome visible cells in the saved validation.', 'cell count')
define('catalogue_record_assignments', 'Number of archived catalogue record-to-state assignments; multi-state records can be counted in more than one state. Not independent unique fires.', 'record-to-state assignment count')
define('n_state_assignments_for_record', 'Number of distinct state assignments for the given catalogue record.', 'state assignment count')


def dictionary():
    # Formatted bilingual table exports have human-readable headings/captions;
    # all canonical machine fields are covered here, including figure panels.
    files = []
    for p in sorted(SD.rglob('*.csv')):
        if 'tables' in p.relative_to(SD).parts or p.name == 'data_dictionary.csv':
            continue
        files.append(p)
    files.extend(sorted(OUTDATA.glob('Supplementary_Data_*.csv')))
    occurrences = defaultdict(list)
    observations = defaultdict(set)
    for p in files:
        rows = readcsv(p)
        if not rows:
            continue
        for field in rows[0]:
            occurrences[field].append(p.relative_to(SUB).as_posix())
            vals = [r.get(field, '') for r in rows]
            if any(v == '' for v in vals):
                observations[field].add('blank observed')
            if any(str(v).lower() in ('nan', 'na', 'null') for v in vals):
                observations[field].add('NA/NaN/null token observed')
    unknown = sorted(set(occurrences) - set(D))
    if unknown:
        raise RuntimeError('Undocumented actual fields: ' + ', '.join(unknown))
    rows = []
    for field in sorted(occurrences, key=str.lower):
        meaning, unit, status = D[field]
        rows.append(dict(field=field, definition_en=meaning, unit_or_scale=unit,
                         missing_value_rule='Missing/blank is not zero. ' + ('; '.join(sorted(observations[field])) or 'No blank/NA token observed in current listed files.'),
                         metadata_status=status, source_files='; '.join(occurrences[field])))
    writecsv(SD / 'data_dictionary.csv', list(rows[0]), rows)
    (ROOT / 'audit/data_documentation_check.json').write_text(json.dumps({
        'dictionary_fields': len(rows), 'canonical_csv_files': len(files),
        'undocumented_actual_fields': unknown,
        'formatted_table_exports': 'English/Chinese headings and complete captions define display columns; canonical full-precision files covered in dictionary',
        'frozen_csv_numerical_values_modified': False,
        'data_files_present': [p.name for p in OUTDATA.glob('Supplementary_Data_*.csv')],
        'script_scope': 'metadata README/dictionary/BibTeX only; no fitting, allocation or data modification'
    }, indent=2), encoding='utf-8')


SOURCE_README = '''# AFIRE Source Data — integrated Supplement

## Scope and status

This local submission package supports the current 2009–2020 manuscript and five mortality outcomes: COPD (J40–J44), chronic lower respiratory diseases (J40–J47), respiratory system diseases (J00–J98), circulatory system diseases (I00–I99), and ischaemic heart disease (I20–I25). It integrates already saved results; it does not refit a mortality model, regenerate an allocation, create new confidence limits, or recompute a multiplicity correction.

The earlier ACS baseline period, dataset publication years and boundary vintage identify sources, not additional study observation years. Outcomes are nested and are not additive independent causes. The file `scope_facts.json` records the frozen scope and key counts.

This is a **local, within-submission access package**, not an assertion that a public repository has been deposited. No repository DOI, release accession or open licence has been invented. Before public deposition the author must confirm third-party redistribution conditions, the data-access statement, the intended repository/version, licence, and the responsible access route for material withheld from redistribution. The supplied checksums authenticate local files, not unknown upstream snapshots.

## File organization and navigation

- `full_results/`: canonical full-precision, in-scope saved analytical and descriptive exports. This includes all 135 health-contrast rows, not just significant or main-figure contrasts.
- `Figure_1/` to `Figure_4/`: panel-level data for the unchanged current main figures. These retain the current main-figure numbering; they are not supplementary figures.
- `figures/Supplementary_Figure_1.csv` to `Supplementary_Figure_7.csv`: source tables for the newly numbered supplementary figures. Their README describes record units, complete contrast coverage and RR/RRR interpretation.
- `tables/Supplementary_Table_01_EN.csv` to `_22_EN.csv` and corresponding `_CN.csv`: editable, display-formatted table exports matching the Supplement. They may round numbers for readability. `tables/full_precision_source_index.csv` maps table numbers to unrounded exports under `tables/full_precision/`; canonical originals are also in `full_results/`.
- `geography/`: archived boundary files, processed display geometry, exact-key diagnostics and map configuration. Read its README before using geographic joins.
- `data_dictionary.csv`: actual field names, definitions, units/scales, observed missing tokens and file mappings for canonical results, main/supplementary figure sources, geography CSVs, and Supplementary Data 1–3. Formatted table headings are described directly in the English table captions/headers rather than treated as machine variable names.
- `../supplementary_data/Supplementary_Data_1.csv` to `_3.csv`: the three explicitly described supporting datasets; their README gives exact filters, row counts and provenance.

CSV exports are UTF-8 (some include a BOM). Original analytical field names and Chinese `outcome_name` values are retained for traceability; this does not mean the English manuscript tables contain Chinese labels. EN display tables are fully English. Import CSV identifiers as text, not automatic spreadsheet numbers. Dates, units and absent-value definitions must not be inferred from formatting alone.

## Health estimates and uncertainty

`health_results.csv` holds 135 rows: A reference interaction (5), B conditional smoke association (25), C common-sample adjustment models (40), D targeted omissions (25), and E paired LST branches (40). The block-specific files preserve those subsets. A record is identified by `outcome_id + analysis_block + model_id + contrast_id`. `sample_hash`, `run_fingerprint`, `imputation_version`, sample counts and formula are part of its provenance. Historic `run_source=recomputed` describes the earlier experiment, not a new fit in this Supplement task.

`beta` is log(RR) in B, but log(RRR), the log ratio of smoke rate ratios per one fixed baseline disadvantage SD, in A/C/D/E. Therefore `percent_estimate = 100 × (exp(beta) − 1)` is a percent change in RR for B and in RRR for A/C/D/E. The old `interaction_percent` field does not change the interpretation of a B row. Positive RRR modification does not imply a positive conditional smoke RR or an absolute attributable-death count.

The fixed smoke IQR is 0.678107947271523 μg/m³. The baseline disadvantage scale and quintiles are not re-estimated after exclusions. Saved confidence limits are ordinary two-sided 95% intervals, using the archived county-cluster variance and Rubin pooling over 30 constrained allocated datasets. These datasets are not independent study replicates. `n_county_years`, not `n_imputations`, is the county-year analysis support. `P_value` is the unadjusted two-sided P value. Only A has the saved `P_adjusted` from the original seven-test Holm family; this is explicitly retained as `original_Holm_family_n7` although only the five current outcomes are reported. No five-test correction was calculated, and B–E do not receive adjusted significance from A. These intervals are not Holm simultaneous intervals.

`common_sample_identity.csv` documents the 3,062-key common-sample comparison and equality of the corresponding frozen allocated values. In contrast, the full reference has 3,072 county-years. Targeted omissions and relaxed/strict LST branches have their own sample support; comparisons must use their named branches, not silently substitute samples. The paired LST fits do not provide a covariance-based difference interval, so none is supplied.

## Counts, suppression and access boundary

`mortality_records.csv` preserves public county-year-outcome counts and suppression flags for 15,360 records. Suppressed `deaths` cells are empty; 325 reported zeros remain zeros. The 3,328 suppressed records are not converted to zero. `state_death_remainders.csv` and `suppression.csv` report state-total conservation remainders and aggregate suppression diagnostics; a remainder is not an identified suppressed county count.

**The allocation-level arrays and reconstructed suppressed county-cell death counts are not redistributed here.** Common-sample hashes and aggregate nested-outcome diagnostics are included instead. The package is sufficient to redraw saved aggregate figures and inspect reported estimates, but does not claim a complete unrestricted refitting dataset. The lawful source route for mortality records is CDC WONDER and its applicable conditions; any proposal to share reconstructed small-cell arrays needs author/institution review. An approved access committee, approval or licence is not asserted where none was supplied.

`validation_evaluation_records.csv` and `validation.csv` concern 2,128 originally visible 10–19-count cells in 298 pseudo-masking groups, using the archived 100 draws and 0–19 support. They are a visible-count analogue, not true suppressed-cell validation. The final mortality analysis uses the separate frozen 30-dataset, 1–9-support procedure. `nested_outcome_check.csv` compares matching array indices across nested outcomes; the diagnostic is not a joint posterior probability and relation counts must not be summed.

## Geographic and source limitations

County identifiers must be five-character strings (`04001`, not numerical 4001); state identifiers must be two-character strings. Some frozen fire/validation files serialize FIPS numerically (for example `6021.0` or `4001`). For a join only, check that a value is integral and left-pad to five digits; preserve the original source field. An unmatched key, an absent exposure and a true zero are different states. Alaska/Hawaii exposure is unavailable, not zero.

The health/exposure county frame comprises 256 counties in AZ/CA/CO/ID/OR/WA. A successful join to 2020 Census cartographic geometry establishes display matching only, not historical areal harmonization. State exposure summaries use 49 exposure-supported jurisdictions including DC; ecological state poverty, county disadvantage, equal-state means and population-weighted county means must not be conflated.

Known upstream metadata gaps remain **PARTIAL**: full smoke download/extraction identity; all disadvantage components, directions and weights; several covariate product releases and native units; archived fire service query/snapshot and full-universe ranking; and complete upstream historical boundary processing. The dictionary does not invent unknown temperature, precipitation or ozone units from model standardization. Supplementary Table 2 documents the authenticated transformation and missing provenance for each model covariate. Current public web documentation confirms source/product identity and definitions, not an unavailable historical download batch.

## Reproduction and citation

From the version directory, `scripts/plot_supplement.py` rebuilds the seven supplementary figures from saved tables; `scripts/build_supplement.py` builds the bilingual Supplement and derives the three Supplementary Data files. They are rendering/assembly scripts, not mortality-model fitting pipelines. `scripts/write_data_documentation.py` only rebuilds the README/dictionary/BibTeX metadata. The scripts must run with the documented local Python dependencies; see the project environment and audit records.

Use `Supplementary_References.bib` and the Supplement's independently numbered reference list for cited public sources and statistical methods. Citation numbers in the manuscript may differ from the internal source IDs; BibTeX keys remain stable. External verification and exact local source hashes are in the non-submission `audit/` folder. No DOI for this derived local package is claimed.

中文核对：这是随稿源数据包，不等于已公开存储库；保留的原始中文字段服务追溯，正式英文表格已英文化；缺失不等于零，Holm 仍沿用原 7 检验家族；受限分配数组未公开，未认证的上游版本和单位仍标记 PARTIAL。
'''


GEOGRAPHY_README = '''# Geographic display data and exact-key checks

The maps use archived U.S. Census Bureau 2020 cartographic boundary files at 1:500,000 scale. The original ZIP downloads and extracted shapefile sidecars under `raw/` are retained. `boundary_provenance.json` records the publisher URL, saved retrieval time, file size, vintage and SHA-256. The current public Census page may have replaced some downloads; only the supplied ZIP checksums identify the local saved files.

- `cb_2020_us_county_500k.zip`: archived county/county-equivalent boundaries.
- `cb_2020_us_state_500k.zip`: archived state/state-equivalent boundaries.
- `counties_256_epsg5070.geojson`: saved geometry for the 256 study counties.
- `states_context_epsg5070.geojson`: saved state/context geometry for the regional map.
- `map_config.json`: source/display CRS, extent, count checks and explicit scope limitation. The native shapefile CRS is EPSG:4269; regional display is NAD83 / Conus Albers (EPSG:5070). GeoJSONs are projected analysis/display exports, not longitude/latitude RFC-7946 web GeoJSON. Read the recorded CRS before use.
- `state_join_audit.csv`: state-key/geometry/exposure availability and inset projection checks. Mainland display is EPSG:5070; inspect the per-row EPSG for Alaska/Hawaii insets.
- **Current county join file:** `../full_results/county_geographic_join.csv`, 256 rows. The old all-period county join audit is not included as a current sample diagnostic.

County counts are AZ 15, CA 58, CO 64, ID 44, OR 36 and WA 39 (total 256). Regional context states NV/UT/WY are background only, not extra mortality-study states. The current map configuration records no missing study counties, extra study counties or duplicated FIPS. A successful key match is not evidence for original exposure allocation, historical boundary harmonization or a temporal crosswalk: none was invented and no observation values were reallocated. No additional geometry simplification is reported beyond the publisher's cartographic product.

FIPS must be strings: state 2 digits, county 5 digits. Some older analytical CSVs contain integer/float-style FIPS tokens, so normalize an integral token and zero-pad only for the join; do not rewrite the frozen source or treat administrative IDs as quantities. A missing geometry, missing exposure and observed zero are distinct. Alaska and Hawaii have a geometry but no available smoke exposure in the current state frame; grey/inset display must not be read as zero smoke.

Fire geometry intersections can produce multiple state assignments for one catalogue record. Centroid administrative labels do not identify an ignition city. Candidate duplicate incident names and years remain flagged, not deleted. See `../../supplementary_data/README.md` for the fire-record boundary.

Source: U.S. Census Bureau, [2020 cartographic boundary files](https://www.census.gov/geographies/mapping-files/2020/geo/carto-boundary-file.html). Cite the source and retain its applicable terms; this package does not apply a new licence to third-party boundaries. A public repository/accession for this local display package has not been assigned.
'''


SUPPLEMENTARY_DATA_README = '''# Supplementary Data 1–3

These CSVs are accompanying data files, not additional numbered Supplementary Tables. They support the 2009–2020 study window and retain the exact already saved numerical precision. `scripts/build_supplement.py::prepare_data` performs only the deterministic filters/flagging described below; no model, allocation, exposure aggregation or fire deduplication is run. `audit/supplementary_data_map.json` records the immediate source path/hash, fields and row count. CSV encoding is UTF-8 with BOM; field names are frozen source names, not a promise that every metadata value is English.

## Supplementary Data 1 — state baseline poverty and mean smoke

`Supplementary_Data_1.csv` contains 49 eligible exposure-supported jurisdictions (48 contiguous states plus DC). Source: `../source_data/full_results/state_baseline_poverty.csv`. Exact transformation: keep rows with case-insensitive `eligible == true`; preserve all source columns and their order. Alaska/Hawaii are not assigned zero exposure or new poverty/exposure values.

Key fields: `state_fips` (2-character string), `state_abbr`, `smoke_mean` (saved equal-year mean concentration across 2009–2020, μg/m³), `poverty_rate` (proportion), `poverty_percent` (100 × proportion), and explicit `baseline_period`, `exposure_period`, `across_year_weight`, `within_state_weight`, `point_weight`. State poverty uses the archived county-total-population weighting and is not the county disadvantage composite. The ACS baseline-period label identifies covariate provenance, not an additional outcome study year. The ecological comparison is descriptive and does not validate the county mortality interaction. Complete archived ACS extraction and some upstream aggregation provenance remain PARTIAL.

## Supplementary Data 2 — state-to-county aggregation diagnostic

`Supplementary_Data_2.csv` contains 72 pairs (6 study states × 12 years). Source: `../source_data/full_results/state_county_bridge.csv`; all rows/columns are copied without numerical changes. `smoke_pm25_annual_burden` is the saved state series and `population_weighted_smoke` the current population-weighted county aggregation (both μg/m³). `difference_saved_minus_current` subtracts the latter from the former, and `ratio_saved_over_current` divides the former by the latter. `n_counties` and `population` give aggregation support.

Differences are retained as diagnostic evidence. The file does not equate different upstream series, estimate a calibration, replace either series, prove a geographic crosswalk or authenticate a missing upstream historical download.

## Supplementary Data 3 — retained fire catalogue records and candidate duplicates

`Supplementary_Data_3.csv` contains 81 already in-scope catalogue records. Source: `../source_data/full_results/fire_catalogue_subset.csv`; all source rows/columns are retained. One final boolean column, `potential_duplicate_name_year`, is true if the record's saved `Rank` appears in `../source_data/full_results/fire_potential_duplicates.csv`. The 28 flagged records form 12 normalized-name/year candidate groups. Flagging is not deduplication or confirmation of event identity.

`Rank` is the prior catalogue label, not a newly calculated complete-universe rank, and gaps are meaningful after interval restriction. `SizeMetricAcres` and `GIS_ACRES` retain acres. `Latitude` and `Longitude` retain saved decimal-degree locations; `centroid_*` and `intersect_*` give administrative assignments and must not be read as verified ignition cities. `city_or_place` remains not determined where no source supports it. FIPS tokens such as `6021.0` are preserved as saved; normalize to five-character strings only for geographic joins. `fire_key`, `UNQE_FIRE_ID` and `GlobalID` preserve record identity without resolving incident/perimeter-version duplication.

There are 89 record-to-state assignments across 13 states, because 8 records have multiple state assignments. Of these assignments, 55 are to the six-state study region, corresponding to 53 catalogue records. These are not 89 or 55 independent unique fires. No causal link to an individual death or county exposure is inferred. Current NIFC/ArcGIS/WFIGS documentation verifies source-service identity only; the complete archived query, snapshot, ranking universe and 2020 service linkage remain PARTIAL. Thus this file is a retained catalogue subset, not an authenticated complete census of the largest independent fires.

## Shared metadata, access and reproducibility boundary

The actual field dictionary is `../source_data/data_dictionary.csv`; source and map limitations are in `../source_data/README.md` and `../source_data/geography/README.md`. Missing/blank is not zero. The original non-English metadata labels are retained for traceability; the corresponding English manuscript tables and legends are English.

These data files contain no allocation-level arrays or reconstructed suppressed county-cell deaths. No repository deposit, public DOI or licence for these derived files is asserted. Author confirmation of third-party conditions and the chosen permanent release/access route remains necessary before external publication. The local evidence package can be inspected without claiming all original upstream inputs or a complete unrestricted mortality-refitting dataset are supplied.
'''


def main():
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in SD.rglob('*.csv') if p.name != 'data_dictionary.csv'}
    bibliography()
    (SD / 'README.md').write_text(SOURCE_README, encoding='utf-8')
    (SD / 'geography/README.md').write_text(GEOGRAPHY_README, encoding='utf-8')
    OUTDATA.mkdir(exist_ok=True)
    (OUTDATA / 'README.md').write_text(SUPPLEMENTARY_DATA_README, encoding='utf-8')
    dictionary()
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in before.items())
    checks = []
    for name in ('county_year_exposure.csv', 'county_map_values.csv', 'county_geographic_join.csv',
                 'mortality_records.csv', 'validation_evaluation_records.csv', 'fire_catalogue_subset.csv'):
        key = 'centroid_county_fips' if name == 'fire_catalogue_subset.csv' else 'county_fips'
        rows = readcsv(SD / 'full_results' / name)
        checks.append(dict(file=name, field=key, rows=len(rows),
                           non_five_digit_tokens=sum(not bool(re.fullmatch(r'\d{5}', r[key])) for r in rows),
                           example=rows[0][key], operation='read-only; original values preserved'))
    writecsv(ROOT / 'audit/data_fips_serialization_check.csv', list(checks[0]), checks)
    data_checks = []
    ranks = {r['Rank'] for r in readcsv(SD / 'full_results/fire_potential_duplicates.csv')}
    for number, name, expected in ((1, 'state_baseline_poverty.csv', 49),
                                   (2, 'state_county_bridge.csv', 72),
                                   (3, 'fire_catalogue_subset.csv', 81)):
        source = readcsv(SD / 'full_results' / name)
        if number == 1:
            source = [r for r in source if r['eligible'].lower() == 'true']
        if number == 3:
            source = [dict(r, potential_duplicate_name_year='true' if r['Rank'] in ranks else 'false') for r in source]
        delivered = readcsv(OUTDATA / ('Supplementary_Data_%d.csv' % number))
        assert delivered == source and len(delivered) == expected
        data_checks.append(dict(id=number, rows=len(delivered), exact_transform_match=True,
                                duplicate_flags=sum(r.get('potential_duplicate_name_year') == 'true' for r in delivered),
                                status='PASS'))
    writecsv(ROOT / 'audit/data_file_transformation_check.csv', list(data_checks[0]), data_checks)
    print('Documentation complete; all %d frozen CSV hashes unchanged.' % len(before))


if __name__ == '__main__':
    main()
