from __future__ import annotations

import argparse

from v7_engine import run_model
from v7_specs import SPEC_BY_ID


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True, choices=sorted(SPEC_BY_ID))
    parser.add_argument("--no-retry-failures", action="store_true")
    args = parser.parse_args()
    run_model(SPEC_BY_ID[args.model_id], retry_failures=not args.no_retry_failures)


if __name__ == "__main__":
    main()
