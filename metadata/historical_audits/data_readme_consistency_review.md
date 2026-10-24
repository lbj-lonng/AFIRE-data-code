# Source Data README / dictionary consistency review

Reviewed against the delivered files and actual `write_data_documentation.py` output. No figure, numerical value, main text or Supplement prose was modified during this review.

| Topic | Status | Evidence / interpretation |
|---|---|---|
| Actual-field coverage | PASS | 230 canonical machine fields across 61 CSVs; no undocumented actual field. Bilingual display-table headings/captions are separately supplied, with unrounded-source index. |
| Data 1 / 2 / 3 transformations | PASS | Exact source-to-delivery checks: eligible state rows 49; bridge rows 72 unchanged; fire rows 81 unchanged plus 28 candidate flags. No fire deduplication or new ranking. |
| Health effect scales | PASS | Overall README, figure README and dictionary all distinguish conditional RR (B) from interaction RRR (A/C/D/E), and retain fixed smoke IQR and baseline SD. |
| P values and intervals | PASS | Saved original seven-test Holm correction only in A; B–E use unadjusted P. Ordinary 95% intervals are not multiplicity-adjusted simultaneous intervals. |
| Missing and suppressed values | PASS | Blank/suppressed is not zero; public zeros are retained. Aggregated state remainders are not identified suppressed county counts. No restricted allocation array is redistributed. |
| FIPS serialization | PASS WITH EXPLICIT NORMALIZATION RULE | Principal county panel/map/current-join/mortality columns are five-digit tokens; validation has 4,032 of 8,512 records with non-five-digit tokens and fire catalogue has 81 floating-point-style FIPS tokens. README/dictionary preserve raw values and require integral-value checking and zero-padding only for joins. |
| Geography frame | PASS | Current county join is full_results/county_geographic_join.csv (256 units); no obsolete all-period county join audit is represented as the current denominator. GeoJSON is explicitly projected EPSG:5070, not longitude/latitude web GeoJSON. |
| State versus county weights | PASS | 49 exposure-supported jurisdictions, equal-state annual statistics, county-population weighting and the ecological poverty proxy are distinguished. Missing Alaska/Hawaii exposure is not zero. |
| Validation / allocation distinction | PASS | Visible 10–19 analogue: 2,128 cells and 298 groups, 100 validation draws and 0–19 support; pooled mortality uses separate 30 allocated datasets with 1–9 support. The 8,512 validation evaluation rows reflect comparator-specific repeated evaluation of those cells. |
| Language / precision | PASS | Original source-field names and Chinese outcome metadata retained for traceability; official EN manuscript table exports are English. Display rounding is distinguished from frozen full precision. |
| Upstream units / downloads / rights | PARTIAL, CONSISTENTLY DISCLOSED | Unknown original covariate units, some product snapshots and composite construction are not guessed. Source identity/current metadata is not claimed to certify an unknown archived extraction. No public repository DOI, licence or approved access authority is fabricated. |
| Source immutability | PASS | Documentation script checked all 130 frozen CSV hashes before/after, with no change. |

Supporting records: `data_documentation_check.json`, `data_file_transformation_check.csv`, `data_fips_serialization_check.csv`, `supplementary_data_map.json`, and the field/source mappings in `submission/source_data/data_dictionary.csv`.
