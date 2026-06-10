"""EDSL runners for augmentation (scaffold + worker) and automation (model solves)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from centaur_benchmark.config import TaskConfig
from centaur_benchmark.edsl_runtime import edsl_run_kwargs
from centaur_benchmark.io import write_json

def _safe_slug(s: str) -> str:
    return (
        s.replace(" ", "_")
        .replace("/", "_")
        .replace(":", "_")
        .replace("\\", "_")
        .replace("|", "_")
    )


def _generate_scaffold(
    task: TaskConfig,
    task_prompt: str,
    assistant_model: str,
) -> str:
    from edsl import Agent, Model, Scenario, Survey, QuestionFreeText

    assistant_agent = Agent(instruction=task.scaffold_prompt_template)
    q = QuestionFreeText("scaffold", "{{ scenario.task_prompt }}")
    survey = Survey([q])
    scenario = Scenario({"task_prompt": task_prompt})
    kwargs: dict[str, Any] = {}
    if task.scaffold_model_max_tokens is not None:
        kwargs["max_tokens"] = int(task.scaffold_model_max_tokens)
    model = Model(assistant_model, **kwargs)
    print(f"Generating scaffold from {assistant_model}...")
    results = survey.by(scenario).by(assistant_agent).by(model).run(
        **edsl_run_kwargs(
            description=f"centaur-scaffold-{assistant_model}",
            visibility=task.remote_inference_visibility,
        ),
    )
    scaffold_text = results.select("scaffold").to_list()[0] or ""
    print(f"Scaffold OK ({len(scaffold_text or '')} chars)")
    return scaffold_text


def _run_worker_batch(
    task: TaskConfig,
    *,
    worker_model: str,
    condition: str,
    full_prompts: list[str],
    remote_description: str,
    remote_visibility: str,
) -> pd.DataFrame:
    from edsl import Agent, Model, Scenario, ScenarioList, Survey, QuestionFreeText

    scenarios = ScenarioList(
        [
            Scenario(
                {
                    "task_prompt": fp,
                    "condition": condition,
                    "replicate_id": i,
                }
            )
            for i, fp in enumerate(full_prompts)
        ]
    )
    q = QuestionFreeText("output", "{{ scenario.task_prompt }}")
    survey = Survey([q])
    worker = Agent(instruction=task.worker_instruction)
    print(f"Running worker={worker_model} condition={condition} n={len(full_prompts)}...")
    results = (
        survey.by(scenarios)
        .by(worker)
        .by(Model(worker_model))
        .run(
            **edsl_run_kwargs(
                description=remote_description,
                visibility=remote_visibility,
                progress_bar=True,
                verbose=True,
                n=1,
            ),
        )
    )
    df = results.select("scenario.replicate_id", "answer.output", "scenario.condition").to_pandas()
    df.rename(
        columns={
            "scenario.replicate_id": "replicate_id",
            "answer.output": "output",
            "scenario.condition": "condition",
        },
        inplace=True,
    )
    return df


def run_augmentation(
    task: TaskConfig,
    run_root: Path,
    *,
    worker_model: str | None = None,
    assistants: dict[str, str] | None = None,
    replicates: int | None = None,
) -> Path:
    """Plain baseline + one scaffold per assistant model. Writes augmentation/outputs.csv."""
    worker_model = worker_model or task.default_worker
    assistants = assistants or task.assistants
    n_rep = replicates if replicates is not None else task.replicates
    if not assistants:
        raise ValueError("No assistants configured for this task.")

    out_csv = run_root / "augmentation" / "outputs.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    scaffolds_dir = run_root / "augmentation" / "scaffolds"
    scaffolds_dir.mkdir(parents=True, exist_ok=True)
    scaffolds_records: list[dict[str, Any]] = []

    all_parts: list[pd.DataFrame] = []

    plain_prompts = [task.task_prompt] * n_rep
    plain_df = _run_worker_batch(
        task,
        worker_model=worker_model,
        condition="plain",
        full_prompts=plain_prompts,
        remote_description=f"{task.slug}-{worker_model}-plain",
        remote_visibility=task.remote_inference_visibility,
    )
    plain_df["assistant_model"] = "plain"
    plain_df["worker_model"] = worker_model
    plain_df["model_id"] = "plain"
    plain_df["model_label"] = "plain"
    plain_df["scaffold_path"] = ""
    plain_df["scaffold_sha256"] = ""
    plain_df["scaffold_text"] = ""
    all_parts.append(plain_df)

    for model_id, model_label in assistants.items():
        scaffold = _generate_scaffold(task, task.task_prompt, model_id)
        scaffold_path = scaffolds_dir / f"{_safe_slug(model_label)}.md"
        scaffold_path.write_text(scaffold, encoding="utf-8")
        scaffold_sha256 = hashlib.sha256(scaffold.encode("utf-8")).hexdigest()
        scaffolds_records.append(
            {
                "model_id": model_id,
                "model_label": model_label,
                "scaffold_path": str(scaffold_path),
                "scaffold_sha256": scaffold_sha256,
                "n_chars": len(scaffold),
            }
        )
        full_prompts = [f"{scaffold}\n\n{task.task_prompt}"] * n_rep
        cond = f"scaffold_{_safe_slug(model_label)}"
        sdf = _run_worker_batch(
            task,
            worker_model=worker_model,
            condition=cond,
            full_prompts=full_prompts,
            remote_description=f"{task.slug}-{worker_model}-{cond}",
            remote_visibility=task.remote_inference_visibility,
        )
        sdf["assistant_model"] = model_label
        sdf["worker_model"] = worker_model
        sdf["model_id"] = model_id
        sdf["model_label"] = model_label
        sdf["scaffold_path"] = str(scaffold_path)
        sdf["scaffold_sha256"] = scaffold_sha256
        sdf["scaffold_text"] = scaffold
        all_parts.append(sdf)

    if scaffolds_records:
        pd.DataFrame(scaffolds_records).to_csv(run_root / "augmentation" / "scaffolds.csv", index=False)

    final_df = pd.concat(all_parts, ignore_index=True)
    final_df.to_csv(out_csv, index=False)
    print(f"Wrote {out_csv} ({len(final_df)} rows)")
    return out_csv


def _run_automation_single_model(
    task: TaskConfig,
    *,
    model_id: str,
    model_label: str,
    prompts: list[str],
    remote_description: str,
    remote_visibility: str,
) -> pd.DataFrame:
    from edsl import Agent, Model, Scenario, ScenarioList, Survey, QuestionFreeText

    condition = f"automation_{model_label.replace(' ', '_')}"
    scenarios = ScenarioList(
        [
            Scenario({"task_prompt": fp, "condition": condition, "replicate_id": i})
            for i, fp in enumerate(prompts)
        ]
    )
    q = QuestionFreeText("output", "{{ scenario.task_prompt }}")
    survey = Survey([q])
    auto_instr = task.automation_worker_instruction or (
        "Complete the task clearly and professionally. Return only the final deliverable."
    )
    worker = Agent(instruction=auto_instr)
    mkwargs: dict[str, Any] = {}
    if task.automation_model_max_tokens is not None:
        mkwargs["max_tokens"] = task.automation_model_max_tokens
    print(f"Running automation model={model_id} n={len(prompts)}...")
    results = (
        survey.by(scenarios)
        .by(worker)
        .by(Model(model_id, **mkwargs))
        .run(
            **edsl_run_kwargs(
                description=remote_description,
                visibility=remote_visibility,
                n=1,
            ),
        )
    )
    df = results.select("scenario.replicate_id", "answer.output", "scenario.condition").to_pandas()
    df.rename(
        columns={
            "scenario.replicate_id": "replicate_id",
            "answer.output": "output",
            "scenario.condition": "condition",
        },
        inplace=True,
    )
    df["model_id"] = model_id
    df["model_label"] = model_label
    return df


def run_automation(
    task: TaskConfig,
    run_root: Path,
    *,
    models: dict[str, str] | None = None,
    replicates: int | None = None,
) -> Path | None:
    """Each model solves the task directly. Writes automation/outputs.csv."""
    models = models or task.automation_models
    if not models:
        print("No automation_models in task config; skipping automation.")
        return None
    n_rep = replicates if replicates is not None else task.replicates
    out_csv = run_root / "automation" / "outputs.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    parts: list[pd.DataFrame] = []
    for model_id, model_label in models.items():
        prompts = [task.task_prompt] * n_rep
        df = _run_automation_single_model(
            task,
            model_id=model_id,
            model_label=model_label,
            prompts=prompts,
            remote_description=f"{task.slug}-automation-{model_id}",
            remote_visibility=task.remote_inference_visibility,
        )
        parts.append(df)
    final_df = pd.concat(parts, ignore_index=True)
    final_df.to_csv(out_csv, index=False)
    print(f"Wrote {out_csv} ({len(final_df)} rows)")
    return out_csv


def patch_augmentation_models(
    task: TaskConfig,
    run_root: Path,
    model_ids: list[str],
    *,
    worker_model: str | None = None,
    replicates: int | None = None,
) -> Path:
    """Regenerate scaffolds + worker outputs for specific assistant models and merge into outputs.csv."""
    worker_model = worker_model or task.default_worker
    n_rep = replicates if replicates is not None else task.replicates
    out_csv = run_root / "augmentation" / "outputs.csv"
    if not out_csv.exists():
        raise FileNotFoundError(f"Missing {out_csv}")
    existing = pd.read_csv(out_csv)
    scaffolds_dir = run_root / "augmentation" / "scaffolds"
    scaffolds_dir.mkdir(parents=True, exist_ok=True)
    scaffolds_records: list[dict[str, Any]] = []
    if (run_root / "augmentation" / "scaffolds.csv").exists():
        scaffolds_records = pd.read_csv(run_root / "augmentation" / "scaffolds.csv").to_dict("records")

    new_parts: list[pd.DataFrame] = []
    for model_id in model_ids:
        model_label = task.assistants.get(model_id)
        if not model_label:
            raise ValueError(f"Unknown assistant model_id: {model_id}")
        scaffold = _generate_scaffold(task, task.task_prompt, model_id)
        scaffold_path = scaffolds_dir / f"{_safe_slug(model_label)}.md"
        scaffold_path.write_text(scaffold, encoding="utf-8")
        scaffold_sha256 = hashlib.sha256(scaffold.encode("utf-8")).hexdigest()
        rec = {
            "model_id": model_id,
            "model_label": model_label,
            "scaffold_path": str(scaffold_path),
            "scaffold_sha256": scaffold_sha256,
            "n_chars": len(scaffold),
        }
        scaffolds_records = [r for r in scaffolds_records if r.get("model_id") != model_id]
        scaffolds_records.append(rec)

        full_prompts = [f"{scaffold}\n\n{task.task_prompt}"] * n_rep
        cond = f"scaffold_{_safe_slug(model_label)}"
        sdf = _run_worker_batch(
            task,
            worker_model=worker_model,
            condition=cond,
            full_prompts=full_prompts,
            remote_description=f"{task.slug}-retry-{worker_model}-{cond}",
            remote_visibility=task.remote_inference_visibility,
        )
        sdf["assistant_model"] = model_label
        sdf["worker_model"] = worker_model
        sdf["model_id"] = model_id
        sdf["model_label"] = model_label
        sdf["scaffold_path"] = str(scaffold_path)
        sdf["scaffold_sha256"] = scaffold_sha256
        sdf["scaffold_text"] = scaffold
        new_parts.append(sdf)

    patched = existing[~existing["model_id"].isin(model_ids)].copy()
    if new_parts:
        patched = pd.concat([patched, *new_parts], ignore_index=True)
    patched.to_csv(out_csv, index=False)
    if scaffolds_records:
        pd.DataFrame(scaffolds_records).to_csv(run_root / "augmentation" / "scaffolds.csv", index=False)
    print(f"Patched augmentation models {model_ids} -> {out_csv}")
    return out_csv


def patch_automation_models(
    task: TaskConfig,
    run_root: Path,
    model_ids: list[str],
    *,
    replicates: int | None = None,
) -> Path:
    """Regenerate automation outputs for specific models and merge into outputs.csv."""
    if not task.automation_models:
        raise ValueError("No automation_models configured")
    n_rep = replicates if replicates is not None else task.replicates
    out_csv = run_root / "automation" / "outputs.csv"
    if not out_csv.exists():
        raise FileNotFoundError(f"Missing {out_csv}")
    existing = pd.read_csv(out_csv)
    new_parts: list[pd.DataFrame] = []
    for model_id in model_ids:
        model_label = task.automation_models.get(model_id)
        if not model_label:
            raise ValueError(f"Unknown automation model_id: {model_id}")
        df = _run_automation_single_model(
            task,
            model_id=model_id,
            model_label=model_label,
            prompts=[task.task_prompt] * n_rep,
            remote_description=f"{task.slug}-automation-retry-{model_id}",
            remote_visibility=task.remote_inference_visibility,
        )
        new_parts.append(df)

    patched = existing[~existing["model_id"].isin(model_ids)].copy()
    if new_parts:
        patched = pd.concat([patched, *new_parts], ignore_index=True)
    patched.to_csv(out_csv, index=False)
    print(f"Patched automation models {model_ids} -> {out_csv}")
    return out_csv


def write_run_config(
    run_root: Path,
    task: TaskConfig,
    *,
    modes: list[str],
    worker_model: str | None,
    replicates: int | None,
    assistants_used: dict[str, str] | None,
    automation_used: dict[str, str] | None,
) -> None:
    from centaur_benchmark import __version__

    cfg = {
        "package_version": __version__,
        "task_slug": task.slug,
        "task_title": task.title,
        "modes": modes,
        "worker_model": worker_model,
        "replicates": replicates if replicates is not None else task.replicates,
        "assistants": assistants_used or task.assistants,
        "automation_models": automation_used or task.automation_models,
        "evaluator_models": task.evaluator_models,
        "default_evaluator": task.default_evaluator,
        "pairwise_n_evals": task.pairwise_n_evals,
        "pairwise_n_outer_runs": task.pairwise_n_outer_runs,
    }
    write_json(run_root / "config.json", cfg)
