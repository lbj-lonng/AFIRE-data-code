from __future__ import annotations

import argparse
import io
import json
import os
import re
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(os.environ.get("AFIRE_COUNTY_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
RAW = ROOT / "data_external" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
PANEL = ROOT / "data_processed" / "county_year_disease_panel_base_v5.csv"

# CDC county air files store FIPS as unpadded text (4, 6, 8, 16, 41, 53).
# Querying 04/06/08 silently omits Arizona, California, and Colorado.
STATE_FIPS_TEXT = {"AZ": "4", "CA": "6", "CO": "8", "ID": "16", "OR": "41", "WA": "53"}
STATE_ABBRS = tuple(STATE_FIPS_TEXT)
UA = "Afire-v6.1 academic county environmental-health downloader/1.0"


def request_bytes(url: str, params=None, timeout=240, retries=5) -> bytes:
    err = None
    headers = {"User-Agent": UA}
    token = os.environ.get("SOCRATA_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.content
        except Exception as exc:  # network-dependent
            err = exc
            time.sleep(min(2**attempt, 20))
    raise RuntimeError(f"Download failed after {retries} attempts: {url}: {err}")


def save_bytes(content: bytes, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(content)
    temporary.replace(destination)
    return destination


def counties() -> pd.DataFrame:
    data = pd.read_csv(PANEL, usecols=["county_fips", "state_abbr"]).drop_duplicates()
    data["county_fips"] = pd.to_numeric(data["county_fips"], errors="raise").astype(int)
    data["county_fips5"] = data["county_fips"].map(lambda value: f"{value:05d}")
    data["county3"] = data["county_fips5"].str[-3:]
    data["noaa_location"] = data["state_abbr"].astype(str) + "-" + data["county3"]
    return data.sort_values("county_fips").reset_index(drop=True)


def parse_noaa_cag_csv(content: bytes) -> pd.DataFrame:
    """Parse an official NOAA Climate-at-a-Glance data-service CSV."""
    text = content.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    header_index = None
    for index, line in enumerate(lines[:100]):
        lower = line.lower()
        if "date" in lower and "," in line and ("value" in lower or "temperature" in lower or "precip" in lower):
            header_index = index
            break
    if header_index is None:
        for index, line in enumerate(lines[:100]):
            if "date" in line.lower() and "," in line:
                header_index = index
                break
    if header_index is None:
        raise ValueError("NOAA CAG response has no recognizable Date/Value header")

    data = pd.read_csv(io.StringIO("\n".join(lines[header_index:])))
    data.columns = [str(column).strip() for column in data.columns]
    lower_map = {column.lower(): column for column in data.columns}
    date_column = lower_map.get("date") or lower_map.get("period") or lower_map.get("year")
    if date_column is None:
        date_column = next((column for column in data.columns if re.search(r"date|period|year", column, re.I)), None)
    value_column = lower_map.get("value")
    if value_column is None:
        excluded = re.compile(r"rank|anomaly|date|period|year", re.I)
        candidates = [column for column in data.columns if not excluded.search(column)]
        numeric_counts = {
            column: pd.to_numeric(data[column], errors="coerce").notna().sum()
            for column in candidates
        }
        value_column = max(numeric_counts, key=numeric_counts.get) if numeric_counts else None
    if date_column is None or value_column is None:
        raise ValueError(f"Unable to identify NOAA date/value columns: {data.columns.tolist()}")

    raw_date = data[date_column].astype(str).str.strip()
    years = raw_date.str.extract(r"((?:19|20)\d{2})", expand=False)
    result = pd.DataFrame(
        {
            "year": pd.to_numeric(years, errors="coerce"),
            "value": pd.to_numeric(data[value_column], errors="coerce"),
        }
    ).dropna()
    result["year"] = result["year"].astype(int)
    result = result.loc[result["year"].between(2006, 2020)].drop_duplicates("year", keep="last")
    if result.empty:
        raise ValueError("NOAA response parsed, but no values fall in 2006-2020")
    return result


def download_noaa(force: bool = False) -> None:
    """Download true county temperature and precipitation from NOAA CAG.

    Official data-service endpoint:
    /county/time-series/{location}/{parameter}/{timescale}/{month}/{years}/data.csv

    Annual: 12-month period ending December.
    Fire season: 6-month period ending October, i.e. May-October.
    NOAA U.S. temperature output is Fahrenheit and precipitation is inches;
    outputs are standardized to degrees Celsius and millimetres.
    """
    raw_directory = RAW / "noaa_cag_county"
    raw_directory.mkdir(exist_ok=True)
    standardized_path = RAW / "noaa_cag_county_year.csv"
    metric_definitions = {
        "temperature_annual_mean": ("tavg", 12, 12, "temperature"),
        "temperature_fireseason_mean": ("tavg", 6, 10, "temperature"),
        "precipitation_annual_total": ("pcp", 12, 12, "precipitation"),
        "precipitation_fireseason_total": ("pcp", 6, 10, "precipitation"),
    }

    all_rows: list[pd.DataFrame] = []
    failures: list[dict] = []
    county_table = counties()
    for county_number, row in enumerate(county_table.itertuples(index=False), start=1):
        yearly = pd.DataFrame({"year": range(2006, 2021)})
        yearly["county_fips"] = int(row.county_fips)
        for variable, (parameter, timescale, ending_month, kind) in metric_definitions.items():
            cache_path = raw_directory / (
                f"{row.county_fips5}_{parameter}_land_{timescale}m_end{ending_month}_2006_2020.csv"
            )
            try:
                if cache_path.exists() and cache_path.stat().st_size > 0 and not force:
                    content = cache_path.read_bytes()
                else:
                    official_url = (
                        "https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/"
                        f"county/time-series/{row.noaa_location}/{parameter}/"
                        f"{timescale}/{ending_month}/2006-2020/data.csv"
                    )
                    content = request_bytes(official_url, timeout=240)
                    save_bytes(content, cache_path)
                parsed = parse_noaa_cag_csv(content)
                if kind == "temperature":
                    parsed[variable] = (parsed["value"] - 32.0) * 5.0 / 9.0
                else:
                    parsed[variable] = parsed["value"] * 25.4
                yearly = yearly.merge(parsed[["year", variable]], on="year", how="left")
            except Exception as exc:
                failures.append(
                    {
                        "county_fips": int(row.county_fips),
                        "noaa_location": row.noaa_location,
                        "variable": variable,
                        "error": repr(exc),
                    }
                )
        all_rows.append(yearly)
        if county_number % 20 == 0 or county_number == len(county_table):
            print(f"NOAA CAG counties: {county_number}/{len(county_table)}", flush=True)

    output = pd.concat(all_rows, ignore_index=True).sort_values(["county_fips", "year"])
    output.to_csv(standardized_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(failures).to_csv(
        RAW / "noaa_cag_download_failures.csv", index=False, encoding="utf-8-sig"
    )

    coverage = {variable: float(output[variable].notna().mean()) for variable in metric_definitions}
    print("NOAA standardized row coverage:", coverage, flush=True)
    temp_values = output[["temperature_annual_mean", "temperature_fireseason_mean"]].stack().dropna()
    precip_values = output[["precipitation_annual_total", "precipitation_fireseason_total"]].stack().dropna()
    if not temp_values.empty and not temp_values.between(-40, 50).all():
        raise RuntimeError("NOAA temperature values failed the -40 to 50 °C plausibility check")
    if not precip_values.empty and not precip_values.between(0, 6000).all():
        raise RuntimeError("NOAA precipitation values failed the 0 to 6000 mm plausibility check")
    if min(coverage.values()) < 0.95:
        raise RuntimeError(
            f"NOAA CAG coverage is below 95%: {coverage}. "
            "Inspect data_external/raw/noaa_cag_download_failures.csv."
        )


def download_census(force: bool = False) -> None:
    """Run the dedicated Census-first downloader and validation stage."""
    from census_acquisition import (
        build_standardized_census,
        run_census_download,
        validate_standardized_census,
    )

    summary = run_census_download(force=force)
    data = build_standardized_census()
    validate_standardized_census(data)
    print(
        "Census ACS/Gazetteer stage completed: "
        f"downloaded={summary.years_downloaded}, cached={summary.years_cached}",
        flush=True,
    )


def socrata_paged(
    dataset_id: str,
    select_fields: list[str],
    where: str,
    order: str,
    page_size: int = 50000,
) -> pd.DataFrame:
    endpoint = f"https://data.cdc.gov/resource/{dataset_id}.csv"
    frames: list[pd.DataFrame] = []
    offset = 0
    while True:
        params = {
            "$select": ",".join(select_fields),
            "$where": where,
            "$order": order,
            "$limit": str(page_size),
            "$offset": str(offset),
        }
        content = request_bytes(endpoint, params=params, timeout=600)
        part = pd.read_csv(io.BytesIO(content), dtype=str)
        if part.empty:
            break
        frames.append(part)
        if len(part) < page_size:
            break
        offset += page_size
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=select_fields)


def normalized_fips(data: pd.DataFrame) -> pd.Series:
    state = pd.to_numeric(data["statefips"], errors="coerce").astype("Int64")
    county = pd.to_numeric(data["countyfips"], errors="coerce").astype("Int64")
    return state.astype(str).str.zfill(2) + county.astype(str).str.zfill(3)


def download_cdc_air_kind(
    dataset_id: str,
    fields: list[str],
    label: str,
    force: bool = False,
) -> None:
    output_directory = RAW / f"cdc_{label}"
    output_directory.mkdir(exist_ok=True)
    expected_fips = set(counties()["county_fips5"])
    states_clause = ",".join(f"'{value}'" for value in STATE_FIPS_TEXT.values())

    for year in range(2006, 2021):
        destination = output_directory / f"{label}_county_daily_{year}.csv"
        valid_cache = False
        if destination.exists() and destination.stat().st_size > 0 and not force:
            try:
                cached = pd.read_csv(destination, dtype=str, usecols=["statefips", "countyfips"])
                cached_fips = set(normalized_fips(cached).dropna())
                valid_cache = len(expected_fips & cached_fips) / len(expected_fips) >= 0.95
            except Exception:
                valid_cache = False
        if valid_cache:
            print(f"CDC {label} {year}: complete cache retained", flush=True)
            continue

        # CDC fields are Text and use unpadded state FIPS values. A single
        # six-state query avoids the previous 04/06/08 mismatch.
        where = (
            f"year='{year}' AND statefips in({states_clause}) "
            "AND countyfips IS NOT NULL"
        )
        data = socrata_paged(dataset_id, fields, where, "statefips,countyfips,date")
        if data.empty:
            raise RuntimeError(f"CDC {label} {year}: API returned no rows")
        save_bytes(data.to_csv(index=False).encode("utf-8-sig"), destination)
        obtained_fips = set(normalized_fips(data).dropna())
        coverage = len(expected_fips & obtained_fips) / len(expected_fips)
        states_observed = sorted(
            pd.to_numeric(data["statefips"], errors="coerce").dropna().astype(int).unique().tolist()
        )
        print(
            f"CDC {label} {year}: rows={len(data):,}; county coverage={coverage:.2%}; "
            f"state FIPS={states_observed}",
            flush=True,
        )
        if coverage < 0.95:
            raise RuntimeError(
                f"CDC {label} {year} county coverage is only {coverage:.2%}. "
                "Inspect the Socrata query and delete the incomplete cached file."
            )


def download_cdc_pm25(force: bool = False) -> None:
    download_cdc_air_kind(
        "53mz-4zqd",
        ["year", "date", "statefips", "countyfips", "pm25_mean_pred", "pm25_pop_pred"],
        "pm25",
        force,
    )


def download_cdc_ozone(force: bool = False) -> None:
    download_cdc_air_kind(
        "3vxk-q2jk",
        ["year", "date", "statefips", "countyfips", "o3_mean_pred", "o3_pop_pred"],
        "ozone",
        force,
    )


def download_cdc_air(force: bool = False) -> None:
    download_cdc_pm25(force)
    download_cdc_ozone(force)


def canonical_column_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def detect_places_columns(data: pd.DataFrame) -> tuple[str, str]:
    canonical = {canonical_column_name(column): column for column in data.columns}
    fips_column = canonical.get("countyfips")
    smoking_candidates = [
        column
        for column in data.columns
        if "csmoking" in canonical_column_name(column)
        and "crude" in canonical_column_name(column)
        and "prev" in canonical_column_name(column)
    ]
    if not smoking_candidates:
        smoking_candidates = [
            column
            for column in data.columns
            if "csmoking" in canonical_column_name(column)
            and "prev" in canonical_column_name(column)
        ]
    smoking_column = smoking_candidates[0] if smoking_candidates else None
    if fips_column is None or smoking_column is None:
        raise RuntimeError(
            "Unable to detect CountyFIPS and CSMOKING crude-prevalence columns. "
            f"Available columns: {data.columns.tolist()}"
        )
    return fips_column, smoking_column


def download_places_smoking(force: bool = False) -> None:
    """Download true PLACES county smoking estimates for 2018-2020.

    2020 PLACES release -> 2018 BRFSS estimate year.
    2021 PLACES release -> 2019 BRFSS estimate year.
    2022 PLACES release -> 2020 BRFSS estimate year.

    Values are not carried backward to 2006-2017 and are used only in a
    2018-2020 sensitivity model.
    """
    releases = {
        2018: ("mssc-ksj7", "PLACES County GIS Friendly, 2020 release"),
        2019: ("kmvs-jkvx", "PLACES County GIS Friendly, 2021 release"),
        2020: ("xyst-f73f", "PLACES County GIS Friendly, 2022 release"),
    }
    destination = RAW / "cdc_places_smoking_county_year.csv"
    if destination.exists() and destination.stat().st_size > 0 and not force:
        try:
            existing = pd.read_csv(destination)
            expected_rows = 3 * len(counties())
            if (
                set(pd.to_numeric(existing["year"], errors="coerce").dropna().astype(int)) == {2018, 2019, 2020}
                and existing["smoking_prevalence"].notna().sum() >= 0.95 * expected_rows
            ):
                print("CDC PLACES smoking: complete cache retained", flush=True)
                return
        except Exception:
            pass

    expected_fips = set(counties()["county_fips5"])
    output_rows: list[pd.DataFrame] = []
    for estimate_year, (dataset_id, release_name) in releases.items():
        endpoint = f"https://data.cdc.gov/resource/{dataset_id}.csv"
        # County GIS-friendly releases contain about 3,100 rows, so one full
        # request is more robust than filtering by a field whose casing changed.
        content = request_bytes(endpoint, params={"$limit": "10000"}, timeout=300)
        raw_data = pd.read_csv(io.BytesIO(content), dtype=str)
        fips_column, smoking_column = detect_places_columns(raw_data)
        fips_numeric = pd.to_numeric(raw_data[fips_column], errors="coerce").astype("Int64")
        prevalence = pd.to_numeric(
            raw_data[smoking_column].astype(str).str.replace("%", "", regex=False), errors="coerce"
        )
        # GIS-friendly crude prevalence is ordinarily percentage points.
        if prevalence.dropna().median() > 1:
            prevalence = prevalence / 100.0
        standardized = pd.DataFrame(
            {
                "county_fips": fips_numeric,
                "year": estimate_year,
                "smoking_prevalence": prevalence,
                "smoking_source_release": release_name,
                "smoking_source_dataset_id": dataset_id,
            }
        ).dropna(subset=["county_fips", "smoking_prevalence"])
        standardized["county_fips5"] = standardized["county_fips"].astype(int).map(lambda value: f"{value:05d}")
        standardized = standardized.loc[standardized["county_fips5"].isin(expected_fips)].drop(columns="county_fips5")
        standardized = standardized.drop_duplicates(["county_fips", "year"])
        obtained = set(standardized["county_fips"].astype(int).map(lambda value: f"{value:05d}"))
        coverage = len(expected_fips & obtained) / len(expected_fips)
        print(f"PLACES smoking estimate year {estimate_year}: coverage={coverage:.2%}", flush=True)
        if coverage < 0.95:
            raise RuntimeError(
                f"PLACES smoking {estimate_year} covers only {coverage:.2%} of study counties"
            )
        output_rows.append(standardized)

    output = pd.concat(output_rows, ignore_index=True).sort_values(["county_fips", "year"])
    output.to_csv(destination, index=False, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        choices=["all", "noaa", "census", "cdc_air", "pm25", "ozone", "places"],
        default="all",
    )
    parser.add_argument("--force", action="store_true", help="Replace cached external files")
    args = parser.parse_args()
    force = args.force or os.environ.get("AFIRE_FORCE_EXTERNAL", "0") == "1"
    functions = {
        "noaa": download_noaa,
        "census": download_census,
        "cdc_air": download_cdc_air,
        "pm25": download_cdc_pm25,
        "ozone": download_cdc_ozone,
        "places": download_places_smoking,
    }
    for name, function in functions.items():
        if args.source in ("all", name):
            print(f"\nDownloading {name}", flush=True)
            function(force)
    print(
        "\nAutomated downloads finished. NCHS urban-rural and HRSA AHRF remain optional inputs; "
        "see docs/REAL_DATA_INPUTS.md.",
        flush=True,
    )


if __name__ == "__main__":
    main()
