#!/usr/bin/env python3
"""No-cap repair for DeepSeek automation rows that fail with short stubs."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from audit_all_outputs import audit_all_outputs
from centaur_benchmark.config import default_tasks_dir, load_task
from centaur_benchmark.io import ensure_run_dir, write_json
from centaur_benchmark.runner import generate_automation_replicate
from output_quality import audit_output_row

MODEL_ID = "deepseek-ai/DeepSeek-V3.1"

# Start with runner_attempt=3 to force a 4,096-token request. DeepSeek V3.1
# frequently returns a literal nan/stub on some tasks with 32k/16k/8k caps,
# while a 4k request is still enough for these benchmark deliverables.
_ATTEMPT_CYCLE = (3, 0, 1, 2)


def repair(task_slug: str, run_id: str, attempts: int) -> bool:
    task = load_task(default_tasks_dir() / f"{task_slug}.yaml")
    root = ensure_run_dir(task_slug, run_id)
    label = (task.automation_models or {})[MODEL_ID]
    condition = f"automation_{label.replace(' ', '_')}"
    for attempt in range(1, attempts + 1):
        runner_attempt = _ATTEMPT_CYCLE[(attempt - 1) % len(_ATTEMPT_CYCLE)]
        print(
            f"DeepSeek {task_slug} attempt {attempt}/{attempts} "
            f"run={run_id} runner_attempt={runner_attempt}",
            flush=True,
        )
        try:
            os.environ["CENTAUR_RUN_ID"] = (
                f"{run_id}-deepseek-repair-{task_slug}-{attempt}"
            )
            raw = generate_automation_replicate(
                task,
                root,
                MODEL_ID,
                0,
                attempt=runner_attempt,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"EXCEPTION {type(exc).__name__}: {exc}", flush=True)
            continue
        audit = audit_output_row(raw, task_slug=task_slug, mode="automation", condition=condition)
        print(f"chars={audit['n_chars']} ok={audit['ok']} issues={audit['issues']}", flush=True)
        if not audit["ok"]:
            continue
        print(f"UPSERTED clean DeepSeek {task_slug} row", flush=True)
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempts", type=int, default=4)
    args = parser.parse_args()
    ok = repair(args.task, args.run_id, args.attempts)
    report = audit_all_outputs(args.run_id)
    out = Path(f"results/logs/audit_{args.run_id}_deepseek_{args.task}_no_cap.json")
    write_json(out, report)
    print(f"REPAIR_OK={ok}", flush=True)
    print(f"AUDIT {report['n_ok']}/{report['n_rows']} ok failing={report['n_failing']}", flush=True)
    for failure in report.get("failures", [])[:10]:
        print("FAIL", failure["task"], failure["mode"], failure["model_label"], failure["quality_issues"], flush=True)


if __name__ == "__main__":
    main()
