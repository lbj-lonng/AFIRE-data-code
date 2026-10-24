from __future__ import annotations

from census_acquisition import CensusError, build_standardized_census, validate_standardized_census


def main() -> None:
    try:
        data = build_standardized_census()
        result = validate_standardized_census(data)
    except CensusError as exc:
        raise SystemExit(f"Census validation failed: {exc}") from exc
    print(result.to_string(index=False))
    print("Census validation PASSED.")


if __name__ == "__main__":
    main()
