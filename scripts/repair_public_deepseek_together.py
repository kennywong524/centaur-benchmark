#!/usr/bin/env python3
"""Repair known public-run DeepSeek automation stubs through Together.

Run this after creating/starting a Together dedicated endpoint for the base
DeepSeek-V3.1 model and setting:

  CENTAUR_DEEPSEEK_ROUTE=together
  CENTAUR_TOGETHER_DEEPSEEK_ENDPOINT=<endpoint id or endpoint model name>

It repairs only the known bad public-release cells unless explicit tasks/runs
are provided.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from audit_all_outputs import audit_all_outputs
from centaur_benchmark.io import write_json
from repair_deepseek_auto_no_cap import repair


DEFAULT_BAD_CELLS: dict[str, list[str]] = {
    "20260629_public_rep4": ["travel_planning", "tutoring"],
    "20260629_public_rep5": ["travel_planning", "tutoring"],
    "20260629_public_rep8": ["travel_planning", "tutoring"],
    "20260629_public_rep9": ["meal_plan", "travel_planning", "tutoring"],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", action="append", help="Run id to repair; may repeat.")
    parser.add_argument("--task", action="append", help="Task slug to repair for every selected run; may repeat.")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()

    if os.environ.get("CENTAUR_DEEPSEEK_ROUTE", "").strip().lower() != "together":
        raise SystemExit("Set CENTAUR_DEEPSEEK_ROUTE=together before running this repair.")
    if not os.environ.get("TOGETHER_API_KEY"):
        raise SystemExit("Set TOGETHER_API_KEY before running this repair.")

    run_ids = args.run_id or list(DEFAULT_BAD_CELLS)
    all_ok = True
    for run_id in run_ids:
        tasks = args.task or DEFAULT_BAD_CELLS.get(run_id, [])
        if not tasks:
            print(f"No default bad cells for {run_id}; pass --task explicitly.")
            continue
        print("=" * 80)
        print(f"RUN {run_id}: tasks={tasks}")
        for task_slug in tasks:
            if args.audit_only:
                continue
            ok = repair(task_slug, run_id, attempts=args.attempts)
            all_ok = all_ok and ok
        report = audit_all_outputs(run_id)
        out = Path(f"results/logs/audit_{run_id}_deepseek_together_repair.json")
        write_json(out, report)
        print(
            f"AUDIT {run_id}: {report['n_ok']}/{report['n_rows']} ok "
            f"failing={report['n_failing']} -> {out}"
        )
        for failure in report.get("failures", [])[:12]:
            print(
                "FAIL",
                failure["task"],
                failure["mode"],
                failure["model_label"],
                failure["quality_issues"],
            )
    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

