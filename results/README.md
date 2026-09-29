# Results (raw runs)

## GPT-4.1 worker experiment: published evaluation protocol

The new September worker experiment is stored under `results/<task>/20260928_gpt41_worker_paper_protocol/` for all seven tasks. It reuses saved assistant guidance and the GPT-4.1 pilot deliverables, with one run per task. Evaluation matches the original GPT-3.5 Turbo augmentation implementation: a four-judge panel and assistant-family-only masking, without masking the fixed worker's family. The existing automation results are reused.

See [`artifacts/gpt41_worker_paper_protocol/README.md`](../artifacts/gpt41_worker_paper_protocol/README.md) for the protocol, source runs, ranking calculation, automation/augmentation comparison, and reproduction instructions. The earlier strict-worker-family-mask pilot is a separate sensitivity analysis.

This directory is **gitignored by default** except the published reference/current runs below, which are force-tracked for reproducibility.

## Current clean run: `20260610_scaffold_strict_v4`

Use this run for current dashboard analysis and paper-facing results. It is the cleaned v4 run after the scaffold-generation bug was fixed: augmentation scaffolds were regenerated with the stricter process-only schema, audited before judging, and then judged with the panel pipeline.

Per task (`counselling`, `market_trends`, `meal_plan`, `operations_research`, `tax_prep`, `travel_planning`, `tutoring`):

```
results/<task>/20260610_scaffold_strict_v4/
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
    pairwise_judgments_*.csv
    leaderboard_*.csv
    rubric_scores_*.csv
    judge_validation.json
  config.json
```

Cross-task matrices and dashboard-ready judge agreement artifacts are in [`artifacts/cross_task/20260610_scaffold_strict_v4/`](../artifacts/cross_task/20260610_scaffold_strict_v4/).

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
