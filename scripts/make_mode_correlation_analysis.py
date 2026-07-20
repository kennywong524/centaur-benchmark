#!/usr/bin/env python3
"""Compute automation--augmentation rank correlations from ten-run summaries."""

from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "artifacts" / "cross_task" / "ten_run_summary" / "model_task_mode_summary_10_runs.csv"
OUT = ROOT / "artifacts" / "cross_task" / "ten_run_summary"
TEX_OUT = ROOT / "artifacts" / "paper_figures" / "table_mode_correlations.tex"

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
    data = pd.read_csv(INPUT)
    assistants = data[~data["model_label"].isin(["plain", "GPT-3.5-Turbo"])].copy()
    wide = (
        assistants.pivot_table(
            index=["task_slug", "model_label"], columns="mode", values="mean_rank"
        )
        .dropna()
        .reset_index()
    )

    rows = []
    for task, group in wide.groupby("task_slug"):
        rho, p_value = spearmanr(group["automation"], group["augmentation"])
        rows.append(
            {
                "task_slug": task,
                "task": TASK_LABELS[task],
                "spearman_rho": rho,
                "p_value": p_value,
                "n_models": len(group),
            }
        )

    result = pd.DataFrame(rows).sort_values("spearman_rho", ascending=False)
    result.to_csv(OUT / "automation_augmentation_correlations_by_task_10_runs.csv", index=False)

    model_means = wide.groupby("model_label")[["automation", "augmentation"]].mean()
    overall_rho, overall_p = spearmanr(model_means["automation"], model_means["augmentation"])
    pd.DataFrame(
        [
            {
                "scope": "model averages across seven tasks",
                "spearman_rho": overall_rho,
                "p_value": overall_p,
                "n_models": len(model_means),
            }
        ]
    ).to_csv(OUT / "automation_augmentation_correlation_overall_10_runs.csv", index=False)

    lines = [
        r"\begin{table}[H]",
        r"    \centering",
        r"    \caption{Task-level association between automation and augmentation rankings. Spearman correlations are computed across the nine assistant models using each model's mean rank over ten runs. Positive values indicate similar cross-mode ordering; values near zero indicate little correspondence. $p$-values are descriptive because each task contains only nine models.}",
        r"    \label{tab:mode-correlations}",
        r"    \small",
        r"    \begin{tabular}{lrr}",
        r"        \toprule",
        r"        Task & Spearman $\rho_t$ & $p$-value \\",
        r"        \midrule",
    ]
    for row in result.itertuples():
        lines.append(f"        {row.task} & {row.spearman_rho:.2f} & {row.p_value:.3f} \\\\")
    lines.extend(
        [
            r"        \bottomrule",
            r"    \end{tabular}",
            r"\end{table}",
            "",
        ]
    )
    TEX_OUT.write_text("\n".join(lines))

    print(result.to_string(index=False))
    print(f"\nOverall: rho={overall_rho:.4f}, p={overall_p:.4f}, n={len(model_means)}")


if __name__ == "__main__":
    main()
