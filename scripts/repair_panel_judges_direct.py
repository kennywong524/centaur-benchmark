#!/usr/bin/env python3
"""Repair failed panel judges with direct provider calls, then rebuild aggregates.

Fallback order for Claude (default):
1. Direct Anthropic API (model from CENTAUR_MODEL_ALIAS_ANTHROPIC_CLAUDE_OPUS_4_8 or claude-opus-4-8)
2. If 404/not_found, try claude-opus-4-20250514
3. If batch still fails, retry direct with workers=1, timeout=600, attempts=10
4. If --edsl-fallback (default on), rerun only the failed Claude cell via EDSL mixed mode,
   then rebuild aggregate from all per-judge CSVs (never trust a Claude-only aggregate)

This is intentionally separate from the main EDSL judge path. It is for cases
where a provider-backed EDSL judge batch returned missing/clipped judgments but
the candidate outputs are already clean. The script rewrites only the requested
per-judge CSVs and then rebuilds the panel aggregate from every available
per-judge CSV in the task/mode directory.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
import re

import pandas as pd

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from centaur_benchmark.config import TaskConfig, default_tasks_dir, load_task  # noqa: E402
from centaur_benchmark.edsl_runtime import provider_model_name  # noqa: E402
from centaur_benchmark.io import results_base  # noqa: E402
from centaur_benchmark.judge_pairwise import (  # noqa: E402
    _aggregate_panel_leaderboard,
    _build_judge_instruction,
    _build_scenarios_augmentation,
    _build_scenarios_automation,
    _ensure_augmentation_columns,
    _filter_scenarios_for_judge,
    _leaderboard_from_panel_scored,
    _parse_pairwise_judgments,
    _pairwise_user_prompt,
    _prep_df,
    _safe_file_slug,
    _scenario_data,
    _score_from_pairwise,
    _write_panel_matrices,
    _write_score_summaries,
    validate_judge_batch,
)


PARSED_COLUMNS = {
    "winner",
    "short_rationale",
    "option_1_scores_json",
    "option_2_scores_json",
    "option_1_average",
    "option_2_average",
    "parse_ok",
}


def _load_dotenv() -> None:
    env_path = _REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _http_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    attempts: int,
    timeout: int,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"HTTP {exc.code}: {body[:800]}")
            if exc.code not in {408, 409, 429, 500, 502, 503, 504}:
                raise last_error
        except Exception as exc:  # noqa: BLE001 - network repair should retry broad transient errors
            last_error = exc
        if attempt < attempts:
            time.sleep(min(30, 2**attempt))
    raise RuntimeError(f"Provider call failed after {attempts} attempts: {last_error}")


def _claude_model_candidates() -> list[str]:
    """Direct Anthropic model ids to try, in order."""
    models: list[str] = []
    alias = os.environ.get("CENTAUR_MODEL_ALIAS_ANTHROPIC_CLAUDE_OPUS_4_8", "").strip()
    if alias:
        models.append(alias)
    else:
        models.append("claude-opus-4-8")
    fallback = "claude-opus-4-20250514"
    if fallback not in models:
        models.append(fallback)
    return models


def _native_model_id(model_id: str) -> str:
    if model_id == "anthropic/claude-opus-4-8":
        return _claude_model_candidates()[0]
    if model_id == "google/gemini-3.1-pro":
        return os.environ.get(
            "CENTAUR_MODEL_ALIAS_GOOGLE_GEMINI_3_1_PRO", "gemini-3.1-pro-preview"
        ).strip() or "gemini-3.1-pro-preview"
    suffix = re.sub(r"[^A-Za-z0-9]+", "_", model_id).strip("_").upper()
    alias = os.environ.get(f"CENTAUR_MODEL_ALIAS_{suffix}", "").strip()
    if alias:
        return alias
    provider_id, _ = provider_model_name(model_id)
    if "/" in provider_id:
        provider_id = provider_id.split("/", 1)[1]
    return provider_id


def _call_claude_model(
    model: str,
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int,
    attempts: int | None = None,
    timeout: int | None = None,
) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    data = _http_json(
        "https://api.anthropic.com/v1/messages",
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        payload=payload,
        attempts=attempts or int(os.environ.get("CENTAUR_DIRECT_JUDGE_ATTEMPTS", "6")),
        timeout=timeout or int(os.environ.get("CENTAUR_DIRECT_JUDGE_TIMEOUT", "240")),
    )
    parts = data.get("content") or []
    text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
    if not text.strip():
        raise RuntimeError(f"Anthropic returned no text: {str(data)[:800]}")
    return text.strip()


def _call_claude(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int,
    attempts: int | None = None,
    timeout: int | None = None,
) -> str:
    last_error: Exception | None = None
    for model in _claude_model_candidates():
        try:
            return _call_claude_model(
                model,
                system_prompt,
                user_prompt,
                max_tokens=max_tokens,
                attempts=attempts,
                timeout=timeout,
            )
        except RuntimeError as exc:
            last_error = exc
            msg = str(exc).lower()
            if "404" in msg or "not_found" in msg:
                print(f"  Claude model {model!r} unavailable; trying next candidate", flush=True)
                continue
            raise
    raise RuntimeError(f"All Claude model candidates failed: {last_error}")


def _call_gemini(system_prompt: str, user_prompt: str, *, max_tokens: int) -> str:
    api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set")
    model = _native_model_id("google/gemini-3.1-pro")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent?key={api_key}"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    data = _http_json(
        url,
        headers={"content-type": "application/json"},
        payload=payload,
        attempts=int(os.environ.get("CENTAUR_DIRECT_JUDGE_ATTEMPTS", "6")),
        timeout=int(os.environ.get("CENTAUR_DIRECT_JUDGE_TIMEOUT", "240")),
    )
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {str(data)[:800]}")
    cand = candidates[0]
    finish = str(cand.get("finishReason", ""))
    parts = ((cand.get("content") or {}).get("parts") or [])
    text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
    if not text.strip():
        raise RuntimeError(f"Gemini returned no text: {str(data)[:800]}")
    if finish.upper() == "MAX_TOKENS":
        raise RuntimeError("Gemini judgment hit MAX_TOKENS")
    return text.strip()


def _call_direct_judge(
    judge_model: str,
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    attempts: int | None = None,
    timeout: int | None = None,
) -> str:
    low = judge_model.lower()
    if "claude" in low or "anthropic" in low:
        return _call_claude(
            system_prompt,
            user_prompt,
            max_tokens=max_tokens,
            attempts=attempts,
            timeout=timeout,
        )
    if "gemini" in low or "google" in low:
        return _call_gemini(system_prompt, user_prompt, max_tokens=max_tokens)
    raise ValueError(f"Direct repair is only implemented for Claude/Gemini, got {judge_model}")


def _build_df_and_scenarios(
    task: TaskConfig,
    run_id: str,
    mode: str,
    judge_model: str,
) -> tuple[pd.DataFrame, list]:
    root = results_base() / task.slug / run_id / mode
    raw = pd.read_csv(root / "outputs.csv")
    if mode == "augmentation":
        raw = _ensure_augmentation_columns(raw)
    df = _prep_df(raw)
    if mode == "augmentation":
        scenarios = _build_scenarios_augmentation(df, task.pairwise_task_context, 1, run_id=None)
    else:
        scenarios = _build_scenarios_automation(df, task.pairwise_task_context, 1)
    return df, _filter_scenarios_for_judge(scenarios, judge_model, exclude_self_family=True)


def _run_direct_judge(
    task: TaskConfig,
    run_id: str,
    mode: str,
    judge_model: str,
    judge_label: str,
    *,
    workers: int,
    max_tokens: int,
    attempts: int | None = None,
    timeout: int | None = None,
) -> pd.DataFrame:
    _, scenarios = _build_df_and_scenarios(task, run_id, mode, judge_model)
    system_prompt = _build_judge_instruction(task)
    call_attempts = attempts or int(os.environ.get("CENTAUR_DIRECT_JUDGE_ATTEMPTS", "6"))
    call_timeout = timeout or int(os.environ.get("CENTAUR_DIRECT_JUDGE_TIMEOUT", "240"))

    def one_row(idx: int, scenario: Any) -> tuple[int, dict[str, Any]]:
        data = _scenario_data(scenario)
        raw = _call_direct_judge(
            judge_model,
            system_prompt=system_prompt,
            user_prompt=_pairwise_user_prompt(
                str(data["task_text"]),
                str(data["option_1"]),
                str(data["option_2"]),
            ),
            max_tokens=max_tokens,
            attempts=call_attempts,
            timeout=call_timeout,
        )
        row = {
            "left_idx": data["left_idx"],
            "right_idx": data["right_idx"],
            "replicate_id": data["replicate_id"],
            "judgment": raw,
        }
        return idx, row

    rows: list[dict[str, Any] | None] = [None] * len(scenarios)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(one_row, i, scenario): i for i, scenario in enumerate(scenarios)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                out_idx, row = fut.result()
                rows[out_idx] = row
            except Exception as exc:  # noqa: BLE001
                data = _scenario_data(scenarios[idx])
                rows[idx] = {
                    "left_idx": data["left_idx"],
                    "right_idx": data["right_idx"],
                    "replicate_id": data["replicate_id"],
                    "judgment": f"PROVIDER_ERROR: {exc}",
                }
                print(f"  row {idx} failed: {exc}", flush=True)
    pairwise = pd.DataFrame([r for r in rows if r is not None])
    pairwise = _parse_pairwise_judgments(pairwise)
    pairwise["judge_model"] = judge_model
    pairwise["judge_label"] = judge_label
    return pairwise


def _is_claude_judge(judge_model: str) -> bool:
    low = judge_model.lower()
    return "claude" in low or "anthropic" in low


def _repair_claude_via_edsl(
    task: TaskConfig,
    run_id: str,
    mode: str,
    judge_model: str,
) -> None:
    """Last-resort Claude repair through EDSL direct Anthropic routing."""
    from centaur_benchmark.judge_pairwise import (
        judge_augmentation_panel,
        judge_automation_panel,
    )

    os.environ.setdefault("CENTAUR_EDSL_MODE", "mixed")
    os.environ.setdefault("CENTAUR_DIRECT_ENABLE_VENDOR_ALIASES", "1")
    os.environ.setdefault(
        "CENTAUR_MODEL_ALIAS_ANTHROPIC_CLAUDE_OPUS_4_8", "claude-opus-4-20250514"
    )
    os.environ.setdefault("EDSL_API_TIMEOUT", "600")
    os.environ.setdefault("REMOTE_PROXY_TIMEOUT", "600")
    os.environ.setdefault("EDSL_MAX_ATTEMPTS", "10")

    root = results_base() / task.slug / run_id
    eval_models = {judge_model: (task.evaluator_models or {}).get(judge_model, judge_model)}
    print(f"  EDSL fallback for {judge_model} ({mode})", flush=True)
    if mode == "augmentation":
        judge_augmentation_panel(task, root, eval_models=eval_models, n_evals=1)
    else:
        judge_automation_panel(task, root, eval_models=eval_models, n_evals=1)


def _repair_judge_cell(
    task: TaskConfig,
    run_id: str,
    mode: str,
    judge_model: str,
    judge_label: str,
    *,
    workers: int,
    max_tokens: int,
    edsl_fallback: bool,
) -> tuple[pd.DataFrame, dict[str, object]]:
    print(f"  repairing {judge_label} via direct provider (workers={workers})", flush=True)
    pairwise = _run_direct_judge(
        task, run_id, mode, judge_model, judge_label, workers=workers, max_tokens=max_tokens
    )
    validation = validate_judge_batch(pairwise)
    if validation["batch_ok"]:
        return pairwise, validation

    if _is_claude_judge(judge_model):
        print(
            f"  {judge_label}: direct pass_rate={validation['row_pass_rate']:.3f}; "
            "retrying with workers=1 timeout=600 attempts=10",
            flush=True,
        )
        pairwise = _run_direct_judge(
            task,
            run_id,
            mode,
            judge_model,
            judge_label,
            workers=1,
            max_tokens=max_tokens,
            attempts=10,
            timeout=600,
        )
        validation = validate_judge_batch(pairwise)
        if validation["batch_ok"]:
            return pairwise, validation

        if edsl_fallback:
            _repair_claude_via_edsl(task, run_id, mode, judge_model)
            out_dir = results_base() / task.slug / run_id / mode
            path = out_dir / f"pairwise_judgments_{_safe_file_slug(judge_label)}.csv"
            pairwise = pd.read_csv(path)
            validation = validate_judge_batch(pairwise)

    return pairwise, validation


def _normalize_existing_pairwise(path: Path, judge_model: str, judge_label: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    base_cols = [c for c in df.columns if c not in PARSED_COLUMNS]
    df = _parse_pairwise_judgments(df[base_cols].copy())
    df["judge_model"] = judge_model
    df["judge_label"] = judge_label
    df.to_csv(path, index=False)
    return df


def rebuild_aggregate(task: TaskConfig, run_id: str, mode: str) -> dict[str, Any]:
    out_dir = results_base() / task.slug / run_id / mode
    if mode == "augmentation":
        raw = _ensure_augmentation_columns(pd.read_csv(out_dir / "outputs.csv"))
    else:
        raw = pd.read_csv(out_dir / "outputs.csv")
    df = _prep_df(raw)

    validation_report: dict[str, Any] = {"judges": {}, "excluded_from_aggregate": []}
    all_pairwise: list[pd.DataFrame] = []
    all_scored: list[pd.DataFrame] = []

    for judge_model, judge_label in (task.evaluator_models or {}).items():
        path = out_dir / f"pairwise_judgments_{_safe_file_slug(judge_label)}.csv"
        if not path.is_file():
            validation_report["judges"][judge_label] = {
                "judge_model": judge_model,
                "batch_ok": False,
                "exclude_reason": "missing_pairwise_csv",
            }
            validation_report["excluded_from_aggregate"].append(
                {"judge_label": judge_label, "judge_model": judge_model, "reason": "missing_pairwise_csv"}
            )
            continue
        pairwise = _normalize_existing_pairwise(path, judge_model, judge_label)
        validation = validate_judge_batch(pairwise)
        validation_report["judges"][judge_label] = {
            "judge_model": judge_model,
            **{k: v for k, v in validation.items() if k != "issues_by_row"},
            "failed_rows": [r for r in validation["issues_by_row"] if not r["ok"]][:20],
        }
        scored = _score_from_pairwise(df, pairwise)
        scored["judge_model"] = judge_model
        scored["judge_label"] = judge_label
        scored.to_csv(out_dir / f"pairwise_ranked_{_safe_file_slug(judge_label)}.csv", index=False)
        if validation["batch_ok"]:
            all_pairwise.append(pairwise)
            all_scored.append(scored)
        else:
            validation_report["excluded_from_aggregate"].append(
                {
                    "judge_label": judge_label,
                    "judge_model": judge_model,
                    "reason": validation["exclude_reason"],
                }
            )

    if not all_pairwise:
        raise RuntimeError(f"No valid judges for {run_id} {task.slug}/{mode}")

    pairwise_all = pd.concat(all_pairwise, ignore_index=True)
    scored_all = pd.concat(all_scored, ignore_index=True)
    leaderboard_by_judge = _leaderboard_from_panel_scored(scored_all)
    aggregate = _aggregate_panel_leaderboard(leaderboard_by_judge)
    pairwise_all.to_csv(out_dir / "pairwise_judgments_by_judge.csv", index=False)
    scored_all.to_csv(out_dir / "pairwise_ranked_by_judge.csv", index=False)
    leaderboard_by_judge.to_csv(out_dir / "leaderboard_by_judge.csv", index=False)
    aggregate.to_csv(out_dir / "leaderboard_aggregate.csv", index=False)
    _write_panel_matrices(out_dir, leaderboard_by_judge, aggregate)
    _write_score_summaries(out_dir, df, pairwise_all)
    validation_report["aggregate_judges"] = sorted(
        {str(frame["judge_label"].iloc[0]) for frame in all_pairwise}
    )
    (out_dir / "judge_validation.json").write_text(
        json.dumps(validation_report, indent=2, default=str),
        encoding="utf-8",
    )
    return validation_report


def _needs_repair(task: TaskConfig, run_id: str, mode: str, judge_label: str, threshold: float) -> bool:
    path = results_base() / task.slug / run_id / mode / "judge_validation.json"
    if not path.is_file():
        return True
    payload = json.loads(path.read_text(encoding="utf-8"))
    info = (payload.get("judges") or {}).get(judge_label) or {}
    return (not bool(info.get("batch_ok"))) or float(info.get("row_pass_rate") or 0.0) < threshold


def main() -> None:
    _load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", action="append", required=True)
    parser.add_argument("--tasks", default=None, help="Comma-separated task slugs; default all")
    parser.add_argument("--modes", default="augmentation,automation")
    parser.add_argument(
        "--judges",
        default="Claude-Opus-4.8,Gemini-3.1-Pro",
        help="Comma-separated judge labels to repair when below threshold",
    )
    parser.add_argument("--threshold", type=float, default=0.9)
    parser.add_argument("--workers", type=int, default=int(os.environ.get("CENTAUR_DIRECT_JUDGE_WORKERS", "2")))
    parser.add_argument("--max-tokens", type=int, default=int(os.environ.get("CENTAUR_DIRECT_JUDGE_MAX_TOKENS", "8192")))
    parser.add_argument("--force", action="store_true", help="Rerun requested judges even if currently healthy")
    parser.add_argument("--rebuild-only", action="store_true", help="Only rebuild aggregates from existing CSVs")
    parser.add_argument(
        "--edsl-fallback",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If direct Claude repair fails, retry failed cells via EDSL (one judge at a time)",
    )
    args = parser.parse_args()

    task_slugs = (
        [x.strip() for x in args.tasks.split(",") if x.strip()]
        if args.tasks
        else sorted(p.stem for p in default_tasks_dir().glob("*.yaml"))
    )
    modes = [x.strip() for x in args.modes.split(",") if x.strip()]
    wanted_labels = {x.strip() for x in args.judges.split(",") if x.strip()}

    for run_id in args.run_id:
        for task_slug in task_slugs:
            task = load_task(default_tasks_dir() / f"{task_slug}.yaml")
            label_to_model = {label: model for model, label in (task.evaluator_models or {}).items()}
            for mode in modes:
                print(f"== {run_id} {task_slug}/{mode} ==", flush=True)
                for judge_label in wanted_labels:
                    judge_model = label_to_model.get(judge_label)
                    if not judge_model:
                        continue
                    if args.rebuild_only:
                        continue
                    if not args.force and not _needs_repair(task, run_id, mode, judge_label, args.threshold):
                        print(f"  {judge_label}: already healthy, skip", flush=True)
                        continue
                    pairwise, validation = _repair_judge_cell(
                        task,
                        run_id,
                        mode,
                        judge_model,
                        judge_label,
                        workers=args.workers,
                        max_tokens=args.max_tokens,
                        edsl_fallback=args.edsl_fallback,
                    )
                    out_dir = results_base() / task.slug / run_id / mode
                    pairwise.to_csv(
                        out_dir / f"pairwise_judgments_{_safe_file_slug(judge_label)}.csv",
                        index=False,
                    )
                    print(
                        f"  {judge_label}: pass_rate={validation['row_pass_rate']:.3f} "
                        f"batch_ok={validation['batch_ok']}",
                        flush=True,
                    )
                report = rebuild_aggregate(task, run_id, mode)
                print(f"  aggregate_judges={report.get('aggregate_judges')}", flush=True)


if __name__ == "__main__":
    main()
