from __future__ import annotations

import argparse
import getpass
import sys

from census_acquisition import CensusError, ENV_PATH, save_api_key, validate_api_key


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure and verify a Census Data API key.")
    parser.add_argument("--key", help="API key. Prefer interactive entry to avoid command history.")
    parser.add_argument("--no-test", action="store_true", help="Save without an online validation request.")
    args = parser.parse_args()

    key = (args.key or getpass.getpass("Paste the activated Census API key (input is hidden): ")).strip()
    if not key:
        raise SystemExit("No key was entered.")
    try:
        if not args.no_test:
            result = validate_api_key(key)
            print(
                f"Key validation passed: {result['rows_returned']} California counties returned; "
                f"masked key {result['masked_key']}.",
                flush=True,
            )
        save_api_key(key)
    except CensusError as exc:
        raise SystemExit(f"Census key setup failed: {exc}") from exc
    print(f"Saved locally to: {ENV_PATH}")
    print("This file is excluded from the project ZIP and must not be uploaded or committed.")


if __name__ == "__main__":
    main()
