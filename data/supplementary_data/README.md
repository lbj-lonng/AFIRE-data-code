# Supplementary Data 1–3

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
