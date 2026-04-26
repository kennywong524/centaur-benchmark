"""Copy summaries to artifacts/ and optional bar plots."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from centaur_benchmark.io import repo_root, results_base


def export_run_artifacts(
    task_slug: str,
    run_id: str,
    *,
    dest: Path | None = None,
    plot: bool = True,
) -> Path:
    """
    Copy leaderboard CSVs from results/<task>/<run>/ to artifacts/<task>/<run>/.
    If plot=True, write simple bar charts when leaderboard exists.
    """
    run_src = results_base() / task_slug / run_id
    if not run_src.is_dir():
        raise FileNotFoundError(f"No such run directory: {run_src}")

    dest = dest or (repo_root() / "artifacts" / task_slug / run_id)
    dest.mkdir(parents=True, exist_ok=True)

    for mode in ("augmentation", "automation"):
        lb = run_src / mode / "leaderboard.csv"
        if lb.exists():
            shutil.copy2(lb, dest / f"leaderboard_{mode}.csv")
            if plot:
                _plot_leaderboard(lb, dest / f"win_rate_{mode}.png", title=f"{task_slug} / {run_id} / {mode}")

    # Optional ranked outputs (smaller than raw outputs)
    for mode in ("augmentation", "automation"):
        rk = run_src / mode / "pairwise_ranked.csv"
        if rk.exists():
            shutil.copy2(rk, dest / f"pairwise_ranked_{mode}.csv")

    (dest / "README.txt").write_text(
        f"Exported from results/{task_slug}/{run_id}/\n"
        "Leaderboards and ranked CSVs are suitable to commit; raw outputs stay in results/.\n",
        encoding="utf-8",
    )
    print(f"Artifacts written to {dest}")
    return dest


def _plot_leaderboard(csv_path: Path, png_path: Path, title: str) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    df = pd.read_csv(csv_path)
    if df.empty:
        return
    col = "avg_win_rate" if "avg_win_rate" in df.columns else None
    if not col:
        return
    label_col = "model_label" if "model_label" in df.columns else "model_id"
    plot_df = df.sort_values(col, ascending=False).head(20)
    plt.figure(figsize=(10, max(3, 0.35 * len(plot_df))))
    sns.barplot(data=plot_df, x=col, y=label_col, color="#4C72B0")
    plt.title(title)
    plt.xlabel(col)
    plt.ylabel("")
    plt.tight_layout()
    png_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(png_path, dpi=150)
    plt.close()
