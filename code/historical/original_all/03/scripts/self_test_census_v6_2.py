from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import pandas as pd

import census_acquisition as census


def main() -> None:
    original = {
        "ACS_DIR": census.ACS_DIR,
        "GAZETTEER_PATH": census.GAZETTEER_PATH,
        "STANDARDIZED_PATH": census.STANDARDIZED_PATH,
        "VALIDATION_PATH": census.VALIDATION_PATH,
        "STATUS_PATH": census.STATUS_PATH,
    }
    try:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            census.ACS_DIR = root / "acs"
            census.ACS_DIR.mkdir()
            census.GAZETTEER_PATH = root / "gazetteer.zip"
            census.STANDARDIZED_PATH = root / "standardized.csv"
            census.VALIDATION_PATH = root / "validation.csv"
            census.STATUS_PATH = root / "status.json"

            county_keys: list[tuple[str, str]] = []
            for state, county_count in census.EXPECTED_COUNTIES.items():
                county_keys.extend((state, f"{county:03d}") for county in range(1, county_count + 1))

            age_columns = [
                "B01001_020E", "B01001_021E", "B01001_022E", "B01001_023E", "B01001_024E", "B01001_025E",
                "B01001_044E", "B01001_045E", "B01001_046E", "B01001_047E", "B01001_048E", "B01001_049E",
            ]
            for year in census.YEARS:
                rows: list[dict[str, str]] = []
                for state, county in county_keys:
                    row = {variable: "100" for variable in census.ACS_VARIABLES}
                    row.update(
                        {
                            "NAME": f"County {county}, State {state}",
                            "B01001_001E": "10000",
                            "B19013_001E": "50000",
                            "B17001_001E": "10000",
                            "B17001_002E": "1000",
                            "state": state,
                            "county": county,
                        }
                    )
                    row.update({column: "200" for column in age_columns})
                    rows.append(row)
                pd.DataFrame(rows).to_csv(census.ACS_DIR / f"acs5_county_{year}.csv", index=False)

            gazetteer_text = "GEOID\tALAND_SQMI\n" + "\n".join(
                f"{state}{county}\t100" for state, county in county_keys
            )
            with zipfile.ZipFile(census.GAZETTEER_PATH, "w") as archive:
                archive.writestr("gazetteer.txt", gazetteer_text)

            standardized = census.build_standardized_census()
            validation = census.validate_standardized_census(standardized)
            assert len(standardized) == 3072
            assert standardized["county_fips"].nunique() == 256
            assert standardized["year"].nunique() == 12
            assert validation["status"].eq("PASS").all()
    finally:
        for name, value in original.items():
            setattr(census, name, value)
    print("Census v6.2 self-test passed: parsing, derivation, county counts, and validation.")


if __name__ == "__main__":
    main()
