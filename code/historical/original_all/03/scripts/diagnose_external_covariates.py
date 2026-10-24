from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

ROOT = Path(os.environ.get("AFIRE_COUNTY_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
RAW = ROOT / "data_external" / "raw"
TABLES = ROOT / "tables"
LOGS = ROOT / "logs"
TABLES.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)
BASE = ROOT / "data_processed" / "county_year_disease_panel_base_v5.csv"


def expected_counties() -> set[str]:
    data = pd.read_csv(BASE, usecols=["county_fips"]).drop_duplicates()
    return set(
        pd.to_numeric(data["county_fips"], errors="coerce")
        .dropna()
        .astype(int)
        .map(lambda value: f"{value:05d}")
    )


def combine_fips(data: pd.DataFrame) -> pd.Series:
    state = pd.to_numeric(data["statefips"], errors="coerce").astype("Int64")
    county = pd.to_numeric(data["countyfips"], errors="coerce").astype("Int64")
    return state.astype(str).str.zfill(2) + county.astype(str).str.zfill(3)


def noaa_rows(expected: set[str]) -> list[dict]:
    path = RAW / "noaa_cag_county_year.csv"
    if not path.exists():
        old_folder = RAW / "noaa_nclimdiv_county"
        old_count = len(list(old_folder.glob("*.csv"))) if old_folder.exists() else 0
        return [
            {
                "source": "NOAA_CAG",
                "period": "2006-2020",
                "status": "missing_blocking",
                "row_coverage_pct": 0.0,
                "county_coverage_pct": 0.0,
                "detail": (
                    f"Missing {path}. Found {old_count} old NOAA/NIDIS files; D0-D4 drought-category "
                    "columns are not temperature and are intentionally ignored."
                ),
            }
        ]
    data = pd.read_csv(path)
    data["county_fips5"] = (
        pd.to_numeric(data["county_fips"], errors="coerce").astype("Int64").astype(str).str.zfill(5)
    )
    rows = []
    for variable in [
        "temperature_annual_mean",
        "temperature_fireseason_mean",
        "precipitation_annual_total",
        "precipitation_fireseason_total",
    ]:
        if variable not in data.columns:
            rows.append(
                {
                    "source": "NOAA_CAG",
                    "period": variable,
                    "status": "missing_blocking" if variable.startswith("temperature") else "missing_optional",
                    "row_coverage_pct": 0.0,
                    "county_coverage_pct": 0.0,
                    "detail": "Column absent from standardized NOAA output",
                }
            )
            continue
        valid = data[variable].notna()
        row_coverage = float(valid.mean() * 100)
        county_coverage = float(
            len(expected & set(data.loc[valid, "county_fips5"])) / len(expected) * 100
        )
        blocking = variable.startswith("temperature")
        status = "ok" if row_coverage >= 95 else ("incomplete_blocking" if blocking else "incomplete_optional")
        rows.append(
            {
                "source": "NOAA_CAG",
                "period": variable,
                "status": status,
                "row_coverage_pct": row_coverage,
                "county_coverage_pct": county_coverage,
                "detail": "Official Climate-at-a-Glance county-year standardized output",
            }
        )
    return rows


def air_rows(expected: set[str], label: str) -> list[dict]:
    folder = RAW / f"cdc_{label}"
    rows = []
    for year in range(2006, 2021):
        path = folder / f"{label}_county_daily_{year}.csv"
        if not path.exists():
            rows.append(
                {
                    "source": f"CDC_{label.upper()}",
                    "period": year,
                    "status": "missing_blocking" if label == "pm25" else "missing_optional",
                    "row_coverage_pct": 0.0,
                    "county_coverage_pct": 0.0,
                    "detail": str(path),
                }
            )
            continue
        try:
            data = pd.read_csv(path, dtype=str, usecols=["statefips", "countyfips"])
            fips = combine_fips(data)
            obtained = set(fips.dropna())
            coverage = float(len(expected & obtained) / len(expected) * 100)
            observed_states = sorted(
                pd.to_numeric(data["statefips"], errors="coerce").dropna().astype(int).unique().tolist()
            )
            blocking = label == "pm25"
            status = "ok" if coverage >= 95 else ("incomplete_blocking" if blocking else "incomplete_optional")
            rows.append(
                {
                    "source": f"CDC_{label.upper()}",
                    "period": year,
                    "status": status,
                    "row_coverage_pct": None,
                    "county_coverage_pct": coverage,
                    "detail": f"state FIPS={observed_states}; rows={len(data)}",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "source": f"CDC_{label.upper()}",
                    "period": year,
                    "status": "parse_error_blocking" if label == "pm25" else "parse_error_optional",
                    "row_coverage_pct": 0.0,
                    "county_coverage_pct": 0.0,
                    "detail": repr(exc),
                }
            )
    return rows


def places_rows(expected: set[str]) -> list[dict]:
    path = RAW / "cdc_places_smoking_county_year.csv"
    if not path.exists():
        return [
            {
                "source": "CDC_PLACES_SMOKING",
                "period": "2018-2020",
                "status": "missing_optional",
                "row_coverage_pct": 0.0,
                "county_coverage_pct": 0.0,
                "detail": "Smoking is a genuine short-period sensitivity variable, not a core-model blocker.",
            }
        ]
    data = pd.read_csv(path)
    data["county_fips5"] = (
        pd.to_numeric(data["county_fips"], errors="coerce").astype("Int64").astype(str).str.zfill(5)
    )
    rows = []
    for year in [2018, 2019, 2020]:
        subset = data.loc[pd.to_numeric(data["year"], errors="coerce").eq(year)]
        valid = pd.to_numeric(subset.get("smoking_prevalence"), errors="coerce").notna()
        obtained = set(subset.loc[valid, "county_fips5"])
        coverage = float(len(expected & obtained) / len(expected) * 100)
        rows.append(
            {
                "source": "CDC_PLACES_SMOKING",
                "period": year,
                "status": "ok_optional" if coverage >= 95 else "incomplete_optional",
                "row_coverage_pct": float(valid.mean() * 100) if len(subset) else 0.0,
                "county_coverage_pct": coverage,
                "detail": "True PLACES estimate year; never backfilled to earlier years",
            }
        )
    return rows


def main() -> None:
    expected = expected_counties()
    rows: list[dict] = []
    rows.extend(noaa_rows(expected))
    rows.extend(air_rows(expected, "pm25"))
    rows.extend(air_rows(expected, "ozone"))
    rows.extend(places_rows(expected))
    output = pd.DataFrame(rows)
    output.to_csv(TABLES / "external_data_diagnostics_v6_1.csv", index=False, encoding="utf-8-sig")

    blocking_statuses = {
        "missing_blocking",
        "incomplete_blocking",
        "parse_error_blocking",
    }
    blocking = output.loc[output["status"].isin(blocking_statuses)]
    summary = {
        "expected_counties": len(expected),
        "blocking_item_count": int(len(blocking)),
        "blocking_items": blocking[["source", "period", "status", "detail"]].to_dict("records"),
        "method_notes": [
            "NOAA D0-D4 files are drought-category distributions, not temperature.",
            "CDC air queries must use unpadded state FIPS text values 4, 6 and 8 for AZ, CA and CO.",
            "PLACES smoking is restricted to genuine 2018-2020 estimate years and is optional.",
        ],
    }
    (LOGS / "external_data_diagnostics_v6_1.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(output.to_string(index=False))
    print(f"\nBlocking items: {len(blocking)}")


if __name__ == "__main__":
    main()
