#!/usr/bin/env python3
"""Retry failed model×task combinations from an audit report."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from centaur_benchmark.config import default_tasks_dir, load_task
from centaur_benchmark.io import ensure_run_dir, results_base
from centaur_benchmark.runner import patch_augmentation_models, patch_automation_models

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_run import audit_run  # noqa: E402


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def retry_from_audit(run_id: str, audit: dict) -> list[dict]:
    """Retry each failure; returns list of actions taken."""
    actions: list[dict] = []
    by_task_mode: dict[tuple[str, str], set[str]] = {}
    for f in audit.get("failures", []):
        kind = str(f.get("kind", ""))
        if kind not in {"empty_output", "format_stub", "empty_scaffold", "missing_model"} and not kind.startswith("short<"):
            continue
        key = (f["task"], f["mode"])
        by_task_mode.setdefault(key, set()).add(f["model_id"])

    for (task_slug, mode), model_ids in sorted(by_task_mode.items()):
        if mode == "augmentation":
            # empty_scaffold / missing assistant -> patch augmentation (not plain)
            model_ids = {m for m in model_ids if m != "plain"}
        if not model_ids:
            continue
        task_path = default_tasks_dir() / f"{task_slug}.yaml"
        task = load_task(task_path)
        root = ensure_run_dir(task.slug, run_id)
        ids = sorted(model_ids)
        print(f"=== RETRY {task_slug} {mode} models={ids} ===")
        if mode == "augmentation":
            patch_augmentation_models(task, root, ids)
        else:
            patch_automation_models(task, root, ids)
        actions.append({"task": task_slug, "mode": mode, "model_ids": ids})
    return actions


def main() -> None:
    _load_dotenv()
    os.environ.setdefault("EDSL_API_TIMEOUT", "600")
    os.environ.setdefault("REMOTE_PROXY_TIMEOUT", "600")
    os.environ.setdefault("EDSL_MAX_ATTEMPTS", "8")

    parser = argparse.ArgumentParser(description="Retry failed outputs from audit JSON or fresh audit.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--audit-json", default=None, help="Use existing audit file")
    parser.add_argument("--max-rounds", type=int, default=3)
    args = parser.parse_args()

    audit_path = Path(args.audit_json) if args.audit_json else results_base() / f"audit_{args.run_id}.json"
    for round_i in range(1, args.max_rounds + 1):
        if round_i == 1 and args.audit_json and audit_path.exists():
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        else:
            audit = audit_run(args.run_id)
            audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

        if audit.get("ready_for_judging"):
            print(f"Run {args.run_id} is ready for judging (round {round_i}).")
            return

        failures = audit.get("failures", [])
        if not failures:
            print("No failures but not ready — check missing_tasks.")
            return

        print(f"=== RETRY ROUND {round_i}/{args.max_rounds} ({len(failures)} failures) ===")
        retry_from_audit(args.run_id, audit)
        audit = audit_run(args.run_id)
        audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        if audit.get("ready_for_judging"):
            print(f"Ready for judging after round {round_i}.")
            return

    print(f"Still {len(audit.get('failures', []))} failures after {args.max_rounds} rounds. See {audit_path}")


if __name__ == "__main__":
    main()
