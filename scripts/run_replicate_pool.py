#!/usr/bin/env python3
"""Launch multiple independent Centaur replicate runs with bounded parallelism.

This intentionally parallelizes across run IDs, not within one run. Each child
process still uses scripts/run_resumable_batch.py, so per-row quality gates,
checkpoints, audits, and repair loops remain unchanged.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = REPO_ROOT / "results" / "logs"


@dataclass
class RunningJob:
    run_id: str
    process: subprocess.Popen
    log_handle: object
    log_path: Path


def _build_child_command(args: argparse.Namespace, run_id: str) -> list[str]:
    cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(REPO_ROOT / "scripts" / "run_resumable_batch.py"),
        "--run-id",
        run_id,
        "--phase",
        args.phase,
        "--replicates",
        str(args.replicates),
        "--verify",
        "--max-retries",
        str(args.max_retries),
        "--max-repair-rounds",
        str(args.max_repair_rounds),
        "--max-step-failures",
        str(args.max_step_failures),
        "--max-consecutive-failures",
        str(args.max_consecutive_failures),
    ]
    if args.tasks:
        cmd.extend(["--tasks", args.tasks])
    if args.phase == "generation":
        cmd.append("--continue-on-error")
    if args.phase == "judge" and args.n_evals is not None:
        cmd.extend(["--n-evals", str(args.n_evals)])
    if args.skip_variability_gate:
        cmd.append("--skip-variability-gate")
    return cmd


def _child_env(args: argparse.Namespace, run_id: str) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", "src:scripts")
    env["CENTAUR_RUN_ID"] = run_id
    env["CENTAUR_EDSL_MODE"] = args.edsl_mode
    env.setdefault("CENTAUR_EDSL_REMOTE", "0")
    env.setdefault("EDSL_API_TIMEOUT", "1800")
    env.setdefault("REMOTE_PROXY_TIMEOUT", "1800")
    env.setdefault("EDSL_MAX_ATTEMPTS", "8")
    return env


def _start(args: argparse.Namespace, run_id: str) -> RunningJob:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"pool_{run_id}.log"
    log_handle = log_path.open("a", encoding="utf-8")
    cmd = _build_child_command(args, run_id)
    print(f"[start] {run_id} -> {log_path}", flush=True)
    print(" ".join(cmd), file=log_handle, flush=True)
    process = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        env=_child_env(args, run_id),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return RunningJob(run_id=run_id, process=process, log_handle=log_handle, log_path=log_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run multiple independent Centaur replicate run IDs in parallel."
    )
    parser.add_argument("--prefix", default="20260629_public_rep")
    parser.add_argument("--start", type=int, default=4, help="First numeric suffix.")
    parser.add_argument("--count", type=int, default=7, help="Number of run IDs to launch.")
    parser.add_argument("--parallel", type=int, default=2, help="Max concurrent run IDs.")
    parser.add_argument(
        "--phase",
        choices=["generation", "judge", "summarize", "all"],
        default="generation",
    )
    parser.add_argument("--replicates", type=int, default=1)
    parser.add_argument("--tasks", default=None, help="Comma-separated task slugs.")
    parser.add_argument("--n-evals", type=int, default=None)
    parser.add_argument(
        "--edsl-mode",
        default="mixed",
        choices=["ep_proxy", "direct", "mixed", "remote"],
        help="mixed = direct provider keys where possible, EP proxy for proxy-only rows.",
    )
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--max-repair-rounds", type=int, default=5)
    parser.add_argument("--max-step-failures", type=int, default=6)
    parser.add_argument("--max-consecutive-failures", type=int, default=30)
    parser.add_argument("--skip-variability-gate", action="store_true")
    args = parser.parse_args()

    run_ids = [f"{args.prefix}{i}" for i in range(args.start, args.start + args.count)]
    pending = list(run_ids)
    running: list[RunningJob] = []
    failed: list[str] = []
    completed: list[str] = []

    while pending or running:
        while pending and len(running) < max(1, args.parallel):
            running.append(_start(args, pending.pop(0)))

        time.sleep(5)
        still_running: list[RunningJob] = []
        for job in running:
            code = job.process.poll()
            if code is None:
                still_running.append(job)
                continue
            job.log_handle.close()
            if code == 0:
                completed.append(job.run_id)
                print(f"[ok] {job.run_id}", flush=True)
            else:
                failed.append(job.run_id)
                print(f"[fail] {job.run_id} exit={code} log={job.log_path}", flush=True)
        running = still_running

    print(f"Completed: {completed}", flush=True)
    if failed:
        print(f"Failed: {failed}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
