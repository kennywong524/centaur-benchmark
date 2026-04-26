"""Pairwise LLM-as-judge over outputs (augmentation or automation)."""

from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd

from centaur_benchmark.config import TaskConfig


def _ensure_augmentation_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "model_id" not in df.columns:
        df["model_id"] = df.get("assistant_model", "unknown")
    if "model_label" not in df.columns:
        df["model_label"] = df["model_id"]
    return df


def _prep_df(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy().reset_index(drop=True)
    d = d[d["output"].notna()].reset_index(drop=True)
    return d


def _build_scenarios_augmentation(
    df: pd.DataFrame,
    task_text: str,
    n_evals: int,
    *,
    run_id: int | None = None,
) -> list:
    from edsl import Scenario

    scenarios = []
    item_pairs = list(itertools.combinations(df.index.tolist(), 2))
    for i, j in item_pairs:
        row_i = df.loc[i]
        row_j = df.loc[j]
        if pd.isna(row_i.get("output")) or pd.isna(row_j.get("output")):
            continue
        for replicate_id in range(n_evals):
            d = {
                "left_idx": int(i),
                "right_idx": int(j),
                "replicate_id": int(replicate_id),
                "task_text": str(task_text),
                "option_1": str(row_i["output"]),
                "option_2": str(row_j["output"]),
                "left_worker_model": str(row_i.get("worker_model", "unknown")),
                "right_worker_model": str(row_j.get("worker_model", "unknown")),
                "left_assistant_model": str(row_i.get("assistant_model", "none")),
                "right_assistant_model": str(row_j.get("assistant_model", "none")),
                "left_condition": str(row_i.get("condition", "unknown")),
                "right_condition": str(row_j.get("condition", "unknown")),
                "left_model_id": str(row_i.get("model_id", "unknown")),
                "right_model_id": str(row_j.get("model_id", "unknown")),
                "left_model_label": str(row_i.get("model_label", "unknown")),
                "right_model_label": str(row_j.get("model_label", "unknown")),
            }
            if run_id is not None:
                d["run_id"] = int(run_id)
            scenarios.append(Scenario(d))
    return scenarios


def _build_scenarios_automation(df: pd.DataFrame, task_text: str, n_evals: int) -> list:
    from edsl import Scenario

    scenarios = []
    item_pairs = list(itertools.combinations(df.index.tolist(), 2))
    for i, j in item_pairs:
        row_i = df.loc[i]
        row_j = df.loc[j]
        if pd.isna(row_i.get("output")) or pd.isna(row_j.get("output")):
            continue
        for replicate_id in range(n_evals):
            scenarios.append(
                Scenario(
                    {
                        "left_idx": int(i),
                        "right_idx": int(j),
                        "replicate_id": int(replicate_id),
                        "task_text": str(task_text),
                        "option_1": str(row_i["output"]),
                        "option_2": str(row_j["output"]),
                        "left_model_id": str(row_i.get("model_id", "unknown")),
                        "right_model_id": str(row_j.get("model_id", "unknown")),
                        "left_model_label": str(row_i.get("model_label", "unknown")),
                        "right_model_label": str(row_j.get("model_label", "unknown")),
                        "left_condition": str(row_i.get("condition", "unknown")),
                        "right_condition": str(row_j.get("condition", "unknown")),
                        "left_replicate_id": int(row_i["replicate_id"])
                        if pd.notna(row_i.get("replicate_id"))
                        else None,
                        "right_replicate_id": int(row_j["replicate_id"])
                        if pd.notna(row_j.get("replicate_id"))
                        else None,
                    }
                )
            )
    return scenarios


def _run_pairwise_survey(
    scenarios_list: list,
    eval_prompt: str,
    eval_model: str,
    *,
    include_run_id: bool,
) -> pd.DataFrame:
    from edsl import Agent, Model, ScenarioList, Survey, QuestionMultipleChoice

    if not scenarios_list:
        return pd.DataFrame()
    scenarios = ScenarioList(scenarios_list)
    q = QuestionMultipleChoice(
        question_name="winner",
        question_text="""
Original request:
{{ task_text }}

--------------------------------------------------
OPTION 1
{{ option_1 }}

--------------------------------------------------
OPTION 2
{{ option_2 }}

Which option is better overall?
""",
        question_options=["option_1", "option_2"],
        include_comment=False,
    )
    survey = Survey([q])
    agent = Agent(instruction=eval_prompt)
    evaluator = Model(eval_model)
    results = (
        survey.by(scenarios)
        .by(agent)
        .by(evaluator)
        .run(
            n=1,
            progress_bar=False,
            verbose=False,
            stop_on_exception=False,
            check_api_keys=False,
            print_exceptions=True,
        )
    )
    if include_run_id:
        pairwise_df = results.select(
            "run_id",
            "left_idx",
            "right_idx",
            "replicate_id",
            "winner",
        ).to_pandas()
    else:
        pairwise_df = results.select(
            "left_idx",
            "right_idx",
            "replicate_id",
            "winner",
        ).to_pandas()
    pairwise_df.columns = [c.split(".")[-1] for c in pairwise_df.columns]
    return pairwise_df


def _aggregate_one_pass(
    df: pd.DataFrame,
    pairwise_df: pd.DataFrame,
    n_evals: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """df must be reset-indexed contiguous 0..n-1 matching left_idx/right_idx."""
    records = []
    for replicate_id in range(n_evals):
        sub = pairwise_df[pairwise_df["replicate_id"] == replicate_id].copy()
        wins = {i: 0 for i in df.index}
        games = {i: 0 for i in df.index}
        for _, row in sub.iterrows():
            left = int(row["left_idx"])
            right = int(row["right_idx"])
            winner = str(row["winner"]).strip()
            games[left] += 1
            games[right] += 1
            if winner == "option_1":
                wins[left] += 1
            elif winner == "option_2":
                wins[right] += 1
        rep_df = pd.DataFrame(
            {
                "item_id": list(df.index),
                "replicate_id": replicate_id,
                "wins": [wins[i] for i in df.index],
                "games": [games[i] for i in df.index],
            }
        )
        rep_df["win_rate"] = rep_df["wins"] / rep_df["games"].replace(0, np.nan)
        rep_df["rank"] = rep_df["wins"].rank(ascending=False, method="average")
        records.append(rep_df)
    long_rank_df = pd.concat(records, ignore_index=True)
    summary = (
        long_rank_df.groupby("item_id")
        .agg(
            avg_rank=("rank", "mean"),
            std_rank=("rank", "std"),
            avg_win_rate=("win_rate", "mean"),
            std_win_rate=("win_rate", "std"),
            total_wins=("wins", "sum"),
            total_games=("games", "sum"),
        )
        .reset_index()
    )
    scored = df.copy()
    scored["item_id"] = scored.index
    scored = scored.merge(summary, on="item_id", how="left")
    scored = scored.sort_values(["avg_rank", "avg_win_rate"], ascending=[True, False])
    return scored, long_rank_df


def _aggregate_multirun(df: pd.DataFrame, all_scored_runs: pd.DataFrame) -> pd.DataFrame:
    base = df.copy()
    base["item_id"] = base.index
    cross = (
        all_scored_runs.groupby("item_id")
        .agg(
            avg_rank=("run_avg_rank", "mean"),
            sd_rank=("run_avg_rank", "std"),
            avg_win_rate=("run_avg_win_rate", "mean"),
            sd_win_rate=("run_avg_win_rate", "std"),
            n_runs=("run_id", "nunique"),
        )
        .reset_index()
    )
    scored = base.merge(cross, on="item_id", how="left")
    return scored.sort_values(["avg_rank", "avg_win_rate"], ascending=[True, False])


def _leaderboard_from_scored(scored: pd.DataFrame) -> pd.DataFrame:
    return (
        scored.groupby(["model_id", "model_label", "condition"])
        .agg(
            avg_rank=("avg_rank", "mean"),
            avg_win_rate=("avg_win_rate", "mean"),
            std_rank=("avg_rank", "std"),
            std_win_rate=("avg_win_rate", "std"),
            total_wins=("total_wins", "mean"),
            total_games=("total_games", "mean"),
        )
        .sort_values(by=["avg_rank", "avg_win_rate"], ascending=[True, False])
        .reset_index()
    )


def judge_augmentation(
    task: TaskConfig,
    run_root: Path,
    *,
    eval_model: str | None = None,
    n_evals: int | None = None,
    n_outer_runs: int | None = None,
) -> tuple[Path, Path, Path]:
    """Read augmentation/outputs.csv; write pairwise_judgments, pairwise_ranked, leaderboard."""
    eval_model = eval_model or task.default_evaluator
    n_evals = n_evals if n_evals is not None else task.pairwise_n_evals
    n_outer = n_outer_runs if n_outer_runs is not None else task.pairwise_n_outer_runs

    inp = run_root / "augmentation" / "outputs.csv"
    if not inp.exists():
        raise FileNotFoundError(f"Missing {inp}; run augmentation first.")
    raw = pd.read_csv(inp)
    raw = _ensure_augmentation_columns(raw)
    df = _prep_df(raw)

    out_dir = run_root / "augmentation"
    judgments_path = out_dir / "pairwise_judgments.csv"
    ranked_path = out_dir / "pairwise_ranked.csv"
    board_path = out_dir / "leaderboard.csv"
    task_text = task.pairwise_task_context

    if n_outer <= 1:
        scenarios = _build_scenarios_augmentation(df, task_text, n_evals, run_id=None)
        pairwise_df = _run_pairwise_survey(scenarios, task.pairwise_eval_prompt, eval_model, include_run_id=False)
        scored, long_df = _aggregate_one_pass(df, pairwise_df, n_evals)
        pairwise_df.to_csv(judgments_path, index=False)
        long_df.to_csv(out_dir / "pairwise_long_rank.csv", index=False)
        scored.to_csv(ranked_path, index=False)
        _leaderboard_from_scored(scored).to_csv(board_path, index=False)
        return judgments_path, ranked_path, board_path

    all_pairwise: list[pd.DataFrame] = []
    all_scored_runs: list[pd.DataFrame] = []
    all_long: list[pd.DataFrame] = []

    for run_id in range(n_outer):
        scenarios = _build_scenarios_augmentation(df, task_text, n_evals, run_id=run_id)
        pw = _run_pairwise_survey(scenarios, task.pairwise_eval_prompt, eval_model, include_run_id=True)
        scored_run, long_rank = _aggregate_one_pass(df, pw, n_evals)
        scored_run = scored_run.rename(
            columns={
                "avg_rank": "run_avg_rank",
                "std_rank": "run_std_rank",
                "avg_win_rate": "run_avg_win_rate",
                "std_win_rate": "run_std_win_rate",
                "total_wins": "run_total_wins",
                "total_games": "run_total_games",
            }
        )
        scored_run["run_id"] = run_id
        long_rank["run_id"] = run_id
        all_pairwise.append(pw)
        all_long.append(long_rank)
        all_scored_runs.append(scored_run)

    all_pairwise_df = pd.concat(all_pairwise, ignore_index=True)
    all_scored_runs_df = pd.concat(all_scored_runs, ignore_index=True)
    all_pairwise_df.to_csv(judgments_path, index=False)
    pd.concat(all_long, ignore_index=True).to_csv(out_dir / "pairwise_long_rank.csv", index=False)
    scored_final = _aggregate_multirun(df, all_scored_runs_df)
    scored_final.to_csv(ranked_path, index=False)
    all_scored_runs_df.to_csv(out_dir / "pairwise_run_level.csv", index=False)
    lb = (
        all_scored_runs_df.groupby(["model_id", "model_label", "condition"])
        .agg(
            avg_rank=("run_avg_rank", "mean"),
            sd_rank=("run_avg_rank", "std"),
            avg_win_rate=("run_avg_win_rate", "mean"),
            sd_win_rate=("run_avg_win_rate", "std"),
            n_runs=("run_id", "nunique"),
        )
        .reset_index()
        .sort_values(by=["avg_rank", "avg_win_rate"], ascending=[True, False])
    )
    lb.to_csv(board_path, index=False)
    return judgments_path, ranked_path, board_path


def judge_automation(
    task: TaskConfig,
    run_root: Path,
    *,
    eval_model: str | None = None,
    n_evals: int | None = None,
) -> tuple[Path, Path, Path]:
    eval_model = eval_model or task.default_evaluator
    n_evals = n_evals if n_evals is not None else task.pairwise_n_evals
    inp = run_root / "automation" / "outputs.csv"
    if not inp.exists():
        raise FileNotFoundError(f"Missing {inp}; run automation first.")
    df = _prep_df(pd.read_csv(inp))
    out_dir = run_root / "automation"
    task_text = task.pairwise_task_context
    scenarios = _build_scenarios_automation(df, task_text, n_evals)
    pairwise_df = _run_pairwise_survey(scenarios, task.pairwise_eval_prompt, eval_model, include_run_id=False)
    scored, long_df = _aggregate_one_pass(df, pairwise_df, n_evals)
    judgments_path = out_dir / "pairwise_judgments.csv"
    ranked_path = out_dir / "pairwise_ranked.csv"
    board_path = out_dir / "leaderboard.csv"
    pairwise_df.to_csv(judgments_path, index=False)
    long_df.to_csv(out_dir / "pairwise_long_rank.csv", index=False)
    scored.to_csv(ranked_path, index=False)
    _leaderboard_from_scored(scored).to_csv(board_path, index=False)
    return judgments_path, ranked_path, board_path
