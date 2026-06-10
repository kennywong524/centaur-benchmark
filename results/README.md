# Results (raw runs)

This directory is **gitignored by default** except the published reference run below, which is force-tracked for reproducibility.

## Committed reference run: `20260609_stable_frontier_v2`

Per task (`counselling`, `market_trends`, `meal_plan`, `operations_research`, `tax_prep`, `travel_planning`, `tutoring`):

```
results/<task>/20260609_stable_frontier_v2/
  augmentation/
    outputs.csv
    scaffolds/*.md
    scaffolds.csv
    pairwise_judgments_*.csv
    leaderboard_*.csv
    rubric_scores_*.csv
    judge_validation.json
  automation/
    outputs.csv
    (same judge artifacts)
  config.json
```

Run-level files at `results/`:

- `audit_20260609_stable_frontier_v2.json`
- `judging_notes_20260609_stable_frontier_v2.md`
- `judge_validation_20260609_stable_frontier_v2.json`
- `logs/judge_*.log`

Cross-task heatmaps and matrices: [`artifacts/cross_task/20260609_stable_frontier_v2/`](../artifacts/cross_task/20260609_stable_frontier_v2/).

Drive handoff bundle (xlsx, zip, html): [`artifacts/drive_handoff/20260609_stable_frontier_v2/`](../artifacts/drive_handoff/20260609_stable_frontier_v2/).

## Not committed

Other run ids under `results/` (e.g. `20260609_final_prompts`, `20260609_stable_frontier`) are local-only and remain gitignored.
