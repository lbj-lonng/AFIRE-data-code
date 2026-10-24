# AFIRE Source Data — integrated Supplement

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
