"""Build a compact JSON bundle for the static results dashboard."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "20260629_public_rep10"
RUNS = [
    {
        "id": "20260610_scaffold_strict_v4",
        "label": "Run 1",
        "description": "Independent run of the full pipeline.",
    },
    {
        "id": "20260612_fresh_rep1",
        "label": "Run 2",
        "description": "Independent run of the full pipeline.",
    },
    {
        "id": "20260612_fresh_rep2",
        "label": "Run 3",
        "description": "Independent run of the full pipeline.",
    },
    {
        "id": "20260629_public_rep4",
        "label": "Run 4",
        "description": "Public-release replication run.",
    },
    {
        "id": "20260629_public_rep5",
        "label": "Run 5",
        "description": "Public-release replication run.",
    },
    {
        "id": "20260629_public_rep6",
        "label": "Run 6",
        "description": "Public-release replication run.",
    },
    {
        "id": "20260629_public_rep7",
        "label": "Run 7",
        "description": "Public-release replication run.",
    },
    {
        "id": "20260629_public_rep8",
        "label": "Run 8",
        "description": "Public-release replication run.",
    },
    {
        "id": "20260629_public_rep9",
        "label": "Run 9",
        "description": "Public-release replication run.",
    },
    {
        "id": "20260629_public_rep10",
        "label": "Run 10",
        "description": "Public-release replication run.",
    },
]
TASKS = [
    "counselling",
    "market_trends",
    "meal_plan",
    "operations_research",
    "tax_prep",
    "travel_planning",
    "tutoring",
]
TASK_LABELS = {
    "counselling": "Counseling",
    "market_trends": "Market Trends",
    "meal_plan": "Menu Planning",
    "operations_research": "Operations Research",
    "tax_prep": "Tax Prep",
    "travel_planning": "Travel Agent",
    "tutoring": "Tutoring",
}
TASK_TYPES = {
    "counselling": "Human-facing interactive",
    "market_trends": "Professional / analytical",
    "meal_plan": "Structured planning",
    "operations_research": "Professional / analytical",
    "tax_prep": "Professional / analytical",
    "travel_planning": "Structured planning",
    "tutoring": "Human-facing interactive",
}
MODES = ["augmentation", "automation"]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def numberish(value):
    if value is None or value == "":
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return value
    return int(x) if x.is_integer() else x


def convert_numbers(row: dict) -> dict:
    return {k: numberish(v) for k, v in row.items()}


def load_task_yaml(slug: str) -> dict:
    path = ROOT / "tasks" / f"{slug}.yaml"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        return {
            "slug": slug,
            "label": TASK_LABELS[slug],
            "type": TASK_TYPES[slug],
            "title": data.get("title", TASK_LABELS[slug]),
            "task_prompt": data.get("task_prompt", ""),
            "scaffold_prompt": data.get("scaffold_prompt_template", ""),
            "worker_instruction": data.get("worker_instruction", ""),
            "rubric": data.get("pairwise_eval_prompt", ""),
        }
    except Exception:
        def block(key: str) -> str:
            m = re.search(rf"^{key}:\s*(.*?)(?=^[a-zA-Z_]+:|\Z)", text, re.M | re.S)
            return (m.group(1).strip() if m else "").strip("'\"")

        return {
            "slug": slug,
            "label": TASK_LABELS[slug],
            "type": TASK_TYPES[slug],
            "title": block("title") or TASK_LABELS[slug],
            "task_prompt": block("task_prompt"),
            "scaffold_prompt": block("scaffold_prompt_template"),
            "worker_instruction": block("worker_instruction"),
            "rubric": block("pairwise_eval_prompt"),
        }


def slim_output(row: dict, idx: int) -> dict:
    return {
        "idx": idx,
        "replicate_id": row.get("replicate_id"),
        "condition": row.get("condition"),
        "assistant_model": row.get("assistant_model"),
        "worker_model": row.get("worker_model"),
        "model_id": row.get("model_id"),
        "model_label": row.get("model_label"),
        "output": row.get("output", ""),
        "scaffold_text": row.get("scaffold_text", ""),
        "scaffold_path": row.get("scaffold_path", ""),
    }


def parse_json_field(value: str) -> dict:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def slim_judgment(row: dict) -> dict:
    return {
        "left_idx": numberish(row.get("left_idx")),
        "right_idx": numberish(row.get("right_idx")),
        "replicate_id": row.get("replicate_id"),
        "winner": row.get("winner"),
        "short_rationale": row.get("short_rationale", ""),
        "option_1_average": numberish(row.get("option_1_average")),
        "option_2_average": numberish(row.get("option_2_average")),
        "option_1_scores": parse_json_field(row.get("option_1_scores_json", "")),
        "option_2_scores": parse_json_field(row.get("option_2_scores_json", "")),
        "parse_ok": row.get("parse_ok"),
        "judge_model": row.get("judge_model"),
        "judge_label": row.get("judge_label"),
    }


def load_run_bundle(run_id: str) -> dict:
    cross = ROOT / "artifacts" / "cross_task" / run_id
    aggregate = [convert_numbers(r) for r in read_csv(cross / "all_leaderboards_long.csv")]
    by_judge = [convert_numbers(r) for r in read_csv(cross / "all_leaderboards_by_judge_long.csv")]
    corr = [convert_numbers(r) for r in read_csv(cross / "judge_rank_correlation_summary.csv")]
    scatter = [convert_numbers(r) for r in read_csv(cross / "judge_rank_scatter_points.csv")]
    runs: dict[str, dict] = {}
    validations: list[dict] = []
    for task in TASKS:
        for mode in MODES:
            key = f"{task}/{mode}"
            mode_dir = ROOT / "results" / task / run_id / mode
            outputs = [slim_output(r, i) for i, r in enumerate(read_csv(mode_dir / "outputs.csv"))]
            judgments = [slim_judgment(r) for r in read_csv(mode_dir / "pairwise_judgments_by_judge.csv")]
            runs[key] = {
                "task": task,
                "task_label": TASK_LABELS[task],
                "mode": mode,
                "outputs": outputs,
                "judgments": judgments,
            }
            validation_path = mode_dir / "judge_validation.json"
            if validation_path.exists():
                validations.append(
                    {
                        "task_slug": task,
                        "task_label": TASK_LABELS[task],
                        "mode": mode,
                        "validation": json.loads(validation_path.read_text(encoding="utf-8")),
                    }
                )
    return {
        "aggregate": aggregate,
        "by_judge": by_judge,
        "validations": validations,
        "correlations": corr,
        "scatter_points": scatter,
        "runs": runs,
    }


def unique_judgment_count(bundle: dict) -> int:
    seen: set[str] = set()
    for task_mode, run in bundle["runs"].items():
        for j in run["judgments"]:
            a = min(int(j["left_idx"]), int(j["right_idx"]))
            b = max(int(j["left_idx"]), int(j["right_idx"]))
            seen.add(f"{task_mode}|{j.get('judge_model')}|{a}|{b}")
    return len(seen)


def run_stats(bundle: dict) -> dict:
    outputs = sum(len(r["outputs"]) for r in bundle["runs"].values())
    judgments = sum(len(r["judgments"]) for r in bundle["runs"].values())
    return {
        "outputs": outputs,
        "judgments": judgments,
        "unique_judgments": unique_judgment_count(bundle),
    }


def meta_run_bundle(bundle: dict) -> dict:
    return {
        "aggregate": bundle["aggregate"],
        "by_judge": bundle["by_judge"],
        "validations": bundle["validations"],
        "correlations": bundle["correlations"],
        "scatter_points": bundle["scatter_points"],
        "runs": {
            key: {"task": run["task"], "task_label": run["task_label"], "mode": run["mode"]}
            for key, run in bundle["runs"].items()
        },
    }


def qual_run_bundle(bundle: dict) -> dict:
    return {
        "runs": {
            key: {
                "task": run["task"],
                "task_label": run["task_label"],
                "mode": run["mode"],
                "outputs": run["outputs"],
                "judgments": run["judgments"],
            }
            for key, run in bundle["runs"].items()
        }
    }


def main() -> None:
    dashboard = ROOT / "dashboard"
    dashboard.mkdir(exist_ok=True)
    runs_by_id_full = {run["id"]: load_run_bundle(run["id"]) for run in RUNS}
    default_bundle = runs_by_id_full[DEFAULT_RUN_ID]
    stats_by_run = {run_id: run_stats(bundle) for run_id, bundle in runs_by_id_full.items()}
    runs_by_id_meta = {run_id: meta_run_bundle(bundle) for run_id, bundle in runs_by_id_full.items()}
    runs_by_id_qual = {run_id: qual_run_bundle(bundle) for run_id, bundle in runs_by_id_full.items()}

    meta_payload = {
        "meta": {
            "run_id": DEFAULT_RUN_ID,
            "default_run_id": DEFAULT_RUN_ID,
            "replicate_runs": RUNS,
            "run_stats": stats_by_run,
            "generated_from": str(ROOT),
            "notes": "Static dashboard meta bundle (rankings, heatmaps, judge diagnostics). Qualitative outputs lazy-load separately.",
            "data_files": {
                "meta": "dashboard-meta.json",
                "qualitative": "dashboard-qualitative.json",
            },
        },
        "tasks": [load_task_yaml(t) for t in TASKS],
        "modes": MODES,
        "model_sets": {
            "all": {
                "label": "All candidates",
                "exclude": [],
            },
            "no_baseline": {
                "label": "Exclude baselines (assistants only)",
                "exclude": ["plain", "GPT-3.5-Turbo"],
            },
            "frontier_current": {
                "label": "Current non-legacy set",
                "include": [
                    "GPT-5-Mini",
                    "Claude-Sonnet-4.6",
                    "Claude-Opus-4.8",
                    "Gemini-3.1-Pro",
                    "DeepSeek-V3.1",
                    "GPT-OSS-120B",
                ],
            },
        },
        "runs_by_id": runs_by_id_meta,
        "aggregate": default_bundle["aggregate"],
        "by_judge": default_bundle["by_judge"],
        "validations": default_bundle["validations"],
        "correlations": default_bundle["correlations"],
        "scatter_points": default_bundle["scatter_points"],
        "runs": runs_by_id_meta[DEFAULT_RUN_ID]["runs"],
    }
    qual_payload = {"runs_by_id": runs_by_id_qual}

    meta_out = dashboard / "dashboard-meta.json"
    qual_out = dashboard / "dashboard-qualitative.json"
    meta_out.write_text(json.dumps(meta_payload, ensure_ascii=False), encoding="utf-8")
    qual_out.write_text(json.dumps(qual_payload, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {meta_out} ({meta_out.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"Wrote {qual_out} ({qual_out.stat().st_size / 1024 / 1024:.1f} MB)")

    # Monolithic bundle kept for offline tooling; dashboard loads split files.
    legacy = {
        **meta_payload,
        "runs_by_id": runs_by_id_full,
        "runs": runs_by_id_full[DEFAULT_RUN_ID]["runs"],
    }
    legacy_out = dashboard / "dashboard-data.json"
    legacy_out.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {legacy_out} ({legacy_out.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
