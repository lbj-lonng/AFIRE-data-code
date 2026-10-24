from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from v7_common import LOGS, ROOT, load_config
from v7_specs import ALL_SPECS, ESSENTIAL_FINAL_IDS


def selected_specs(suite: str, groups: list[str], model_ids: list[str]):
    specs = ALL_SPECS
    if suite == "final":
        specs = [s for s in specs if s.model_id in ESSENTIAL_FINAL_IDS]
    elif suite == "core":
        specs = [s for s in specs if s.group == "core"]
    elif suite == "all":
        pass
    else:
        raise ValueError(suite)
    if groups:
        specs = [s for s in specs if s.group in groups]
    if model_ids:
        wanted = set(model_ids)
        specs = [s for s in specs if s.model_id in wanted]
    return specs


def run_subprocess(model_id: str) -> tuple[str, int]:
    log_path = LOGS / f"{model_id}.log"
    env = os.environ.copy()
    env["AFIRE_PROJECT_ROOT"] = str(ROOT)
    env.setdefault("OPENBLAS_NUM_THREADS", "1")
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("MKL_NUM_THREADS", "1")
    command = [sys.executable, str(ROOT / "scripts" / "v7_run_model.py"), "--model-id", model_id]
    with log_path.open("a", encoding="utf-8") as handle:
        process = subprocess.run(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
    return model_id, process.returncode


def main() -> None:
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["final", "core", "all"], default="final")
    parser.add_argument("--group", action="append", default=[])
    parser.add_argument("--model-id", action="append", default=[])
    parser.add_argument("--workers", type=int, default=int(config.get("default_workers", 2)))
    args = parser.parse_args()
    specs = selected_specs(args.suite, args.group, args.model_id)
    if not specs:
        raise SystemExit("没有选中任何模型")
    workers = max(1, int(args.workers))
    print(f"Selected {len(specs)} models; workers={workers}", flush=True)
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_subprocess, s.model_id): s.model_id for s in specs}
        for future in as_completed(futures):
            model_id, code = future.result()
            print(f"{model_id}: process_exit={code}", flush=True)
            if code != 0:
                failures.append(model_id)
    if failures:
        print("Processes with nonzero exit:", ", ".join(failures), flush=True)
    print("Suite execution finished. Run aggregation next.", flush=True)


if __name__ == "__main__":
    main()
