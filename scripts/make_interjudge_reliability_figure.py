"""Create the appendix figure for inter-judge reliability."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "artifacts" / "cross_task" / "ten_run_summary"
OUT_DIR = ROOT / "artifacts" / "paper_figures"

SCOPE_LABELS = {
    "overall": "Overall",
    "augmentation": "Augmentation",
    "automation": "Automation",
}
TASK_LABELS = {
    "counselling": "Counseling",
    "market_trends": "Market Trends",
    "meal_plan": "Menu Planning",
    "operations_research": "Operations Research",
    "tax_prep": "Tax Prep",
    "travel_planning": "Travel Agent",
    "tutoring": "Tutoring",
}


def main() -> None:
    summary = pd.read_csv(
        DATA_DIR / "interjudge_reliability_summary_10_runs.csv"
    )
    by_task_mode = pd.read_csv(
        DATA_DIR / "interjudge_reliability_by_task_mode_10_runs.csv"
    )

    summary["label"] = summary["scope"].map(SCOPE_LABELS)
    summary = summary.set_index("scope").loc[
        ["overall", "augmentation", "automation"]
    ].reset_index()

    task_order = list(TASK_LABELS)
    mode_order = ["augmentation", "automation"]
    alpha_matrix = (
        by_task_mode.pivot(
            index="task",
            columns="mode",
            values="krippendorff_alpha_nominal",
        )
        .loc[task_order, mode_order]
        .to_numpy()
    )

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "xtick.labelsize": 10.5,
            "ytick.labelsize": 10.5,
        }
    )

    fig = plt.figure(figsize=(13.2, 5.8), facecolor="white")
    grid = fig.add_gridspec(1, 2, width_ratios=[1.05, 1.35], wspace=0.34)

    # Panel A: headline reliability metrics.
    ax_left = fig.add_subplot(grid[0, 0])
    x = np.arange(len(summary))
    width = 0.34
    agreement = summary["agreement_rate"].to_numpy()
    alpha = summary["krippendorff_alpha_nominal"].to_numpy()

    bars_agreement = ax_left.bar(
        x - width / 2,
        agreement,
        width,
        color="#2A836B",
        label="Raw agreement",
    )
    bars_alpha = ax_left.bar(
        x + width / 2,
        alpha,
        width,
        color="#315C9B",
        label=r"Krippendorff's $\alpha$",
    )
    ax_left.set_ylim(0, 0.86)
    ax_left.set_xticks(x, summary["label"])
    ax_left.set_ylabel("Reliability")
    ax_left.set_title("A. Agreement across eligible judges", loc="left", pad=12)
    ax_left.grid(axis="y", color="#D9DEE7", linewidth=0.8)
    ax_left.set_axisbelow(True)
    ax_left.spines[["top", "right"]].set_visible(False)
    ax_left.legend(frameon=False, loc="upper left", ncols=2, fontsize=9.5)

    for bar, value in zip(bars_agreement, agreement):
        ax_left.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.018,
            f"{value:.1%}",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="semibold",
        )
    for bar, value in zip(bars_alpha, alpha):
        ax_left.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.018,
            f"{value:.3f}",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="semibold",
        )

    # Panel B: task- and mode-level chance-corrected reliability.
    ax_right = fig.add_subplot(grid[0, 1])
    image = ax_right.imshow(
        alpha_matrix,
        cmap="YlGnBu",
        vmin=0.20,
        vmax=0.65,
        aspect="auto",
    )
    ax_right.set_xticks(
        np.arange(len(mode_order)), ["Augmentation", "Automation"]
    )
    ax_right.set_yticks(
        np.arange(len(task_order)),
        [TASK_LABELS[task] for task in task_order],
    )
    ax_right.set_title(
        r"B. Krippendorff's $\alpha$ by task and mode",
        loc="left",
        pad=12,
    )
    ax_right.tick_params(length=0)
    for spine in ax_right.spines.values():
        spine.set_visible(False)

    for row in range(alpha_matrix.shape[0]):
        for col in range(alpha_matrix.shape[1]):
            value = alpha_matrix[row, col]
            text_color = "white" if value >= 0.47 else "#172033"
            ax_right.text(
                col,
                row,
                f"{value:.3f}",
                ha="center",
                va="center",
                color=text_color,
                fontsize=11,
                fontweight="semibold",
            )

    colorbar = fig.colorbar(image, ax=ax_right, fraction=0.046, pad=0.04)
    colorbar.set_label(r"Krippendorff's $\alpha$", rotation=90, labelpad=10)
    colorbar.outline.set_visible(False)

    fig.text(
        0.01,
        0.01,
        "Raw agreement is the share of eligible judge-pair decisions selecting "
        "the same canonical winner. Alpha adjusts for chance agreement.",
        fontsize=9.5,
        color="#4B5565",
    )
    fig.subplots_adjust(left=0.10, right=0.96, top=0.90, bottom=0.16)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    png_path = OUT_DIR / "figureA_interjudge_reliability.png"
    pdf_path = OUT_DIR / "figureA_interjudge_reliability.pdf"
    fig.savefig(png_path, dpi=320, bbox_inches="tight", facecolor="white")
    fig.savefig(pdf_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    print(png_path)
    print(pdf_path)


if __name__ == "__main__":
    main()
