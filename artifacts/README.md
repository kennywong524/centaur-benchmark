# Artifacts

This directory holds **small, publishable** outputs copied or exported from `results/`.

Raw model outputs, pairwise judgment dumps, and per-task leaderboards stay under `results/` (gitignored) unless you choose to commit them.

## Cross-task run: `20260609_stable_frontier_v2`

The reference stable-frontier run is in [`cross_task/20260609_stable_frontier_v2/`](cross_task/20260609_stable_frontier_v2/).

| File pattern | Meaning |
|--------------|---------|
| `rank_matrix_*_aggregate.csv` | Panel-aggregated ranks across judges (lower = better) |
| `rank_matrix_*_<judge>.csv` | Per-judge ranks |
| `win_rate_matrix_*` | Same structure, win rates instead of ranks |
| `rank_heatmap_*.png` | Visual heatmaps (augmentation vs automation, per judge) |
| `all_leaderboards_long.csv` | Combined aggregate leaderboards, all tasks |
| `all_leaderboards_by_judge_long.csv` | Per-judge leaderboards, all tasks |

### Reproduce these artifacts

From the repo root (see [main README](../README.md) for full setup):

```bash
set -a && source .env && set +a
export PYTHONPATH=src CENTAUR_EDSL_REMOTE=0

# Requires completed judging for run id 20260609_stable_frontier_v2
.venv/bin/python scripts/run_full_pipeline.py \
  --run-id 20260609_stable_frontier_v2 \
  --mode summarize
```

Output directory: `artifacts/cross_task/20260609_stable_frontier_v2/`.

Validation before summarize:

```bash
.venv/bin/python scripts/validate_judging.py --run-id 20260609_stable_frontier_v2
```

Expect `ready_for_summarize=true` and 14 complete task/mode folders.

## Drive handoff bundle

[`drive_handoff/20260609_stable_frontier_v2/`](drive_handoff/20260609_stable_frontier_v2/) contains an xlsx workbook, full zip of raw results, navigation HTML, and judging notes for sharing outside the repo.

Raw per-task CSVs and scaffolds live under [`results/`](../results/) (same run id).

## Per-task artifacts (CLI)

For a single task via the CLI:

```bash
centaur-benchmark summarize --task meal_plan --run <RUN_ID>
```

Copies leaderboards into `artifacts/<task>/<run>/` and writes bar charts.
