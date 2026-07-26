#!/usr/bin/env python3
"""Diagnose whether response length is associated with pairwise win rates.

The analysis treats each run x task x mode as a separate comparison universe.
This avoids conflating legitimate between-task differences in deliverable length
with within-task evaluator preferences. Judge-specific win rates are averaged
only across judges eligible under the leave-family-out protocol.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import binomtest, spearmanr, ttest_1samp


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
SUMMARY_OUT = ROOT / "artifacts" / "cross_task" / "ten_run_summary"
FIGURE_OUTS = [ROOT / "artifacts" / "paper_figures", ROOT / "paper_figures"]
META_PATH = ROOT / "dashboard" / "dashboard-meta.json"

TASK_ORDER = [
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
MODES = ["augmentation", "automation"]


def word_count(text: object) -> int:
    return len(re.findall(r"\b[\w'-]+\b", str(text)))


def load_run_ids() -> list[str]:
    data = json.loads(META_PATH.read_text())
    return [item["id"] for item in data["meta"]["replicate_runs"]]


def load_output_level_rows() -> pd.DataFrame:
    records: list[dict] = []
    for run_id in load_run_ids():
        for task in TASK_ORDER:
            for mode in MODES:
                mode_dir = RESULTS / task / run_id / mode
                outputs = pd.read_csv(mode_dir / "outputs.csv").reset_index(drop=True)
                ranked = pd.read_csv(mode_dir / "pairwise_ranked_by_judge.csv")
                ranked = ranked[pd.to_numeric(ranked["total_games"], errors="coerce") > 0].copy()
                ranked["avg_win_rate"] = pd.to_numeric(ranked["avg_win_rate"], errors="coerce")
                judge_mean = (
                    ranked.groupby("item_id", as_index=False)
                    .agg(
                        mean_win_rate=("avg_win_rate", "mean"),
                        n_eligible_judges=("judge_model", "nunique"),
                    )
                )
                outputs["item_id"] = outputs.index
                outputs = outputs.merge(judge_mean, on="item_id", how="left", validate="one_to_one")
                if outputs["mean_win_rate"].isna().any():
                    missing = outputs.loc[outputs["mean_win_rate"].isna(), "model_label"].tolist()
                    raise RuntimeError(f"Missing win rates for {run_id}/{task}/{mode}: {missing}")
                for row in outputs.itertuples(index=False):
                    records.append(
                        {
                            "run_id": run_id,
                            "task": task,
                            "mode": mode,
                            "item_id": int(row.item_id),
                            "model": str(row.model_label),
                            "condition": str(row.condition),
                            "word_count": word_count(row.output),
                            "character_count": len(str(row.output)),
                            "mean_win_rate": float(row.mean_win_rate),
                            "n_eligible_judges": int(row.n_eligible_judges),
                        }
                    )
    return pd.DataFrame(records)


def slice_correlations(rows: pd.DataFrame) -> pd.DataFrame:
    records: list[dict] = []
    for (run_id, task, mode), group in rows.groupby(["run_id", "task", "mode"]):
        result = spearmanr(group["word_count"], group["mean_win_rate"])
        records.append(
            {
                "run_id": run_id,
                "task": task,
                "mode": mode,
                "spearman_rho": float(result.statistic),
                "p_value": float(result.pvalue),
                "n_outputs": int(len(group)),
                "median_words": float(group["word_count"].median()),
            }
        )
    return pd.DataFrame(records)


def summarize_correlations(correlations: pd.DataFrame) -> pd.DataFrame:
    records: list[dict] = []
    for (task, mode), group in correlations.groupby(["task", "mode"]):
        values = group["spearman_rho"].dropna().to_numpy()
        test = ttest_1samp(values, popmean=0.0)
        records.append(
            {
                "task": task,
                "task_label": TASK_LABELS[task],
                "mode": mode,
                "mean_within_run_rho": float(values.mean()),
                "median_within_run_rho": float(np.median(values)),
                "se_across_runs": float(values.std(ddof=1) / np.sqrt(len(values))),
                "two_sided_p": float(test.pvalue),
                "n_runs": int(len(values)),
            }
        )
    return pd.DataFrame(records)


def pair_majority_rows() -> pd.DataFrame:
    records: list[dict] = []
    for run_id in load_run_ids():
        for task in TASK_ORDER:
            for mode in MODES:
                mode_dir = RESULTS / task / run_id / mode
                outputs = pd.read_csv(mode_dir / "outputs.csv").reset_index(drop=True)
                outputs["word_count"] = outputs["output"].map(word_count)
                judgments = pd.read_csv(mode_dir / "pairwise_judgments_by_judge.csv")
                judgments = judgments[judgments["winner"].isin(["option_1", "option_2"])].copy()
                judgments["winner_idx"] = np.where(
                    judgments["winner"].eq("option_1"),
                    judgments["left_idx"],
                    judgments["right_idx"],
                )
                judgments["pair_lo"] = judgments[["left_idx", "right_idx"]].min(axis=1)
                judgments["pair_hi"] = judgments[["left_idx", "right_idx"]].max(axis=1)
                for (pair_lo, pair_hi), group in judgments.groupby(["pair_lo", "pair_hi"]):
                    shares = group["winner_idx"].value_counts(normalize=True)
                    lo_share = float(shares.get(pair_lo, 0.0))
                    hi_share = float(shares.get(pair_hi, 0.0))
                    if np.isclose(lo_share, hi_share):
                        outcome = "judge_tie"
                    else:
                        winner_idx = int(pair_lo if lo_share > hi_share else pair_hi)
                        loser_idx = int(pair_hi if winner_idx == pair_lo else pair_lo)
                        winner_words = int(outputs.loc[winner_idx, "word_count"])
                        loser_words = int(outputs.loc[loser_idx, "word_count"])
                        if winner_words == loser_words:
                            outcome = "length_tie"
                        else:
                            outcome = "longer_wins" if winner_words > loser_words else "shorter_wins"
                    records.append(
                        {
                            "run_id": run_id,
                            "task": task,
                            "mode": mode,
                            "pair_lo": int(pair_lo),
                            "pair_hi": int(pair_hi),
                            "outcome": outcome,
                            "n_judgments": int(len(group)),
                        }
                    )
    return pd.DataFrame(records)


def summarize_pair_majorities(rows: pd.DataFrame) -> pd.DataFrame:
    records: list[dict] = []
    for (task, mode), group in rows.groupby(["task", "mode"]):
        decisive = group[group["outcome"].isin(["longer_wins", "shorter_wins"])]
        longer = int(decisive["outcome"].eq("longer_wins").sum())
        total = int(len(decisive))
        test = binomtest(longer, total, p=0.5) if total else None
        records.append(
            {
                "task": task,
                "task_label": TASK_LABELS[task],
                "mode": mode,
                "longer_wins": longer,
                "shorter_wins": total - longer,
                "decisive_pairs": total,
                "share_longer_wins": longer / total if total else np.nan,
                "two_sided_binomial_p": float(test.pvalue) if test else np.nan,
                "judge_ties": int(group["outcome"].eq("judge_tie").sum()),
                "length_ties": int(group["outcome"].eq("length_tie").sum()),
            }
        )
    return pd.DataFrame(records)


def length_adjusted_rankings(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Residualize win rate on log word count within each run/task/mode slice."""
    adjusted: list[pd.DataFrame] = []
    for _, group in rows.groupby(["run_id", "task", "mode"], sort=False):
        group = group.copy()
        x = np.log1p(group["word_count"].to_numpy(dtype=float))
        y = group["mean_win_rate"].to_numpy(dtype=float)
        design = np.column_stack([np.ones(len(group)), x])
        fitted = design @ np.linalg.lstsq(design, y, rcond=None)[0]
        group["length_adjusted_win_rate"] = y - fitted + y.mean()
        group["unadjusted_rank"] = group["mean_win_rate"].rank(
            ascending=False, method="average"
        )
        group["length_adjusted_rank"] = group["length_adjusted_win_rate"].rank(
            ascending=False, method="average"
        )
        adjusted.append(group)
    detail = pd.concat(adjusted, ignore_index=True)

    summary = (
        detail.groupby(["mode", "model"], as_index=False)
        .agg(
            mean_unadjusted_rank=("unadjusted_rank", "mean"),
            mean_length_adjusted_rank=("length_adjusted_rank", "mean"),
            mean_word_count=("word_count", "mean"),
            n_slices=("run_id", "count"),
        )
    )
    summary["rank_shift_after_adjustment"] = (
        summary["mean_length_adjusted_rank"] - summary["mean_unadjusted_rank"]
    )
    return detail, summary


def draw_figure(correlation_summary: pd.DataFrame, pair_summary: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13.6, 5.8), dpi=240)
    colors = {"augmentation": "#2f6fcb", "automation": "#d96f31"}
    offsets = {"augmentation": -0.14, "automation": 0.14}
    y = np.arange(len(TASK_ORDER))

    ax = axes[0]
    ax.axvline(0, color="#667085", linewidth=1.0)
    for mode in MODES:
        sub = correlation_summary[correlation_summary["mode"] == mode].set_index("task").loc[TASK_ORDER]
        ax.errorbar(
            sub["mean_within_run_rho"],
            y + offsets[mode],
            xerr=1.96 * sub["se_across_runs"],
            fmt="o",
            color=colors[mode],
            ecolor=colors[mode],
            capsize=3,
            markersize=6,
            label=mode.title(),
        )
    ax.set_yticks(y)
    ax.set_yticklabels([TASK_LABELS[t] for t in TASK_ORDER])
    ax.invert_yaxis()
    ax.set_xlim(-1, 1)
    ax.set_xlabel("Mean within-run Spearman correlation\n(output words vs. pairwise win rate)")
    ax.set_title("A. Length--performance association", loc="left", fontweight="semibold")
    ax.grid(axis="x", color="#d9dee7", linewidth=0.8)
    ax.legend(frameon=False, loc="lower right")

    ax = axes[1]
    width = 0.34
    for mode, shift in [("augmentation", -width / 2), ("automation", width / 2)]:
        sub = pair_summary[pair_summary["mode"] == mode].set_index("task").loc[TASK_ORDER]
        ax.barh(
            y + shift,
            sub["share_longer_wins"],
            height=width,
            color=colors[mode],
            alpha=0.85,
            label=mode.title(),
        )
    ax.axvline(0.5, color="#667085", linestyle=(0, (4, 4)), linewidth=1.0)
    ax.set_yticks(y)
    ax.set_yticklabels([TASK_LABELS[t] for t in TASK_ORDER])
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("Share of decisive model pairs in which\nthe longer output wins")
    ax.set_title("B. Longer-output win share", loc="left", fontweight="semibold")
    ax.grid(axis="x", color="#d9dee7", linewidth=0.8)
    ax.legend(frameon=False, loc="lower right")

    fig.tight_layout(w_pad=3.0)
    for figure_out in FIGURE_OUTS:
        figure_out.mkdir(parents=True, exist_ok=True)
        for ext in ("png", "pdf"):
            fig.savefig(
                figure_out / f"figureA_output_length_diagnostic.{ext}",
                bbox_inches="tight",
                facecolor="white",
            )
    plt.close(fig)


def main() -> None:
    SUMMARY_OUT.mkdir(parents=True, exist_ok=True)
    output_rows = load_output_level_rows()
    correlations = slice_correlations(output_rows)
    correlation_summary = summarize_correlations(correlations)
    pair_rows = pair_majority_rows()
    pair_summary = summarize_pair_majorities(pair_rows)
    adjusted_detail, adjusted_summary = length_adjusted_rankings(output_rows)

    output_rows.to_csv(SUMMARY_OUT / "output_length_and_win_rates_10_runs.csv", index=False)
    correlations.to_csv(SUMMARY_OUT / "output_length_correlations_by_run_10_runs.csv", index=False)
    correlation_summary.to_csv(SUMMARY_OUT / "output_length_correlation_summary_10_runs.csv", index=False)
    pair_summary.to_csv(SUMMARY_OUT / "output_length_pair_majority_summary_10_runs.csv", index=False)
    adjusted_detail.to_csv(SUMMARY_OUT / "output_length_adjusted_ranks_by_run_10_runs.csv", index=False)
    adjusted_summary.to_csv(SUMMARY_OUT / "output_length_adjusted_rank_summary_10_runs.csv", index=False)
    draw_figure(correlation_summary, pair_summary)

    print("Mean within-run Spearman correlations:")
    print(correlation_summary.to_string(index=False))
    print("\nLonger-output majority win shares:")
    print(pair_summary.to_string(index=False))
    print("\nLength-adjusted model rankings:")
    print(
        adjusted_summary.sort_values(["mode", "mean_length_adjusted_rank"])
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
