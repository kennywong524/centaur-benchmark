"""Recompute the GPT-4.1 worker pilot using strict worker and assistant family masking.

Reads saved judge responses only. Makes no inference calls.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from centaur_benchmark.judge_pairwise import (
    _model_family,
    _score_from_pairwise,
    _write_panel_matrices,
    _write_score_summaries,
    validate_judge_batch,
)

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results/travel_planning/20260924_gpt41_worker_pilot"
OUT = RUN / "augmentation"
BACKUP = OUT / "before_strict_leave_family_out"

outputs = pd.read_csv(OUT / "outputs.csv").reset_index(drop=True)
judgments_source = (BACKUP / "pairwise_judgments_by_judge.csv") if BACKUP.exists() else (OUT / "pairwise_judgments_by_judge.csv")
judgments = pd.read_csv(judgments_source)
assert len(outputs) == 10 and outputs["worker_model"].eq("gpt-4.1").all()
assert len(judgments) in {100, 110} and judgments["parse_ok"].all()

def candidate_families(index: int) -> set[str]:
    row = outputs.iloc[index]
    families = {_model_family(row["worker_model"])}
    if row["model_id"] != "plain":
        families.add(_model_family(row["model_id"], row["model_label"]))
    return families

keep = []
for row in judgments.itertuples(index=False):
    judge_family = _model_family(row.judge_model)
    keep.append(judge_family not in candidate_families(int(row.left_idx))
                and judge_family not in candidate_families(int(row.right_idx)))
eligible = judgments.loc[keep].copy()
removed = judgments.loc[[not k for k in keep]].copy()
assert len(eligible) == 100 and len(removed) in {0, 10}
assert set(removed["judge_model"]).issubset({"gpt-4.1"})
assert set(eligible["judge_model"]) == {
    "anthropic/claude-opus-4-8", "google/gemini-3.1-pro", "deepseek-ai/DeepSeek-V3.1"
}

by_judge = []
scored_frames = []
for judge_model, frame in eligible.groupby("judge_model", sort=True):
    report = validate_judge_batch(frame)
    assert report["batch_ok"], (judge_model, report)
    scored = _score_from_pairwise(outputs, frame)
    scored["judge_model"] = judge_model
    scored["judge_label"] = frame["judge_label"].iloc[0]
    scored_frames.append(scored)
    by_judge.append(scored[["judge_model", "judge_label", "model_id", "model_label",
                            "condition", "avg_rank", "avg_win_rate", "total_wins", "total_games"]])
scored_all = pd.concat(scored_frames, ignore_index=True)
judge_board = pd.concat(by_judge, ignore_index=True)
judge_board = judge_board.loc[judge_board["total_games"].gt(0)].copy()
assert judge_board.groupby("judge_model").size().to_dict() == {
    "anthropic/claude-opus-4-8": 8,
    "deepseek-ai/DeepSeek-V3.1": 9,
    "google/gemini-3.1-pro": 9,
}

aggregate = (judge_board.groupby(["model_id", "model_label", "condition"], as_index=False)
    .agg(avg_rank_across_judges=("avg_rank", "mean"),
         sd_rank_across_judges=("avg_rank", "std"),
         avg_win_rate_across_judges=("avg_win_rate", "mean"),
         sd_win_rate_across_judges=("avg_win_rate", "std"),
         n_judges=("judge_model", "nunique")))
aggregate["aggregate_rank"] = aggregate["avg_rank_across_judges"].rank(
    ascending=True, method="min"
)
aggregate = aggregate.sort_values(
    ["aggregate_rank", "avg_rank_across_judges", "model_label"]
).reset_index(drop=True)
assert len(aggregate) == 10
assert aggregate["n_judges"].value_counts().to_dict() == {3: 6, 2: 4}

derived = [
    "pairwise_judgments_by_judge.csv", "pairwise_ranked_by_judge.csv",
    "leaderboard_by_judge.csv", "leaderboard_aggregate.csv",
    "leaderboard_matrix_rank_by_judge.csv", "leaderboard_matrix_win_rate_by_judge.csv",
    "leaderboard_matrix_aggregate.csv", "rubric_scores_long.csv",
    "rubric_scores_summary.csv", "judge_validation.json",
]
if not BACKUP.exists():
    BACKUP.mkdir()
    for name in derived:
        if (OUT / name).exists():
            shutil.copy2(OUT / name, BACKUP / name)

eligible.to_csv(OUT / "pairwise_judgments_by_judge.csv", index=False)
scored_all.to_csv(OUT / "pairwise_ranked_by_judge.csv", index=False)
judge_board.to_csv(OUT / "leaderboard_by_judge.csv", index=False)
aggregate.to_csv(OUT / "leaderboard_aggregate.csv", index=False)
_write_panel_matrices(OUT, judge_board, aggregate)
_write_score_summaries(OUT, outputs, eligible)
for judge_model, frame in eligible.groupby("judge_model"):
    label = frame["judge_label"].iloc[0]
    scored_all.loc[scored_all["judge_model"].eq(judge_model)].to_csv(
        OUT / f"pairwise_ranked_{label}.csv", index=False
    )

validation = {
    "policy": "A judge is excluded when its provider family matches the worker or assistant family of either candidate.",
    "worker_family": "openai", "excluded_judge": "gpt-4.1",
    "eligible_judges": sorted(eligible["judge_label"].unique().tolist()),
    "judgments_kept": len(eligible), "judgments_excluded": len(removed),
    "eligible_pair_counts": eligible.groupby("judge_model").size().to_dict(),
    "ranking_basis": "Mean of eligible judge-specific candidate ranks; lower is better.",
    "computed_at": datetime.now(timezone.utc).isoformat(),
    "prior_derived_files": str(BACKUP),
    "raw_excluded_judgments_retained_at": str(OUT / "pairwise_judgments_GPT-4.1.csv"),
}
(OUT / "judge_validation.json").write_text(json.dumps(validation, indent=2))
manifest_path = RUN / "pilot_manifest.json"
manifest = json.loads(manifest_path.read_text())
manifest["strict_leave_family_out"] = validation
manifest_path.write_text(json.dumps(manifest, indent=2))
print(aggregate[["aggregate_rank", "model_label", "avg_rank_across_judges",
                 "n_judges", "avg_win_rate_across_judges"]].to_string(index=False))
