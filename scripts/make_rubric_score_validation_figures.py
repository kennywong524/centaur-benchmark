#!/usr/bin/env python3
"""Build ten-run rubric-score robustness figures for the paper."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import rankdata, spearmanr


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "dashboard" / "dashboard-data.json"
OUT = ROOT / "artifacts" / "paper_figures"
SUMMARY_OUT = ROOT / "artifacts" / "cross_task" / "ten_run_summary"

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
MODEL_ORDER = [
    "GPT-5-Mini",
    "Claude-Opus-4.8",
    "GPT-O4-Mini",
    "Claude-Sonnet-4.6",
    "GPT-OSS-120B",
    "Gemini-3.1-Pro",
    "DeepSeek-V3.1",
    "GPT-4.1",
    "GPT-O3-Mini",
    "GPT-3.5-Turbo",
]


def load_rows() -> tuple[pd.DataFrame, pd.DataFrame]:
    data = json.loads(DATA_PATH.read_text())
    run_ids = [item["id"] for item in data["meta"]["replicate_runs"]]
    pairwise_rows: list[dict] = []
    rubric_rows: list[dict] = []

    for run_id in run_ids:
        run = data["runs_by_id"][run_id]
        for row in run["aggregate"]:
            if not isinstance(row.get("rank_value"), (int, float)):
                continue
            model_label = "GPT-3.5-Turbo" if row["model_label"] == "plain" else row["model_label"]
            pairwise_rows.append(
                {
                    "run_id": run_id,
                    "task": row["task_slug"],
                    "mode": row["mode"],
                    "model": model_label,
                    "pairwise_rank": float(row["rank_value"]),
                }
            )
        for row in run["rubric_scores"]:
            if not isinstance(row.get("mean_score"), (int, float)):
                continue
            model_label = "GPT-3.5-Turbo" if row["model_label"] == "plain" else row["model_label"]
            rubric_rows.append(
                {
                    "run_id": run_id,
                    "task": row["task_slug"],
                    "mode": row["mode"],
                    "judge": row["judge_model"],
                    "model": model_label,
                    "dimension": row["dimension"],
                    "score": float(row["mean_score"]),
                }
            )
    return pd.DataFrame(pairwise_rows), pd.DataFrame(rubric_rows)


def rubric_rankings(rubric_rows: pd.DataFrame) -> pd.DataFrame:
    # Every rubric dimension receives equal weight within a judge/model cell.
    judge_model = (
        rubric_rows.groupby(["run_id", "task", "mode", "judge", "model"], as_index=False)
        .agg(mean_rubric_score=("score", "mean"), n_dimensions=("dimension", "nunique"))
    )

    # Judges use the 1--10 scale differently. Standardize within each
    # run/task/mode/judge comparison universe before combining eligible judges.
    groups = judge_model.groupby(["run_id", "task", "mode", "judge"])["mean_rubric_score"]
    means = groups.transform("mean")
    sds = groups.transform(lambda values: values.std(ddof=0)).replace(0, np.nan)
    judge_model["standardized_score"] = (
        (judge_model["mean_rubric_score"] - means) / sds
    ).fillna(0.0)

    model_scores = (
        judge_model.groupby(["run_id", "task", "mode", "model"], as_index=False)
        .agg(
            standardized_score=("standardized_score", "mean"),
            raw_rubric_score=("mean_rubric_score", "mean"),
            n_judges=("judge", "nunique"),
        )
    )

    ranked = []
    for _, group in model_scores.groupby(["run_id", "task", "mode"], sort=False):
        group = group.copy()
        group["rubric_rank"] = rankdata(
            -group["standardized_score"].to_numpy(), method="average"
        )
        ranked.append(group)
    return pd.concat(ranked, ignore_index=True)


def summarize(pairwise: pd.DataFrame, rubric: pd.DataFrame) -> pd.DataFrame:
    pair_summary = (
        pairwise.groupby(["task", "mode", "model"], as_index=False)
        .agg(
            pairwise_mean_rank=("pairwise_rank", "mean"),
            pairwise_se=("pairwise_rank", lambda x: x.std(ddof=1) / np.sqrt(x.count())),
            n_runs_pairwise=("run_id", "nunique"),
        )
    )
    rubric_summary = (
        rubric.groupby(["task", "mode", "model"], as_index=False)
        .agg(
            rubric_mean_rank=("rubric_rank", "mean"),
            rubric_se=("rubric_rank", lambda x: x.std(ddof=1) / np.sqrt(x.count())),
            mean_standardized_score=("standardized_score", "mean"),
            mean_raw_rubric_score=("raw_rubric_score", "mean"),
            raw_rubric_score_se=(
                "raw_rubric_score",
                lambda x: x.std(ddof=1) / np.sqrt(x.count()),
            ),
            n_runs_rubric=("run_id", "nunique"),
        )
    )
    return pair_summary.merge(rubric_summary, on=["task", "mode", "model"], how="inner")


def draw_heatmaps(summary: pd.DataFrame) -> None:
    cmap = sns.diverging_palette(145, 20, s=80, l=55, center="light", as_cmap=True)
    fig, axes = plt.subplots(2, 1, figsize=(15.6, 9.8), dpi=240)

    for ax, mode in zip(axes, ["augmentation", "automation"]):
        sub = summary[summary["mode"] == mode].copy()
        values = sub.pivot(index="task", columns="model", values="rubric_mean_rank")
        ses = sub.pivot(index="task", columns="model", values="rubric_se")
        values = values.reindex(index=TASK_ORDER, columns=MODEL_ORDER)
        ses = ses.reindex(index=TASK_ORDER, columns=MODEL_ORDER)
        annotations = values.copy().astype(object)
        for task in values.index:
            for model in values.columns:
                value = values.loc[task, model]
                se = ses.loc[task, model]
                annotations.loc[task, model] = (
                    "" if pd.isna(value) else f"{value:.1f}\n$\\pm${se:.1f}"
                )

        sns.heatmap(
            values,
            ax=ax,
            cmap=cmap,
            vmin=1,
            vmax=10,
            annot=annotations,
            fmt="",
            annot_kws={"fontsize": 9.2, "fontweight": "semibold"},
            linewidths=0.8,
            linecolor="white",
            cbar_kws={"label": "Mean rubric-derived rank", "pad": 0.015},
        )
        ax.set_title(
            f"{mode.title()}: rubric-score rankings across ten runs",
            loc="left",
            fontsize=14,
            fontweight="semibold",
            pad=10,
        )
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.set_yticklabels([TASK_LABELS[t] for t in TASK_ORDER], rotation=0, fontsize=10.5)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=25, ha="right", fontsize=9.5)
        ax.collections[0].colorbar.ax.tick_params(labelsize=9)
        ax.collections[0].colorbar.set_label("Mean rubric-derived rank", fontsize=10)

    fig.subplots_adjust(left=0.13, right=0.96, top=0.96, bottom=0.10, hspace=0.48)
    for ext in ["png", "pdf"]:
        fig.savefig(OUT / f"figureA_rubric_score_rank_heatmaps.{ext}", bbox_inches="tight")
    plt.close(fig)


def draw_average_score_heatmaps(summary: pd.DataFrame) -> None:
    cmap = sns.diverging_palette(20, 145, s=80, l=55, center="light", as_cmap=True)
    fig, axes = plt.subplots(2, 1, figsize=(15.6, 9.8), dpi=240)

    for ax, mode in zip(axes, ["augmentation", "automation"]):
        sub = summary[summary["mode"] == mode].copy()
        values = sub.pivot(index="task", columns="model", values="mean_raw_rubric_score")
        ses = sub.pivot(index="task", columns="model", values="raw_rubric_score_se")
        values = values.reindex(index=TASK_ORDER, columns=MODEL_ORDER)
        ses = ses.reindex(index=TASK_ORDER, columns=MODEL_ORDER)
        annotations = values.copy().astype(object)
        for task in values.index:
            for model in values.columns:
                value = values.loc[task, model]
                se = ses.loc[task, model]
                annotations.loc[task, model] = (
                    "" if pd.isna(value) else f"{value:.2f}\n$\\pm${se:.2f}"
                )

        sns.heatmap(
            values,
            ax=ax,
            cmap=cmap,
            vmin=1,
            vmax=10,
            annot=annotations,
            fmt="",
            annot_kws={"fontsize": 8.8, "fontweight": "semibold"},
            linewidths=0.8,
            linecolor="white",
            cbar_kws={"label": "Mean rubric score (1--10)", "pad": 0.015},
        )
        ax.set_title(
            f"{mode.title()}: average rubric scores across ten runs",
            loc="left",
            fontsize=14,
            fontweight="semibold",
            pad=10,
        )
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.set_yticklabels([TASK_LABELS[t] for t in TASK_ORDER], rotation=0, fontsize=10.5)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=25, ha="right", fontsize=9.5)
        ax.collections[0].colorbar.ax.tick_params(labelsize=9)
        ax.collections[0].colorbar.set_label("Mean rubric score (1--10)", fontsize=10)

    fig.subplots_adjust(left=0.13, right=0.96, top=0.96, bottom=0.10, hspace=0.48)
    for ext in ["png", "pdf"]:
        fig.savefig(OUT / f"figureA_average_rubric_score_heatmaps.{ext}", bbox_inches="tight")
    plt.close(fig)


def draw_model_average_scores(rubric: pd.DataFrame) -> None:
    # Average across tasks inside each run first, then estimate uncertainty
    # across the ten independent run-level averages.
    run_model = (
        rubric.groupby(["run_id", "mode", "model"], as_index=False)
        .agg(run_average_score=("raw_rubric_score", "mean"))
    )
    model_summary = (
        run_model.groupby(["mode", "model"], as_index=False)
        .agg(
            mean_score=("run_average_score", "mean"),
            se=("run_average_score", lambda x: x.std(ddof=1) / np.sqrt(x.count())),
            n_runs=("run_id", "nunique"),
        )
    )

    fig, axes = plt.subplots(1, 2, figsize=(12.6, 6.2), dpi=240, sharex=True)
    styles = {
        "augmentation": ("#2f6fcb", "A. Augmentation"),
        "automation": ("#d96f31", "B. Automation"),
    }
    for ax, mode in zip(axes, ["augmentation", "automation"]):
        color, title = styles[mode]
        sub = model_summary[model_summary["mode"] == mode].sort_values(
            "mean_score", ascending=True
        )
        y = np.arange(len(sub))
        ax.errorbar(
            sub["mean_score"],
            y,
            xerr=sub["se"],
            fmt="o",
            markersize=7,
            color=color,
            ecolor="#657083",
            elinewidth=1.3,
            capsize=3,
            capthick=1.1,
        )
        ax.set_yticks(y)
        labels = sub["model"].tolist()
        if mode == "augmentation":
            labels = ["GPT-3.5-Turbo (plain)" if x == "GPT-3.5-Turbo" else x for x in labels]
        ax.set_yticklabels(labels, fontsize=9.5)
        ax.set_title(title, loc="left", fontsize=13, fontweight="semibold")
        ax.set_xlabel("Absolute mean rubric score (higher is better)", fontsize=10.5)
        ax.set_xlim(1, 10)
        ax.grid(axis="x", color="#d9dee7", linewidth=0.8)
        for yi, (_, row) in enumerate(sub.iterrows()):
            ax.text(
                row["mean_score"] + row["se"] + 0.08,
                yi,
                f"{row['mean_score']:.2f} $\\pm$ {row['se']:.2f}",
                va="center",
                fontsize=8.2,
                color="#1f2433",
            )
    fig.subplots_adjust(left=0.16, right=0.98, bottom=0.12, top=0.92, wspace=0.45)
    for ext in ["png", "pdf"]:
        fig.savefig(OUT / f"figureA_model_average_rubric_scores.{ext}", bbox_inches="tight")
    plt.close(fig)

    model_summary.to_csv(
        SUMMARY_OUT / "model_average_rubric_scores_10_runs.csv", index=False
    )


def alignment_statistics(summary: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    slice_rows = []
    for (task, mode), group in summary.groupby(["task", "mode"]):
        rho = float(spearmanr(group["pairwise_mean_rank"], group["rubric_mean_rank"]).statistic)
        pair_winners = set(
            group.loc[group["pairwise_mean_rank"] == group["pairwise_mean_rank"].min(), "model"]
        )
        rubric_winners = set(
            group.loc[group["rubric_mean_rank"] == group["rubric_mean_rank"].min(), "model"]
        )
        slice_rows.append(
            {
                "task": task,
                "mode": mode,
                "spearman": rho,
                "winner_overlap": bool(pair_winners & rubric_winners),
                "mean_absolute_rank_gap": float(
                    np.mean(np.abs(group["pairwise_mean_rank"] - group["rubric_mean_rank"]))
                ),
            }
        )
    slices = pd.DataFrame(slice_rows)
    stats = {
        "mean_spearman": float(slices["spearman"].mean()),
        "median_spearman": float(slices["spearman"].median()),
        "winner_agreement": float(slices["winner_overlap"].mean()),
        "winner_matches": int(slices["winner_overlap"].sum()),
        "n_slices": int(len(slices)),
        "mean_absolute_rank_gap": float(slices["mean_absolute_rank_gap"].mean()),
    }
    return slices, stats


def draw_alignment(summary: pd.DataFrame, stats: dict) -> None:
    fig, ax = plt.subplots(figsize=(7.8, 7.0), dpi=240)
    mode_style = {
        "augmentation": ("#2f6fcb", "Augmentation"),
        "automation": ("#d96f31", "Automation"),
    }
    for mode, (color, label) in mode_style.items():
        sub = summary[summary["mode"] == mode]
        ax.scatter(
            sub["pairwise_mean_rank"],
            sub["rubric_mean_rank"],
            s=50,
            color=color,
            alpha=0.72,
            edgecolor="white",
            linewidth=0.5,
            label=label,
        )
    ax.plot([1, 10], [1, 10], color="#1f2433", linestyle=(0, (5, 5)), linewidth=1.4)
    ax.fill_between([1, 10], [0, 9], [2, 11], color="#dce8f7", alpha=0.35, zorder=0)
    ax.set_xlim(0.7, 10.3)
    ax.set_ylim(0.7, 10.3)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Pairwise mean rank", fontsize=12)
    ax.set_ylabel("Rubric-derived mean rank", fontsize=12)
    ax.set_xticks(range(1, 11))
    ax.set_yticks(range(1, 11))
    ax.grid(True, color="#d9dee7", linewidth=0.8)
    ax.legend(loc="lower right", frameon=True)
    ax.text(
        0.04,
        0.96,
        (
            f"Mean within-task Spearman $\\rho$ = {stats['mean_spearman']:.2f}\n"
            f"Same winner in {stats['winner_matches']}/{stats['n_slices']} task--mode slices\n"
            f"Mean absolute rank gap = {stats['mean_absolute_rank_gap']:.2f}"
        ),
        transform=ax.transAxes,
        va="top",
        fontsize=10.5,
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "edgecolor": "#c9d0da"},
    )
    fig.tight_layout()
    for ext in ["png", "pdf"]:
        fig.savefig(OUT / f"figureA_pairwise_vs_rubric_rank_alignment.{ext}", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUT.mkdir(parents=True, exist_ok=True)
    pairwise, rubric_rows = load_rows()
    rubric = rubric_rankings(rubric_rows)
    summary = summarize(pairwise, rubric)
    slices, stats = alignment_statistics(summary)

    summary.to_csv(SUMMARY_OUT / "pairwise_vs_rubric_rankings_10_runs.csv", index=False)
    slices.to_csv(SUMMARY_OUT / "pairwise_vs_rubric_alignment_by_slice_10_runs.csv", index=False)
    (SUMMARY_OUT / "pairwise_vs_rubric_alignment_10_runs.json").write_text(
        json.dumps(stats, indent=2) + "\n"
    )
    draw_heatmaps(summary)
    draw_average_score_heatmaps(summary)
    draw_model_average_scores(rubric)
    draw_alignment(summary, stats)
    print(json.dumps(stats, indent=2))
    print(f"Wrote figures to {OUT}")


if __name__ == "__main__":
    main()
