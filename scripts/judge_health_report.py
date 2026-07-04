#!/usr/bin/env python3
"""Report panel-judge health for one or more benchmark runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from centaur_benchmark.config import default_tasks_dir, load_task
from centaur_benchmark.io import results_base

REQUIRED_ARTIFACTS = (
    "pairwise_judgments_by_judge.csv",
    "pairwise_ranked_by_judge.csv",
    "leaderboard_by_judge.csv",
    "leaderboard_aggregate.csv",
    "rubric_scores_long.csv",
    "rubric_scores_summary.csv",
)


def _task_slugs(explicit: list[str] | None) -> list[str]:
    if explicit:
        return explicit
    return sorted(p.stem for p in default_tasks_dir().glob("*.yaml"))


def _health_rows(run_id: str, task_slugs: list[str] | None) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    flags: list[str] = []
    for task_slug in _task_slugs(task_slugs):
        task = load_task(default_tasks_dir() / f"{task_slug}.yaml")
        eval_models = task.evaluator_models or {}
        for mode in ("augmentation", "automation"):
            root = results_base() / task_slug / run_id / mode
            jv_path = root / "judge_validation.json"
            aggregate_path = root / "leaderboard_aggregate.csv"
            missing_artifacts = [name for name in REQUIRED_ARTIFACTS if not (root / name).is_file()]
            aggregate_judges: list[str] = []
            judge_info: dict = {}
            if jv_path.is_file():
                payload = json.loads(jv_path.read_text(encoding="utf-8"))
                judge_info = payload.get("judges", {})
                aggregate_judges = list(payload.get("aggregate_judges") or [])

            if not jv_path.is_file():
                for model_id, label in eval_models.items():
                    rows.append(
                        {
                            "run_id": run_id,
                            "task": task_slug,
                            "mode": mode,
                            "judge_model": model_id,
                            "judge_label": label,
                            "pairwise_rows": 0,
                            "parsed_rows": 0,
                            "parse_pass_rate": 0.0,
                            "batch_ok": False,
                            "included_in_aggregate": False,
                        }
                    )
                flags.append(f"{run_id} {task_slug}/{mode}: missing judge_validation.json")
                if missing_artifacts:
                    flags.append(
                        f"{run_id} {task_slug}/{mode}: missing artifacts {missing_artifacts}"
                    )
                if not aggregate_path.is_file():
                    flags.append(f"{run_id} {task_slug}/{mode}: missing leaderboard_aggregate.csv")
                continue

            seen_labels: set[str] = set()
            for model_id, label in eval_models.items():
                info = judge_info.get(label, {})
                n_rows = int(info.get("n_rows") or 0)
                n_passing = int(info.get("n_passing") or 0)
                pass_rate = float(info.get("row_pass_rate") or 0.0)
                batch_ok = bool(info.get("batch_ok", False))
                included = label in aggregate_judges
                rows.append(
                    {
                        "run_id": run_id,
                        "task": task_slug,
                        "mode": mode,
                        "judge_model": model_id,
                        "judge_label": label,
                        "pairwise_rows": n_rows,
                        "parsed_rows": n_passing,
                        "parse_pass_rate": round(pass_rate, 4),
                        "batch_ok": batch_ok,
                        "included_in_aggregate": included,
                    }
                )
                seen_labels.add(label)
                if n_rows == 0:
                    flags.append(f"{run_id} {task_slug}/{mode}: {label} has 0 rows")

            for label, info in judge_info.items():
                if label in seen_labels:
                    continue
                n_rows = int(info.get("n_rows") or 0)
                n_passing = int(info.get("n_passing") or 0)
                rows.append(
                    {
                        "run_id": run_id,
                        "task": task_slug,
                        "mode": mode,
                        "judge_model": str(info.get("judge_model") or label),
                        "judge_label": label,
                        "pairwise_rows": n_rows,
                        "parsed_rows": n_passing,
                        "parse_pass_rate": round(float(info.get("row_pass_rate") or 0.0), 4),
                        "batch_ok": bool(info.get("batch_ok", False)),
                        "included_in_aggregate": label in aggregate_judges,
                    }
                )
                if n_rows == 0:
                    flags.append(f"{run_id} {task_slug}/{mode}: {label} has 0 rows")

            if len(aggregate_judges) < 2:
                flags.append(
                    f"{run_id} {task_slug}/{mode}: only {len(aggregate_judges)} judge(s) in aggregate "
                    f"({aggregate_judges or 'none'})"
                )
            if not aggregate_path.is_file():
                flags.append(f"{run_id} {task_slug}/{mode}: missing leaderboard_aggregate.csv")
            if missing_artifacts:
                flags.append(
                    f"{run_id} {task_slug}/{mode}: missing artifacts {missing_artifacts}"
                )
    return rows, flags


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", action="append", required=True)
    parser.add_argument("--tasks", default=None, help="Comma-separated task slugs.")
    parser.add_argument(
        "--csv-out",
        default=None,
        help="Write combined health table CSV (default: results/logs/judge_health_<run>.csv)",
    )
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    task_slugs = [x.strip() for x in args.tasks.split(",") if x.strip()] if args.tasks else None
    all_rows: list[dict] = []
    all_flags: list[str] = []
    for run_id in args.run_id:
        rows, flags = _health_rows(run_id, task_slugs)
        all_rows.extend(rows)
        all_flags.extend(flags)
        df = pd.DataFrame(rows)
        csv_out = args.csv_out or str(results_base() / "logs" / f"judge_health_{run_id}.csv")
        if args.csv_out is None or len(args.run_id) == 1:
            run_csv = str(results_base() / "logs" / f"judge_health_{run_id}.csv")
        else:
            run_csv = csv_out.replace(".csv", f"_{run_id}.csv") if csv_out.endswith(".csv") else csv_out
        Path(run_csv).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(run_csv, index=False)
        print(f"Wrote {run_csv} ({len(df)} rows)")
        print(f"=== HEALTH {run_id} ===")
        if df.empty:
            print("(no judge artifacts yet)")
        else:
            print(
                df.to_string(
                    index=False,
                    columns=[
                        "task",
                        "mode",
                        "judge_label",
                        "pairwise_rows",
                        "parsed_rows",
                        "parse_pass_rate",
                        "batch_ok",
                        "included_in_aggregate",
                    ],
                )
            )
        total_pairwise = int(df["pairwise_rows"].sum()) if not df.empty else 0
        included = df[df["included_in_aggregate"]]["judge_label"].nunique() if not df.empty else 0
        print(f"total_pairwise_rows={total_pairwise}")
        if flags:
            print("FLAGS:")
            for flag in flags:
                print(f"  - {flag}")
        else:
            print("FLAGS: none")
        print()

    if args.json_out:
        payload = {"rows": all_rows, "flags": all_flags}
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {args.json_out}")

    if all_flags:
        sys.exit(2)


if __name__ == "__main__":
    main()
