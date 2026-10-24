from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> None:
    downloader = load_module("download_real_covariates", ROOT / "scripts" / "download_real_covariates.py")
    builder = load_module("build_real_covariate_panel", ROOT / "scripts" / "build_real_covariate_panel.py")

    sample_noaa = (
        b"Title,County average temperature\n"
        b"Date,Value,Anomaly\n"
        b"2006,50.0,1.0\n"
        b"2007,51.0,1.2\n"
        b"2020,55.0,2.0\n"
    )
    parsed = downloader.parse_noaa_cag_csv(sample_noaa)
    assert parsed["year"].tolist() == [2006, 2007, 2020]
    assert parsed["value"].tolist() == [50.0, 51.0, 55.0]

    fips_data = pd.DataFrame({"statefips": ["4", "6", "08"], "countyfips": ["013", "37", "031"]})
    assert downloader.normalized_fips(fips_data).tolist() == ["04013", "06037", "08031"]

    places = pd.DataFrame(
        {
            "CountyFIPS": ["04013"],
            "StateAbbr": ["AZ"],
            "CSMOKING_CrudePrev": ["14.2"],
        }
    )
    fips_column, smoke_column = downloader.detect_places_columns(places)
    assert fips_column == "CountyFIPS"
    assert smoke_column == "CSMOKING_CrudePrev"

    dates = pd.Series(["2020-01-02", "01/03/2020", "04JAN2020:00:00:00.000"])
    parsed_dates = builder.parse_cdc_date(dates)
    assert parsed_dates.notna().all()
    assert parsed_dates.dt.year.eq(2020).all()

    source = (ROOT / "scripts" / "download_real_covariates.py").read_text(encoding="utf-8")
    assert '"AZ": "4"' in source and '"CA": "6"' in source and '"CO": "8"' in source
    assert "/land/" in source
    print("v6.1 self-test passed: NOAA parser, FIPS normalization, PLACES schema, and date parser.")


if __name__ == "__main__":
    main()
