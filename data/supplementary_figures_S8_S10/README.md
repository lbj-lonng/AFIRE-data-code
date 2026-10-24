# Source data and interpretation

All numerical inputs originate from the frozen integrated Supplementary Information version identified in the build script. Original source hashes are recorded under audit. Source data are UTF-8 CSV files with headers; preserve county FIPS as five-character identifiers when opening in spreadsheet software.

## Figure 8

- `S8_ab_county_display_values.csv`: 256 counties, long-term annual-concentration means, unchanged fixed disadvantage and quintile, mean population for traceability, exact county names/FIPS, display row, the two display-only tertile codes and map colours. Tertile codes 0/1/2 mean low/middle/high. No combined risk score is formed. Population is not used to weight panels b–d.
- `S8_ab_bivariate_cell_counts.csv`: county counts for all nine combinations, summing to256.
- `S8_c_county_year_exposure.csv`: 3,072 county–years; `county_smoke_pm25_annual_burden_y` is already annual mean concentration in μg/m³ despite its legacy field name. Never divide it again by365.25.
- `S8_d_quintile_year_means.csv`: 60 quintile–year means and county counts; counties equally weighted, quintile membership fixed across years.
- `S8_display_definitions.json`: full-precision cutpoints, boundary convention, colour palette and square-root heatmap normalization. Heatmap uses raw concentrations with a nonlinear display scale; no concentration is changed or truncated.

## Figure 9

- `S9_a_county_suppression.csv`: each county has60 year–cause records. Numerator counts suppressed records, not hidden deaths.
- `S9_b_state_cause_status_summary.csv`:30 state–cause cells, with numerator, denominator and percentage. Denominators differ by state county count but not by cause within state.
- `S9_c_all_record_statuses.csv`:15,360 records, one per county/year/cause. `record_status`:0=public positive count,1=public zero,2=suppressed. `display_row` matches Figure8. White visual gaps between cause blocks are layout spacing and have no record IDs. There are no unclassified missing records.

## Figure 10

- `S10_a_validation_geography.csv`: all256 counties, including123 with zero eligible evaluation cells. A zero is neither missing exposure nor zero deaths. Count each county/year/cause once, not once per method.
- `S10_b_paired_error_differences.csv`: three comparisons×2,128 matched cells=6,384 rows. Difference=absolute error of first named method minus that of second. Negative favours first method. State/year/cause/FIPS identifies the pair; repeated cells across comparisons are not independent observations.
- `S10_b_descriptive_summary.csv`: descriptive means, medians and fractions below/equal/above zero. Fractions are not P values; ties use the stored floating-point differences. No new uncertainty intervals or hypothesis tests.
- `S10_cd_frozen_performance_metrics.csv`:24 scope–method rows (pooled plus five causes×four methods), copied unchanged in value from the frozen summary. All six metrics retained, although panelsc–d emphasize five complementary quantities.
- `S10_c_loss_ratios_to_equal.csv`:4×3 metric-specific ratios; no pooled composite score. Ratios use full-precision stored metrics, not rounded printed values.

## Geography, independence and uncertainty

`counties_256_epsg5070.geojson` and `states_context_epsg5070.geojson` are copied existing geometries, not newly downloaded boundaries. All256 county identifiers match exactly once. Projection is EPSG:5070;2020 geometry is only a display reference, not proof of historical boundary harmonization. Existing `boundary_provenance.json` and `map_config.json` provide details. Arizona/California/Colorado/Idaho/Oregon/Washington contain15/58/64/44/36/39 study counties. Nevada, Utah and Wyoming are context states only.

Observation window:2009–2020. Mortality outcomes: COPD, chronic lower respiratory diseases, respiratory-system diseases, circulatory-system diseases and ischaemic heart disease. These categories overlap and cannot be added to form mutually exclusive deaths. No new mortality fits, imputations, allocations, bootstrap intervals, correlations or P values are produced. Saved validation count intervals are not regression-effect confidence intervals. The four validation methods share the same298 groups and2,128 cells, and evaluate public10–19 analogues with0–19 support, not genuine suppressed1–9 truth.
