from __future__ import annotations

import argparse
import json

from census_acquisition import (
    CensusError,
    STATUS_PATH,
    build_standardized_census,
    run_census_download,
    validate_standardized_census,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and validate Census ACS data before the full Afire pipeline.")
    parser.add_argument("--force", action="store_true", help="Redownload all ACS years and Gazetteer.")
    args = parser.parse_args()
    try:
        summary = run_census_download(force=args.force)
        print(
            json.dumps(
                {
                    "years_downloaded": summary.years_downloaded,
                    "years_cached": summary.years_cached,
                    "gazetteer_downloaded": summary.gazetteer_downloaded,
                    "key_source": summary.key_source,
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )
        data = build_standardized_census()
        validation = validate_standardized_census(data)
    except CensusError as exc:
        raise SystemExit(f"Census stage failed: {exc}") from exc
    print("\nCensus stage PASSED.")
    print(f"Status: {STATUS_PATH}")
    print(validation.to_string(index=False))


if __name__ == "__main__":
    main()
