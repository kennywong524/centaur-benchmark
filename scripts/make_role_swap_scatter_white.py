#!/usr/bin/env python3
"""Export the dashboard role-swap scatter on a white page background."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "dashboard" / "dashboard-data.json"
OUTPUT_DIRS = [ROOT / "artifacts" / "paper_figures", ROOT / "paper_figures"]

TASK_ORDER = [
    "counselling",
    "market_trends",
    "meal_plan",
    "operations_research",
    "tax_prep",
    "travel_planning",
    "tutoring",
]

SHORT_LABELS = {
    "GPT-5-Mini": "G5M",
    "GPT-4.1": "G4.1",
    "GPT-O4-Mini": "O4",
    "GPT-O3-Mini": "O3",
    "GPT-OSS-120B": "OSS",
    "DeepSeek-V3.1": "DS",
    "Claude-Opus-4.8": "Opus",
    "Claude-Sonnet-4.6": "Sonnet",
    "Gemini-3.1-Pro": "Gemini",
}

BASELINES = {"plain", "GPT-3.5-Turbo", "GPT-3.5-Turbo (plain)"}


def _rank_of_ranks(rows: list[dict], mode: str) -> list[dict]:
    ranked = []
    for task in TASK_ORDER:
        task_rows = [r for r in rows if r.get("mode") == mode and r.get("task_slug") == task]
        task_rows.sort(
            key=lambda r: (
                float(r.get("rank_value", float("inf"))),
                -float(r.get("score", float("-inf"))),
                r.get("model_label", ""),
            )
        )
        for display_rank, row in enumerate(task_rows, start=1):
            ranked.append({**row, "display_rank": display_rank})
    return ranked


def panel_average_ranks(data: dict) -> pd.DataFrame:
    buckets: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"automation": [], "augmentation": []}
    )

    for run_meta in data["meta"]["replicate_runs"]:
        run = data["runs_by_id"][run_meta["id"]]
        per_run: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: {"automation": [], "augmentation": []}
        )
        for mode in ("augmentation", "automation"):
            for row in _rank_of_ranks(run["aggregate"], mode):
                per_run[row["model_label"]][mode].append(float(row["display_rank"]))

        for model, values in per_run.items():
            if model in BASELINES or not values["automation"] or not values["augmentation"]:
                continue
            buckets[model]["automation"].append(sum(values["automation"]) / len(values["automation"]))
            buckets[model]["augmentation"].append(sum(values["augmentation"]) / len(values["augmentation"]))

    rows = []
    for model, values in buckets.items():
        rows.append(
            {
                "model": model,
                "automation_rank": sum(values["automation"]) / len(values["automation"]),
                "augmentation_rank": sum(values["augmentation"]) / len(values["augmentation"]),
            }
        )
    return pd.DataFrame(rows)


def draw(df: pd.DataFrame) -> None:
    max_rank = max(9, len(df))
    df = df.copy()
    df["automation_reverse"] = max_rank + 1 - df["automation_rank"]
    df["augmentation_reverse"] = max_rank + 1 - df["augmentation_rank"]
    df["gap"] = df["augmentation_reverse"] - df["automation_reverse"]

    fig, ax = plt.subplots(figsize=(8.2, 8.2), dpi=240, facecolor="white")
    ax.set_facecolor("white")
    ax.set_xlim(1, 9)
    ax.set_ylim(1, 9)
    ax.set_aspect("equal", adjustable="box")

    # Restrained quadrant fills preserve the dashboard's reading cues while
    # the page and plotting surface remain white.
    ax.axvspan(1, 5, ymin=0.5, ymax=1.0, color="#2f6fcb", alpha=0.075, zorder=0)
    ax.axvspan(5, 9, ymin=0.5, ymax=1.0, color="#27805a", alpha=0.065, zorder=0)
    ax.axvspan(1, 5, ymin=0.0, ymax=0.5, color="#7a8496", alpha=0.055, zorder=0)
    ax.axvspan(5, 9, ymin=0.0, ymax=0.5, color="#d96f31", alpha=0.075, zorder=0)

    ticks = [1, 2, 4, 6, 8, 9]
    ax.set_xticks(ticks)
    ax.set_yticks(ticks)
    ax.grid(color="#e6eaf0", linewidth=0.85, zorder=0)
    ax.plot([1, 9], [1, 9], color="#8a93a3", linewidth=1.5, linestyle=(0, (4, 4)), zorder=1)

    colors = {"aug": "#2f6fcb", "auto": "#d27743", "bal": "#66758a"}
    label_offsets = {
        "GPT-5-Mini": (-10, 0, "right"),
        "GPT-4.1": (10, 0, "left"),
        "GPT-O4-Mini": (10, 0, "left"),
        "GPT-O3-Mini": (10, 0, "left"),
        "GPT-OSS-120B": (10, 0, "left"),
        "DeepSeek-V3.1": (10, 0, "left"),
        "Claude-Opus-4.8": (10, 0, "left"),
        "Claude-Sonnet-4.6": (10, 0, "left"),
        "Gemini-3.1-Pro": (10, 0, "left"),
    }

    for _, row in df.iterrows():
        gap = row["gap"]
        # Use the presentation threshold from the captured dashboard figure;
        # Gemini's small cross-role gap remains visually neutral.
        lean = "aug" if gap >= 0.85 else "auto" if gap <= -0.85 else "bal"
        color = colors[lean]
        x, y = row["automation_reverse"], row["augmentation_reverse"]
        ax.scatter(x, y, s=245, color=color, alpha=0.16, edgecolors="none", zorder=3)
        ax.scatter(x, y, s=105, color=color, edgecolors="white", linewidths=2.0, zorder=4)
        dx, dy, ha = label_offsets[row["model"]]
        ax.annotate(
            SHORT_LABELS[row["model"]],
            (x, y),
            xytext=(dx, dy),
            textcoords="offset points",
            ha=ha,
            va="center",
            fontsize=12.5,
            fontweight="bold",
            color="#1f2937",
            zorder=5,
        )

    ax.text(1.20, 8.82, "Stronger assistant", ha="left", va="top", fontsize=11.5, fontweight="bold", color="#3569ba")
    ax.text(8.80, 8.82, "Strong in both", ha="right", va="top", fontsize=11.5, fontweight="bold", color="#347557")
    ax.text(1.20, 1.15, "Weaker in both", ha="left", va="bottom", fontsize=11.5, fontweight="bold", color="#657083")
    ax.text(8.80, 1.15, "Stronger automator", ha="right", va="bottom", fontsize=11.5, fontweight="bold", color="#bc642f")
    ax.text(4.85, 5.30, "Same in both roles", ha="center", va="bottom", fontsize=10.5, fontstyle="italic", color="#7a8496")

    ax.set_xlabel("Automation reverse rank →", fontsize=13.5, fontweight="bold", labelpad=20)
    ax.set_ylabel("← Augmentation reverse rank", fontsize=13.5, fontweight="bold", labelpad=20)
    ax.tick_params(axis="both", labelsize=11.5, colors="#657083", length=0, pad=8)
    for spine in ax.spines.values():
        spine.set_color("#d9dee7")
        spine.set_linewidth(0.9)

    fig.subplots_adjust(left=0.14, right=0.98, bottom=0.13, top=0.98)
    for output_dir in OUTPUT_DIRS:
        output_dir.mkdir(parents=True, exist_ok=True)
        for stem in ("figure2b_role_swap_scatter", "figure2b_role_swap_scatter_white"):
            fig.savefig(output_dir / f"{stem}.png", dpi=320, facecolor="white", bbox_inches="tight")
            fig.savefig(output_dir / f"{stem}.pdf", facecolor="white", bbox_inches="tight")
    plt.close(fig)

    print(df[["model", "automation_reverse", "augmentation_reverse", "gap"]].sort_values("automation_reverse").to_string(index=False))


def main() -> None:
    with DATA_PATH.open() as f:
        data = json.load(f)
    draw(panel_average_ranks(data))


if __name__ == "__main__":
    main()
