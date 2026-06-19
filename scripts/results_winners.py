#!/usr/bin/env python3
"""Print the canonical per-task winners used in the Results section.

This reads the SAME source as the paper figures and the live dashboard
(``dashboard/dashboard-data.json``) and uses the same aggregation as
``make_paper_figures.py`` (mean rank across runs, all-candidates universe with
the baseline kept). Use it to keep the Results prose in lock-step with both the
figures and the dashboard's Replicate Summary.

Usage:
    python scripts/results_winners.py
"""
import make_paper_figures as m

# Internal column keys for the baseline (same GPT-3.5-Turbo system in both modes).
BASELINE_KEY = {"augmentation": "plain", "automation": "GPT-3.5-Turbo"}


def main():
    data = m.load_data()
    runs = [r.get("label") for r in data["meta"]["replicate_runs"]]
    print(f"Source: dashboard/dashboard-data.json | runs: {runs}")
    print("Universe: all candidates (baseline kept) | metric: mean rank across runs, lower = best\n")

    for mode in ("automation", "augmentation"):
        mean, _, _ = m.mean_rank_matrix(data, mode)
        base = BASELINE_KEY[mode]
        print(f"=== {mode.upper()} ===")
        for task in mean.index:
            s = mean.loc[task].sort_values()
            winner = m.display_model_label(s.index[0])
            wrank = round(float(s.iloc[0]), 2)
            note = ""
            if s.index[0] == base:
                focal = s.drop(index=base, errors="ignore")
                note = (f"  [baseline wins; best assistant = "
                        f"{m.display_model_label(focal.index[0])} ({round(float(focal.iloc[0]), 2)})]")
            # Flag near-ties at the top (within 0.05 rank).
            if len(s) > 1 and abs(float(s.iloc[1]) - float(s.iloc[0])) < 0.05:
                note += f"  [TIE with {m.display_model_label(s.index[1])}]"
            print(f"  {task:<22} {winner:<24} ({wrank}){note}")
        print()


if __name__ == "__main__":
    main()
