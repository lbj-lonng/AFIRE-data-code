from __future__ import annotations

import csv
import io
import json
import os
import re
import stat
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

ROOT = Path(os.environ.get("AFIRE_COUNTY_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
RAW = ROOT / "data_external" / "raw"
ACS_DIR = RAW / "census_acs"
CONFIG_DIR = ROOT / "config"
TABLES = ROOT / "tables"
LOGS = ROOT / "logs"
ENV_PATH = CONFIG_DIR / "census_api_key.env"
GAZETTEER_PATH = RAW / "census_gazetteer_2020.zip"
STANDARDIZED_PATH = ROOT / "data_external" / "processed" / "census_county_year_six_states_2009_2020.csv"
VALIDATION_PATH = TABLES / "census_validation_v6_2.csv"
STATUS_PATH = LOGS / "census_status_v6_2.json"

STATE_FIPS = {"AZ": "04", "CA": "06", "CO": "08", "ID": "16", "OR": "41", "WA": "53"}
EXPECTED_COUNTIES = {"04": 15, "06": 58, "08": 64, "16": 44, "41": 36, "53": 39}
YEARS = tuple(range(2009, 2021))
ACS_BASE = "https://api.census.gov/data/{year}/acs/acs5"
GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2020_Gazetteer/2020_Gaz_counties_national.zip"
)
USER_AGENT = "Afire-v6.2 Census-first academic downloader/1.0"

ACS_VARIABLES = [
    "NAME",
    "B01001_001E",
    "B01001_020E", "B01001_021E", "B01001_022E", "B01001_023E", "B01001_024E", "B01001_025E",
    "B01001_044E", "B01001_045E", "B01001_046E", "B01001_047E", "B01001_048E", "B01001_049E",
    "B19013_001E",
    "B17001_001E", "B17001_002E",
]


class CensusError(RuntimeError):
    pass


@dataclass(frozen=True)
class DownloadSummary:
    years_downloaded: list[int]
    years_cached: list[int]
    gazetteer_downloaded: bool
    key_source: str


def _ensure_dirs() -> None:
    for path in [RAW, ACS_DIR, CONFIG_DIR, TABLES, LOGS, STANDARDIZED_PATH.parent]:
        path.mkdir(parents=True, exist_ok=True)


def load_env_file(path: Path = ENV_PATH) -> dict[str, str]:
    """Load a small KEY=VALUE file without overriding existing environment variables."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            values[key] = value
            os.environ.setdefault(key, value)
    return values


def get_api_key() -> tuple[str | None, str]:
    direct = os.environ.get("CENSUS_API_KEY", "").strip()
    if direct:
        return direct, "environment"
    loaded = load_env_file()
    from_file = loaded.get("CENSUS_API_KEY", "").strip()
    if from_file:
        return from_file, str(ENV_PATH.relative_to(ROOT))
    return None, "missing"


def mask_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"


def save_api_key(key: str, path: Path = ENV_PATH) -> None:
    _ensure_dirs()
    key = key.strip()
    if not key or any(char.isspace() for char in key):
        raise CensusError("Census API key is empty or contains whitespace")
    path.write_text(
        "# Local credential. Do not upload or commit this file.\n"
        f"CENSUS_API_KEY={key}\n",
        encoding="utf-8",
    )
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _request(
    url: str,
    *,
    params: dict[str, str] | None = None,
    timeout: int = 180,
    retries: int = 5,
) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                url,
                params=params,
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
            )
            if response.status_code == 200:
                return response
            snippet = response.text[:500].replace("\n", " ")
            if response.status_code in {400, 401, 403}:
                raise CensusError(
                    f"Census request rejected (HTTP {response.status_code}). "
                    f"Check that the key was activated. Server message: {snippet}"
                )
            response.raise_for_status()
        except CensusError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(2 ** (attempt - 1), 16))
    raise CensusError(f"Request failed after {retries} attempts: {url}: {last_error}")


def validate_api_key(key: str) -> dict[str, str | int]:
    """Make a minimal official ACS query before downloading all years."""
    response = _request(
        ACS_BASE.format(year=2020),
        params={
            "get": "NAME,B01001_001E",
            "for": "county:*",
            "in": "state:06",
            "key": key,
        },
        timeout=90,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise CensusError(f"Census returned non-JSON content: {response.text[:300]}") from exc
    if not isinstance(payload, list) or len(payload) < 2:
        raise CensusError(f"Unexpected Census response: {str(payload)[:500]}")
    header = payload[0]
    if not {"NAME", "B01001_001E", "state", "county"}.issubset(header):
        raise CensusError(f"Census test response lacks expected columns: {header}")
    return {
        "status": "valid",
        "test_year": 2020,
        "test_state": "California",
        "rows_returned": len(payload) - 1,
        "masked_key": mask_key(key),
    }


def _atomic_write_bytes(content: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=destination.parent, suffix=".part") as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(destination)


def _validate_acs_raw_frame(frame: pd.DataFrame, year: int) -> pd.DataFrame:
    required = set(ACS_VARIABLES + ["state", "county"])
    missing = sorted(required - set(frame.columns))
    if missing:
        raise CensusError(f"ACS {year} is missing fields: {missing}")
    frame = frame.copy()
    frame["state"] = frame["state"].astype(str).str.zfill(2)
    frame["county"] = frame["county"].astype(str).str.zfill(3)
    frame = frame.loc[frame["state"].isin(STATE_FIPS.values())].copy()
    counts = frame.groupby("state")["county"].nunique().to_dict()
    problems = {
        state: {"expected": expected, "observed": int(counts.get(state, 0))}
        for state, expected in EXPECTED_COUNTIES.items()
        if int(counts.get(state, 0)) != expected
    }
    if problems:
        raise CensusError(f"ACS {year} six-state county counts failed: {problems}")
    if frame.duplicated(["state", "county"]).any():
        raise CensusError(f"ACS {year} contains duplicate state/county rows")
    return frame


def download_acs_year(year: int, key: str, force: bool = False) -> str:
    destination = ACS_DIR / f"acs5_county_{year}.csv"
    if destination.exists() and destination.stat().st_size > 0 and not force:
        try:
            cached = pd.read_csv(destination, dtype=str)
            _validate_acs_raw_frame(cached, year)
            return "cached"
        except Exception:
            destination.unlink(missing_ok=True)

    response = _request(
        ACS_BASE.format(year=year),
        params={
            "get": ",".join(ACS_VARIABLES),
            "for": "county:*",
            "key": key,
        },
        timeout=180,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise CensusError(f"ACS {year} returned non-JSON content: {response.text[:300]}") from exc
    if not isinstance(payload, list) or len(payload) < 2:
        raise CensusError(f"ACS {year} returned no data: {str(payload)[:500]}")
    frame = pd.DataFrame(payload[1:], columns=payload[0])
    frame = _validate_acs_raw_frame(frame, year)
    # Save only the six study states to reduce package size and prevent accidental scope drift.
    frame.to_csv(destination, index=False, encoding="utf-8-sig")
    return "downloaded"


def download_gazetteer(force: bool = False) -> bool:
    if GAZETTEER_PATH.exists() and GAZETTEER_PATH.stat().st_size > 0 and not force:
        try:
            with zipfile.ZipFile(GAZETTEER_PATH) as archive:
                if any(name.lower().endswith(".txt") for name in archive.namelist()):
                    return False
        except zipfile.BadZipFile:
            GAZETTEER_PATH.unlink(missing_ok=True)
    response = _request(GAZETTEER_URL, timeout=180)
    _atomic_write_bytes(response.content, GAZETTEER_PATH)
    with zipfile.ZipFile(GAZETTEER_PATH) as archive:
        if not any(name.lower().endswith(".txt") for name in archive.namelist()):
            raise CensusError("Downloaded Gazetteer archive does not contain a text table")
    return True


def run_census_download(force: bool = False) -> DownloadSummary:
    _ensure_dirs()
    key, source = get_api_key()
    missing_years = [year for year in YEARS if not (ACS_DIR / f"acs5_county_{year}.csv").exists()]
    if missing_years or force:
        if not key:
            raise CensusError(
                "CENSUS_API_KEY is missing. Run 01_setup_census.bat first, or set the environment variable."
            )
        validate_api_key(key)

    downloaded: list[int] = []
    cached: list[int] = []
    for number, year in enumerate(YEARS, start=1):
        if not key:
            # Existing cache can be validated without a key.
            frame = pd.read_csv(ACS_DIR / f"acs5_county_{year}.csv", dtype=str)
            _validate_acs_raw_frame(frame, year)
            cached.append(year)
            continue
        status = download_acs_year(year, key, force=force)
        (downloaded if status == "downloaded" else cached).append(year)
        print(f"Census ACS {number:02d}/{len(YEARS)}: {year} -> {status}", flush=True)

    gazetteer_downloaded = download_gazetteer(force=force)
    return DownloadSummary(downloaded, cached, gazetteer_downloaded, source)


def _numeric(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    # ACS uses large negative sentinel values for unavailable estimates.
    return values.mask(values <= -1_000_000)


def build_standardized_census() -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    age_columns = [
        "B01001_020E", "B01001_021E", "B01001_022E", "B01001_023E", "B01001_024E", "B01001_025E",
        "B01001_044E", "B01001_045E", "B01001_046E", "B01001_047E", "B01001_048E", "B01001_049E",
    ]
    for year in YEARS:
        path = ACS_DIR / f"acs5_county_{year}.csv"
        if not path.exists():
            raise CensusError(f"Missing ACS cache: {path}")
        raw = _validate_acs_raw_frame(pd.read_csv(path, dtype=str), year)
        population = _numeric(raw["B01001_001E"])
        age65_count = sum((_numeric(raw[column]) for column in age_columns), start=pd.Series(0.0, index=raw.index))
        state = raw["state"].astype(str).str.zfill(2)
        county = raw["county"].astype(str).str.zfill(3)
        frame = pd.DataFrame(
            {
                "county_fips": state + county,
                "state_fips": state,
                "county_component": county,
                "county_name": raw["NAME"],
                "year": year,
                "acs_population": population,
                "age65_count": age65_count,
                "age65_share": age65_count / population,
                "acs_median_household_income": _numeric(raw["B19013_001E"]),
                "acs_poverty_universe": _numeric(raw["B17001_001E"]),
                "acs_poverty_count": _numeric(raw["B17001_002E"]),
                "acs_poverty_rate": _numeric(raw["B17001_002E"]) / _numeric(raw["B17001_001E"]),
                "acs_vintage": year,
                "acs_period_label": (
                    f"{year - 4}-{year} ACS 5-year" if year >= 2010 else "2005-2009 ACS 5-year"
                ),
            }
        )
        rows.append(frame)
    output = pd.concat(rows, ignore_index=True)

    if not GAZETTEER_PATH.exists():
        raise CensusError("Census Gazetteer archive is missing")
    with zipfile.ZipFile(GAZETTEER_PATH) as archive:
        text_name = next((name for name in archive.namelist() if name.lower().endswith(".txt")), None)
        if not text_name:
            raise CensusError("Gazetteer archive contains no text table")
        with archive.open(text_name) as handle:
            gazetteer = pd.read_csv(handle, sep="\t", dtype=str)
    gazetteer.columns = [column.strip() for column in gazetteer.columns]
    geoid_column = next(column for column in gazetteer if column.upper() == "GEOID")
    area_column = next(column for column in gazetteer if "ALAND_SQMI" in column.upper())
    area = pd.DataFrame(
        {
            "county_fips": gazetteer[geoid_column].astype(str).str.zfill(5),
            "land_area_sqmi_2020": _numeric(gazetteer[area_column]),
        }
    ).drop_duplicates("county_fips")
    output = output.merge(area, on="county_fips", how="left", validate="many_to_one")
    output["land_area_km2_2020"] = output["land_area_sqmi_2020"] * 2.589988110336
    output["population_density_km2"] = output["acs_population"] / output["land_area_km2_2020"]
    output["county_fips"] = output["county_fips"].astype(int)
    output = output.sort_values(["county_fips", "year"]).reset_index(drop=True)
    output.to_csv(STANDARDIZED_PATH, index=False, encoding="utf-8-sig")
    return output


def validate_standardized_census(data: pd.DataFrame | None = None) -> pd.DataFrame:
    if data is None:
        if not STANDARDIZED_PATH.exists():
            data = build_standardized_census()
        else:
            data = pd.read_csv(STANDARDIZED_PATH)
    checks: list[dict[str, object]] = []

    def add(check: str, passed: bool, observed: object, expected: object, severity: str = "error") -> None:
        checks.append(
            {
                "check": check,
                "status": "PASS" if passed else "FAIL",
                "observed": observed,
                "expected": expected,
                "severity": severity,
            }
        )

    add("row_count", len(data) == 256 * len(YEARS), len(data), 256 * len(YEARS))
    add("unique_county_year", not data.duplicated(["county_fips", "year"]).any(), int(data.duplicated(["county_fips", "year"]).sum()), 0)
    add("county_count", data["county_fips"].nunique() == 256, int(data["county_fips"].nunique()), 256)
    add("year_count", data["year"].nunique() == len(YEARS), int(data["year"].nunique()), len(YEARS))
    annual_counts = data.groupby("year")["county_fips"].nunique()
    add("256_counties_each_year", bool((annual_counts == 256).all()), annual_counts.to_dict(), "256 for every year")

    required = ["acs_population", "age65_share", "population_density_km2"]
    for variable in required:
        coverage = float(data[variable].notna().mean()) if variable in data else 0.0
        add(f"coverage_{variable}", coverage >= 0.99, round(coverage, 6), ">=0.99")
    add("population_positive", bool((data["acs_population"].dropna() > 0).all()), int((data["acs_population"] <= 0).sum()), 0)
    add("age65_share_range", bool(data["age65_share"].dropna().between(0, 1).all()), [float(data["age65_share"].min()), float(data["age65_share"].max())], "0 to 1")
    add("density_positive", bool((data["population_density_km2"].dropna() > 0).all()), int((data["population_density_km2"] <= 0).sum()), 0)

    validation = pd.DataFrame(checks)
    validation.to_csv(VALIDATION_PATH, index=False, encoding="utf-8-sig")
    failed = validation.loc[(validation["status"] == "FAIL") & (validation["severity"] == "error")]
    status = {
        "status": "ready" if failed.empty else "failed_validation",
        "standardized_file": _display_path(STANDARDIZED_PATH),
        "validation_file": _display_path(VALIDATION_PATH),
        "rows": int(len(data)),
        "counties": int(data["county_fips"].nunique()),
        "years": [int(data["year"].min()), int(data["year"].max())],
        "failed_checks": failed["check"].tolist(),
    }
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    if not failed.empty:
        raise CensusError(f"Census validation failed: {failed[['check', 'observed', 'expected']].to_dict('records')}")
    return validation




def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)

def census_ready() -> bool:
    if not STATUS_PATH.exists():
        return False
    try:
        status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return status.get("status") == "ready" and STANDARDIZED_PATH.exists()
