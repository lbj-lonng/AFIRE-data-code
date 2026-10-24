# Supplementary figure source data

All CSV files are UTF-8 and preserve the frozen numerical values. None of these
files was produced by a new mortality-model fit, allocation, uncertainty
calculation or multiple-testing correction. Every CSV is a byte-identical copy
of its already in-scope source table. File provenance and hashes are retained
in the non-submission audit rather than in figure labels or captions.

| Figure | Rows | Record unit | Principal plotting fields |
|---|---:|---|---|
| 1 | 72 | State–year | state_abbr, year, population_weighted_smoke |
| 2 | 256 | County | county_fips, state_abbr, smoke_mean |
| 3 | 3 | Expected parent–child relation | relation, draw_violations, any_draw_violations, mean_count_violations |
| 4 | 25 | Outcome × disadvantage level | outcome_id, ses_sd, percent_estimate, percent_CI_lower, percent_CI_upper |
| 5 | 40 | Outcome × common-sample model | outcome_id, model_id, percent_estimate, percent_CI_lower, percent_CI_upper |
| 6 | 25 | Outcome × omission specification | outcome_id, model_id, percent_estimate, percent_CI_lower, percent_CI_upper |
| 7 | 40 | Outcome × LST paired-model branch | outcome_id, model_id, percent_estimate, percent_CI_lower, percent_CI_upper |

## Dictionary and interpretation

- `county_fips`: five-character administrative identifier; preserve leading
  zeros. `state_abbr`: AZ, CA, CO, ID, OR or WA.
- `year`: observation year, 2009–2020. `population_weighted_smoke`: annual
  within-state county-population-weighted smoke PM₂.₅ concentration, μg/m³.
  `smoke_mean`: temporal mean of the county's annual concentration across the
  same period, μg/m³. These are different weighting operations.
- `relation`, `child`, `parent`: expected diagnostic containment relation.
  `draw_violations`: child > parent comparisons across 3,072 county–years and
  30 allocation indices (92,160 per relation). `any_draw_violations`: number of
  county–years inconsistent in at least one allocation; `mean_count_violations`:
  number inconsistent after averaging allocated counts. These are array
  diagnostics, not joint posterior probabilities. Relations are not additive.
- `outcome_id`: `copd`, `chronic_lower_respiratory`, `respiratory_system`,
  `circulatory_system` or `ischemic_heart_disease`, in that display order.
- `analysis_block`: B conditional contrasts, C common-sample environmental
  specifications, D targeted omissions, E LST paired branches. The unique key
  is outcome_id + analysis_block + model_id + contrast_id.
- `ses_sd`: evaluated fixed baseline-disadvantage level; all −2, −1, 0, +1 and
  +2 SD contrasts are retained. `percent_estimate`: 100 × (RR − 1) in Figure 4,
  but 100 × (RRR − 1) for the interaction in Figures 5–7. The fixed smoke IQR is
  0.678107947271523 μg/m³; fixed disadvantage scales are not recalculated.
- `percent_CI_lower`, `percent_CI_upper`: saved ordinary two-sided 95%
  confidence limits under the existing cluster-variance and Rubin procedure;
  they are not Holm simultaneous intervals. `P_value` is an unadjusted
  two-sided P value in blocks B–E. Empty `P_adjusted` is not a zero P value.
- `n_county_years`, `n_counties`, `n_states`, `states`: actual specification
  support. C-block models share 3,062 county–years; D and E sample definitions
  differ as described in their captions and Supplementary Methods.
- `n_imputations` retains the frozen field name for the 30 allocated datasets;
  these are not independent study replicates. `sample_hash`, `run_fingerprint`
  and `imputation_version` preserve model and allocation identity.
- Additional columns preserve the frozen model/diagnostic record for exact
  traceability. Historic `run_source` text describes the source experiment,
  not any re-estimation in this Supplement integration.

No point, interval or county has been excluded for plotting convenience.
All raw county points appear in Figure 2; its boxplot summaries are descriptive
and do not add inferential uncertainty. Other non-inferential panels have no
artificial CI. Please consult the full Supplement and its data-availability
statement for upstream data-access and redistribution limitations; no public
repository deposition is claimed here.
