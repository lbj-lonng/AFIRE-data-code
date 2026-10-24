# Statistical boundaries of this integration

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
