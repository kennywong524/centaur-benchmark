#!/usr/bin/env python3
"""Audit a benchmark run for missing or empty outputs and scaffolds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from centaur_benchmark.config import default_tasks_dir, load_task
from centaur_benchmark.io import results_base, write_json

DEFAULT_MIN_OUTPUT_CHARS = 250


def _output_failure_reasons(text: str, *, min_chars: int = DEFAULT_MIN_OUTPUT_CHARS) -> list[str]:
    out = str(text or "").strip()
    if not out:
        return ["empty_output"]
    reasons: list[str] = []
    if out.startswith("{'format':") or out.startswith('{"format":'):
        reasons.append("format_stub")
    if len(out) < min_chars:
        reasons.append(f"short<{min_chars}")
    return reasons


def audit_run(
    run_id: str,
    *,
    task_slugs: list[str] | None = None,
    min_output_chars: int = DEFAULT_MIN_OUTPUT_CHARS,
) -> dict:
    task_paths = sorted(default_tasks_dir().glob("*.yaml"))
    tasks = [load_task(p) for p in task_paths]
    if task_slugs:
        wanted = set(task_slugs)
        tasks = [t for t in tasks if t.slug in wanted]

    report: dict = {
        "run_id": run_id,
        "min_output_chars": min_output_chars,
        "tasks": {},
        "failures": [],
        "missing_tasks": [],
        "ready_for_judging": True,
    }

    for task in tasks:
        root = results_base() / task.slug / run_id
        task_info: dict = {
            "augmentation_outputs": False,
            "automation_outputs": False,
            "bad_outputs": [],
            "bad_scaffolds": [],
            "empty_scaffolds": [],
            "missing_models": {"augmentation": [], "automation": []},
        }

        aug_csv = root / "augmentation" / "outputs.csv"
        auto_csv = root / "automation" / "outputs.csv"
        if not aug_csv.exists() or not auto_csv.exists():
            report["missing_tasks"].append(task.slug)
            report["ready_for_judging"] = False
            report["tasks"][task.slug] = task_info
            continue

        task_info["augmentation_outputs"] = True
        task_info["automation_outputs"] = True

        for mode, path, expected in (
            ("augmentation", aug_csv, set(task.assistants.keys()) | {"plain"}),
            ("automation", auto_csv, set((task.automation_models or {}).keys())),
        ):
            df = pd.read_csv(path)
            for _, row in df.iterrows():
                out = str(row.get("output", "") or "")
                reasons = _output_failure_reasons(out, min_chars=min_output_chars)
                if not reasons:
                    continue
                failure = {
                    "task": task.slug,
                    "mode": mode,
                    "model_id": str(row.get("model_id", "")),
                    "model_label": str(row.get("model_label", "")),
                    "kind": reasons[0],
                    "reasons": reasons,
                    "n_chars": len(out.strip()),
                    "preview": out.strip()[:120],
                }
                task_info["bad_outputs"].append(failure)
                report["failures"].append(failure)
                report["ready_for_judging"] = False

            present = set(df["model_id"].astype(str))
            if mode == "augmentation":
                missing = sorted(expected - present)
            else:
                missing = sorted(expected - present)
            if missing:
                task_info["missing_models"][mode] = missing
                for mid in missing:
                    failure = {
                        "task": task.slug,
                        "mode": mode,
                        "model_id": mid,
                        "model_label": (task.assistants if mode == "augmentation" else task.automation_models or {}).get(mid, mid),
                        "kind": "missing_model",
                    }
                    report["failures"].append(failure)
                    report["ready_for_judging"] = False

        from centaur_benchmark.runner import _safe_slug

        scaffolds_dir = root / "augmentation" / "scaffolds"
        for model_id, model_label in task.assistants.items():
            p = scaffolds_dir / f"{_safe_slug(model_label)}.md"
            if not p.exists() or p.stat().st_size == 0:
                failure = {
                    "task": task.slug,
                    "mode": "augmentation",
                    "model_id": model_id,
                    "model_label": model_label,
                    "kind": "empty_scaffold",
                }
                task_info["empty_scaffolds"].append(failure)
                if not any(
                    f["task"] == task.slug
                    and f["model_id"] == model_id
                    and f["kind"] == "empty_scaffold"
                    for f in report["failures"]
                ):
                    report["failures"].append(failure)
                report["ready_for_judging"] = False
                continue

            scaffold_text = p.read_text(encoding="utf-8", errors="replace")
            scaffold_reasons = _output_failure_reasons(
                scaffold_text, min_chars=min_output_chars
            )
            if scaffold_reasons:
                failure = {
                    "task": task.slug,
                    "mode": "augmentation",
                    "model_id": model_id,
                    "model_label": model_label,
                    "kind": scaffold_reasons[0],
                    "reasons": scaffold_reasons,
                    "n_chars": len(scaffold_text.strip()),
                    "preview": scaffold_text.strip()[:120],
                }
                task_info["bad_scaffolds"].append(failure)
                report["failures"].append(failure)
                report["ready_for_judging"] = False

        report["tasks"][task.slug] = task_info

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit run outputs for completeness.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tasks", default=None, help="Comma-separated task slugs")
    parser.add_argument("--json-out", default=None, help="Write audit JSON path")
    parser.add_argument("--min-chars", type=int, default=DEFAULT_MIN_OUTPUT_CHARS)
    args = parser.parse_args()
    slugs = [x.strip() for x in args.tasks.split(",") if x.strip()] if args.tasks else None
    report = audit_run(args.run_id, task_slugs=slugs, min_output_chars=args.min_chars)
    out = Path(args.json_out) if args.json_out else results_base() / f"audit_{args.run_id}.json"
    write_json(out, report)
    print(f"Audit written to {out}")
    print(f"ready_for_judging={report['ready_for_judging']}")
    print(f"failures={len(report['failures'])} missing_tasks={report['missing_tasks']}")
    for f in report["failures"]:
        print(f"  {f['task']}/{f['mode']}: {f['model_label']} ({f['kind']})")


if __name__ == "__main__":
    main()
