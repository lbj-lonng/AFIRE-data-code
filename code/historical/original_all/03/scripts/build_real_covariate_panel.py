from __future__ import annotations

import json
import os
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get("AFIRE_COUNTY_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
RAW = ROOT / "data_external" / "raw"
OUT = ROOT / "data_external" / "processed"
TABLES = ROOT / "tables"
LOGS = ROOT / "logs"
OUT.mkdir(parents=True, exist_ok=True)
TABLES.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)
BASE = ROOT / "data_processed" / "county_year_disease_panel_base_v5.csv"
STATES = {4, 6, 8, 16, 41, 53}


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def parse_cdc_date(series: pd.Series) -> pd.Series:
    """Parse known CDC date formats without emitting repeated inference warnings."""
    raw = series.astype(str).str.strip()
    result = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns]")
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d-%b-%Y",
        "%d%b%Y:%H:%M:%S.%f",
        "%d%b%Y:%H:%M:%S",
    ]
    for date_format in formats:
        missing = result.isna()
        if not missing.any():
            break
        result.loc[missing] = pd.to_datetime(raw.loc[missing], format=date_format, errors="coerce")
    # Pandas >=2 supports format='mixed'; use it only for genuinely unmatched rows.
    missing = result.isna()
    if missing.any():
        try:
            result.loc[missing] = pd.to_datetime(raw.loc[missing], format="mixed", errors="coerce")
        except (TypeError, ValueError):
            result.loc[missing] = pd.to_datetime(raw.loc[missing], errors="coerce")
    return result


def build_acs() -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for path in sorted((RAW / "census_acs").glob("acs5_county_*.csv")):
        year_match = re.search(r"(\d{4})", path.name)
        if not year_match:
            continue
        year = int(year_match.group(1))
        data = pd.read_csv(path, dtype=str)
        required = {"state", "county", "B01001_001E", "B19013_001E", "B17001_001E", "B17001_002E"}
        if not required.issubset(data.columns):
            raise RuntimeError(f"ACS file lacks required fields: {path}")
        state_numeric = numeric(data["state"]).astype("Int64")
        county_numeric = numeric(data["county"]).astype("Int64")
        data["county_fips"] = (state_numeric.astype(str).str.zfill(2) + county_numeric.astype(str).str.zfill(3)).astype("Int64")
        data = data.loc[state_numeric.isin(STATES)].copy()
        age_columns = [
            "B01001_020E", "B01001_021E", "B01001_022E", "B01001_023E", "B01001_024E", "B01001_025E",
            "B01001_044E", "B01001_045E", "B01001_046E", "B01001_047E", "B01001_048E", "B01001_049E",
        ]
        missing_age = [column for column in age_columns if column not in data.columns]
        if missing_age:
            raise RuntimeError(f"ACS age fields are missing from {path.name}: {missing_age}")
        population = numeric(data["B01001_001E"])
        age65 = sum((numeric(data[column]) for column in age_columns), start=pd.Series(0.0, index=data.index))
        rows.append(
            pd.DataFrame(
                {
                    "county_fips": data["county_fips"],
                    "year": year,
                    "acs_population": population,
                    "age65_share": age65 / population,
                    "acs_median_household_income": numeric(data["B19013_001E"]),
                    "acs_poverty_rate": numeric(data["B17001_002E"]) / numeric(data["B17001_001E"]),
                }
            )
        )
    if not rows:
        return pd.DataFrame()
    output = pd.concat(rows, ignore_index=True)

    gazetteer_path = RAW / "census_gazetteer_2020.zip"
    if gazetteer_path.exists():
        with zipfile.ZipFile(gazetteer_path) as archive:
            text_name = next(name for name in archive.namelist() if name.lower().endswith(".txt"))
            with archive.open(text_name) as file_handle:
                gazetteer = pd.read_csv(file_handle, sep="\t", dtype=str)
        gazetteer.columns = [column.strip() for column in gazetteer.columns]
        geoid_column = next(column for column in gazetteer if column.strip().upper() == "GEOID")
        area_column = next(column for column in gazetteer if "ALAND_SQMI" in column.upper())
        area = pd.DataFrame(
            {
                "county_fips": numeric(gazetteer[geoid_column]).astype("Int64"),
                "land_sqmi": numeric(gazetteer[area_column]),
            }
        ).drop_duplicates("county_fips")
        output = output.merge(area, on="county_fips", how="left", validate="many_to_one")
        output["population_density_km2"] = output["acs_population"] / (output["land_sqmi"] * 2.589988)
    return output.drop_duplicates(["county_fips", "year"])


def build_air(kind: str) -> pd.DataFrame:
    folder = RAW / f"cdc_{kind}"
    rows: list[pd.DataFrame] = []
    population_weighted = "pm25_pop_pred" if kind == "pm25" else "o3_pop_pred"
    area_mean = "pm25_mean_pred" if kind == "pm25" else "o3_mean_pred"
    for path in sorted(folder.glob(f"{kind}_county_daily_*.csv")):
        data = pd.read_csv(path, dtype=str)
        required = {"year", "date", "statefips", "countyfips"}
        if not required.issubset(data.columns):
            raise RuntimeError(f"CDC {kind} file lacks required fields: {path}")
        data["date_parsed"] = parse_cdc_date(data["date"])
        data["year"] = numeric(data["year"]).astype("Int64")
        state = numeric(data["statefips"]).astype("Int64")
        county = numeric(data["countyfips"]).astype("Int64")
        data["county_fips"] = (state.astype(str).str.zfill(2) + county.astype(str).str.zfill(3)).astype("Int64")
        value_column = population_weighted if population_weighted in data.columns else area_mean
        if value_column not in data.columns:
            raise RuntimeError(f"CDC {kind} file has no {population_weighted} or {area_mean}: {path}")
        data["value"] = numeric(data[value_column])
        data["fire_season"] = data["date_parsed"].dt.month.between(5, 10)
        annual = (
            data.groupby(["county_fips", "year"], as_index=False)["value"]
            .mean()
            .rename(columns={"value": f"{kind}_annual_mean"})
        )
        fire_season = (
            data.loc[data["fire_season"]]
            .groupby(["county_fips", "year"], as_index=False)["value"]
            .mean()
            .rename(columns={"value": f"{kind}_fireseason_mean"})
        )
        rows.append(annual.merge(fire_season, on=["county_fips", "year"], how="left", validate="one_to_one"))
    if not rows:
        return pd.DataFrame()
    output = pd.concat(rows, ignore_index=True)
    # If a directory contains duplicate exports, re-aggregate rather than creating duplicate keys.
    value_columns = [column for column in output.columns if column not in {"county_fips", "year"}]
    return output.groupby(["county_fips", "year"], as_index=False)[value_columns].mean()


def build_noaa() -> pd.DataFrame:
    standardized_path = RAW / "noaa_cag_county_year.csv"
    if not standardized_path.exists():
        return pd.DataFrame()
    data = pd.read_csv(standardized_path)
    data["county_fips"] = numeric(data["county_fips"]).astype("Int64")
    data["year"] = numeric(data["year"]).astype("Int64")
    required = {"temperature_annual_mean", "temperature_fireseason_mean"}
    if not required.issubset(data.columns):
        raise RuntimeError(
            "NOAA standardized file does not contain real temperature fields. "
            "The old D0-D4 NIDIS drought-category files cannot be used as temperature."
        )
    allowed = [
        "temperature_annual_mean",
        "temperature_fireseason_mean",
        "precipitation_annual_total",
        "precipitation_fireseason_total",
        "pdsi_annual_mean",
        "pdsi_fireseason_mean",
    ]
    present = [column for column in allowed if column in data.columns]
    return data[["county_fips", "year"] + present].drop_duplicates(["county_fips", "year"])


def optional_csv(filename: str) -> pd.DataFrame:
    path = RAW / filename
    if not path.exists():
        return pd.DataFrame()
    data = pd.read_csv(path)
    if not {"county_fips", "year"}.issubset(data.columns):
        raise RuntimeError(f"Optional input lacks county_fips/year: {path}")
    data["county_fips"] = numeric(data["county_fips"]).astype("Int64")
    data["year"] = numeric(data["year"]).astype("Int64")
    return data.drop_duplicates(["county_fips", "year"])


def coverage_in_window(data: pd.DataFrame, variable: str, first_year: int, last_year: int) -> dict:
    window = data.loc[data["year"].between(first_year, last_year)]
    if variable not in window.columns or window.empty:
        return {
            "variable": variable,
            "year_min": first_year,
            "year_max": last_year,
            "nonmissing_n": 0,
            "expected_n": int(len(window)),
            "nonmissing_pct": 0.0,
            "county_coverage_pct": 0.0,
        }
    nonmissing = window[variable].notna()
    counties_expected = window["county_fips"].nunique()
    counties_observed = window.loc[nonmissing, "county_fips"].nunique()
    return {
        "variable": variable,
        "year_min": first_year,
        "year_max": last_year,
        "nonmissing_n": int(nonmissing.sum()),
        "expected_n": int(len(window)),
        "nonmissing_pct": float(nonmissing.mean() * 100),
        "county_coverage_pct": float(100 * counties_observed / counties_expected) if counties_expected else 0.0,
    }


def main() -> None:
    key = (
        pd.read_csv(BASE, usecols=["county_fips", "year"])
        .drop_duplicates()
        .sort_values(["county_fips", "year"])
    )
    key["county_fips"] = numeric(key["county_fips"]).astype("Int64")
    key["year"] = numeric(key["year"]).astype("Int64")
    parts = [
        build_acs(),
        build_noaa(),
        build_air("pm25"),
        build_air("ozone"),
        optional_csv("cdc_places_smoking_county_year.csv"),
        optional_csv("nchs_urban_rural_county_year.csv"),
        optional_csv("ahrf_county_year.csv"),
    ]
    output = key.copy()
    for part in parts:
        if not part.empty:
            output = output.merge(part, on=["county_fips", "year"], how="left", validate="one_to_one")

    smoke = pd.read_csv(ROOT / "data_reference" / "county_year_smoke_pm25.csv").rename(
        columns={"GEOID": "county_fips"}
    )
    smoke["county_fips"] = numeric(smoke["county_fips"]).astype("Int64")
    smoke["year"] = numeric(smoke["year"]).astype("Int64")
    smoke_columns = [
        "county_fips",
        "year",
        "county_smoke_pm25_annual_burden",
        "county_smoke_days",
        "county_smoke_pm25_mean_smoke_days",
        "county_smoke_pm25_max",
    ]
    output = output.merge(
        smoke[smoke_columns].drop_duplicates(["county_fips", "year"]),
        on=["county_fips", "year"],
        how="left",
        validate="one_to_one",
    )
    if "pm25_annual_mean" in output.columns:
        output["nonwildfire_pm25_candidate"] = (
            output["pm25_annual_mean"] - output["county_smoke_pm25_annual_burden"]
        )
        output["nonwildfire_negative_flag"] = output["nonwildfire_pm25_candidate"].lt(0)

    output_path = OUT / "county_year_real_covariates_v6.csv"
    output.to_csv(output_path, index=False, encoding="utf-8-sig")

    coverage_specs = [
        ("temperature_annual_mean", 2006, 2020),
        ("temperature_fireseason_mean", 2006, 2020),
        ("precipitation_annual_total", 2006, 2020),
        ("precipitation_fireseason_total", 2006, 2020),
        ("pm25_annual_mean", 2006, 2020),
        ("pm25_fireseason_mean", 2006, 2020),
        ("ozone_annual_mean", 2006, 2020),
        ("ozone_fireseason_mean", 2006, 2020),
        ("age65_share", 2009, 2020),
        ("population_density_km2", 2009, 2020),
        ("smoking_prevalence", 2018, 2020),
    ]
    coverage_rows = [coverage_in_window(output, *spec) for spec in coverage_specs]
    coverage = pd.DataFrame(coverage_rows)
    coverage.to_csv(TABLES / "covariate_completeness_v6.csv", index=False, encoding="utf-8-sig")
    coverage.to_csv(TABLES / "covariate_completeness_v6_1.csv", index=False, encoding="utf-8-sig")

    coverage_map = coverage.set_index("variable")["nonmissing_pct"].to_dict()
    core_required = [
        "temperature_annual_mean",
        "temperature_fireseason_mean",
        "age65_share",
        "population_density_km2",
    ]
    environmental_required = ["pm25_annual_mean"]
    missing_core = [variable for variable in core_required if coverage_map.get(variable, 0.0) < 95.0]
    missing_environment = [
        variable for variable in environmental_required if coverage_map.get(variable, 0.0) < 95.0
    ]
    smoking_ready = coverage_map.get("smoking_prevalence", 0.0) >= 95.0
    status = {
        "n_rows": int(len(output)),
        "n_counties": int(output["county_fips"].nunique()),
        "core_model_ready": not missing_core,
        "environmental_model_ready": not missing_environment,
        "all_requested_covariates_ready": not missing_core and not missing_environment,
        # Backward-compatible gate: M2/M3 can run without pretending that
        # smoking exists before PLACES county releases.
        "full_model_ready": not missing_core,
        "missing_required_for_core_model": missing_core,
        "missing_required_for_environmental_model": missing_environment,
        "missing_required_for_full_model": missing_core,
        "smoking_is_optional_sensitivity": True,
        "smoking_sensitivity_ready_2018_2020": smoking_ready,
        "smoking_nonmissing_pct_2018_2020": float(coverage_map.get("smoking_prevalence", 0.0)),
        "coverage_threshold_pct": 95.0,
        "output": str(output_path.relative_to(ROOT)),
    }
    (LOGS / "covariate_build_status_v6.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (LOGS / "covariate_build_status_v6_1.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
