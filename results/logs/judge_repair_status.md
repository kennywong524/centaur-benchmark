# Judge repair status

## Included judge counts (task-mode cells)
- Claude-Opus-4.8: 98/98
- DeepSeek-V3.1: 98/98
- GPT-4.1: 98/98
- Gemini-3.1-Pro: 98/98

## Health flags
0 — none

## Pipeline
- **repair:** complete (98/98 cells, exit 0, ~8 hr direct Anthropic/Google)
- **validate:** complete (7/7 runs, `complete=14`, `ready_for_summarize=True`)
- **summarize:** complete (rep4–rep10 cross-task matrices)
- **dashboard + figures:** complete

## Artifacts
- `dashboard/dashboard-data.json`: ok
- `artifacts/paper_figures/`: ok
- `results/logs/judge_health_public_all_repaired.json`: ok

## Notes
- Post-repair shell script initially failed on health arg parsing and a summarize-line typo; both fixed in `scripts/run_post_judge_repair.sh`.
- A few cells had sub-perfect parse rates (e.g. tax_prep Claude ~0.93–0.96, Gemini ~0.97) but all remained above the 0.9 threshold and included in aggregates.
