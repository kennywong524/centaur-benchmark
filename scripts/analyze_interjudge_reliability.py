"""Measure inter-judge reliability on overlapping pairwise comparisons.

The judge panel is partially crossed because leave-family-out evaluation makes
some judge-output combinations ineligible. Krippendorff's alpha with nominal
distance accommodates that missingness. Choices are normalized to the
lower/higher output index so randomized A/B order does not affect agreement.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "artifacts" / "cross_task" / "ten_run_summary"
RUNS = [
    "20260610_scaffold_strict_v4",
    "20260612_fresh_rep1",
    "20260612_fresh_rep2",
    *[f"20260629_public_rep{i}" for i in range(4, 11)],
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
MODES = ["augmentation", "automation"]
ITEM_COLUMNS = ["run_id", "task", "mode", "pair_low", "pair_high"]


def load_ratings() -> tuple[pd.DataFrame, dict[str, int]]:
    frames: list[pd.DataFrame] = []
    raw_rows = 0
    parse_failures = 0
    nonprimary_repeats = 0

    for run_id in RUNS:
        for task in TASKS:
            for mode in MODES:
                path = (
                    ROOT
                    / "results"
                    / task
                    / run_id
                    / mode
                    / "pairwise_judgments_by_judge.csv"
                )
                frame = pd.read_csv(path)
                raw_rows += len(frame)
                parse_ok = frame["parse_ok"].fillna(False).astype(bool)
                parse_failures += int((~parse_ok).sum())
                nonprimary_repeats += int((frame["replicate_id"] != 0).sum())
                frame = frame[
                    parse_ok
                    & (frame["replicate_id"] == 0)
                    & frame["winner"].isin(["option_1", "option_2"])
                ].copy()

                frame["pair_low"] = frame[["left_idx", "right_idx"]].min(axis=1).astype(int)
                frame["pair_high"] = frame[["left_idx", "right_idx"]].max(axis=1).astype(int)
                option_1_selected_low = (
                    (frame["winner"] == "option_1")
                    & (frame["left_idx"] == frame["pair_low"])
                )
                option_2_selected_low = (
                    (frame["winner"] == "option_2")
                    & (frame["right_idx"] == frame["pair_low"])
                )
                frame["choice"] = np.where(
                    option_1_selected_low | option_2_selected_low, 0, 1
                )
                frame["run_id"] = run_id
                frame["task"] = task
                frame["mode"] = mode
                frames.append(
                    frame[
                        [
                            *ITEM_COLUMNS,
                            "judge_model",
                            "judge_label",
                            "choice",
                        ]
                    ]
                )

    ratings = pd.concat(frames, ignore_index=True)
    duplicate_count = int(
        ratings.duplicated([*ITEM_COLUMNS, "judge_model"], keep=False).sum()
    )
    ratings = ratings.drop_duplicates([*ITEM_COLUMNS, "judge_model"], keep="first")
    audit = {
        "raw_judgment_rows": raw_rows,
        "parse_failures": parse_failures,
        "nonprimary_repeated_evaluations_excluded": nonprimary_repeats,
        "duplicate_judge_item_rows": duplicate_count,
        "usable_primary_ratings": len(ratings),
    }
    return ratings, audit


def reliability_stats(frame: pd.DataFrame) -> dict[str, float | int]:
    agreeing_pairs = 0
    judge_pairs = 0
    item_count = 0
    unanimous_items = 0
    single_rated_items = 0
    pooled_choices: list[int] = []

    for _, item in frame.groupby(ITEM_COLUMNS, sort=False):
        item = item.drop_duplicates("judge_model")
        if len(item) < 2:
            single_rated_items += 1
            continue
        choices = item["choice"].astype(int)
        n_zero = int((choices == 0).sum())
        n_one = int((choices == 1).sum())
        item_count += 1
        unanimous_items += int(n_zero == 0 or n_one == 0)
        agreeing_pairs += n_zero * (n_zero - 1) // 2 + n_one * (n_one - 1) // 2
        judge_pairs += len(item) * (len(item) - 1) // 2
        pooled_choices.extend(choices.tolist())

    if not judge_pairs:
        return {
            "items_with_overlap": item_count,
            "single_rated_items_excluded": single_rated_items,
            "judge_pair_decisions": 0,
            "agreement_rate": np.nan,
            "unanimous_item_rate": np.nan,
            "krippendorff_alpha_nominal": np.nan,
            "ratings_in_alpha": 0,
        }

    agreement = agreeing_pairs / judge_pairs
    observed_disagreement = 1.0 - agreement
    n_ratings = len(pooled_choices)
    n_zero = pooled_choices.count(0)
    n_one = pooled_choices.count(1)
    expected_disagreement = (
        2.0 * n_zero * n_one / (n_ratings * (n_ratings - 1))
        if n_ratings > 1
        else np.nan
    )
    alpha = (
        1.0 - observed_disagreement / expected_disagreement
        if expected_disagreement and not np.isnan(expected_disagreement)
        else np.nan
    )
    return {
        "items_with_overlap": item_count,
        "single_rated_items_excluded": single_rated_items,
        "judge_pair_decisions": judge_pairs,
        "agreement_rate": agreement,
        "unanimous_item_rate": unanimous_items / item_count,
        "krippendorff_alpha_nominal": alpha,
        "ratings_in_alpha": n_ratings,
    }


def scope_summary(ratings: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    scopes = [
        ("overall", "all", ratings),
        *[(mode, mode, ratings[ratings["mode"] == mode]) for mode in MODES],
    ]
    for scope, mode, frame in scopes:
        rows.append({"scope": scope, "mode": mode, **reliability_stats(frame)})
    return pd.DataFrame(rows)


def task_mode_summary(ratings: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for task in TASKS:
        for mode in MODES:
            frame = ratings[(ratings["task"] == task) & (ratings["mode"] == mode)]
            rows.append({"task": task, "mode": mode, **reliability_stats(frame)})
    return pd.DataFrame(rows)


def cohen_kappa(left: pd.Series, right: pd.Series) -> float:
    observed = float((left == right).mean())
    left_one = float(left.mean())
    right_one = float(right.mean())
    expected = left_one * right_one + (1.0 - left_one) * (1.0 - right_one)
    return (observed - expected) / (1.0 - expected) if expected < 1.0 else np.nan


def judge_pair_summary(ratings: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    judges = sorted(ratings["judge_label"].unique())
    for mode in ["all", *MODES]:
        scoped = ratings if mode == "all" else ratings[ratings["mode"] == mode]
        for judge_a, judge_b in combinations(judges, 2):
            left = scoped[scoped["judge_label"] == judge_a][
                [*ITEM_COLUMNS, "choice"]
            ].rename(columns={"choice": "choice_a"})
            right = scoped[scoped["judge_label"] == judge_b][
                [*ITEM_COLUMNS, "choice"]
            ].rename(columns={"choice": "choice_b"})
            overlap = left.merge(right, on=ITEM_COLUMNS, how="inner")
            rows.append(
                {
                    "mode": mode,
                    "judge_a": judge_a,
                    "judge_b": judge_b,
                    "overlapping_comparisons": len(overlap),
                    "agreement_rate": float(
                        (overlap["choice_a"] == overlap["choice_b"]).mean()
                    ),
                    "cohen_kappa": cohen_kappa(
                        overlap["choice_a"], overlap["choice_b"]
                    ),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ratings, audit = load_ratings()
    scopes = scope_summary(ratings)
    by_task_mode = task_mode_summary(ratings)
    by_judge_pair = judge_pair_summary(ratings)

    scopes.to_csv(OUT_DIR / "interjudge_reliability_summary_10_runs.csv", index=False)
    by_task_mode.to_csv(
        OUT_DIR / "interjudge_reliability_by_task_mode_10_runs.csv", index=False
    )
    by_judge_pair.to_csv(
        OUT_DIR / "interjudge_reliability_by_judge_pair_10_runs.csv", index=False
    )
    payload = {
        "method": {
            "agreement": (
                "Share of all eligible judge-pair decisions that select the same "
                "canonical winner on the same output comparison."
            ),
            "alpha": (
                "Krippendorff's alpha with nominal distance, calculated on the "
                "partially crossed leave-family-out panel."
            ),
            "repeat_handling": (
                "Only replicate_id=0 is retained so the initial meal-plan "
                "n_evals=3 artifact does not receive extra weight."
            ),
        },
        "audit": audit,
        "summary": scopes.to_dict(orient="records"),
    }
    (OUT_DIR / "interjudge_reliability_10_runs.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    print(scopes.to_string(index=False))
    print(f"\nWrote inter-judge reliability artifacts to {OUT_DIR}")


if __name__ == "__main__":
    main()
