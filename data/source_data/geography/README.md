# Geographic display data and exact-key checks

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
