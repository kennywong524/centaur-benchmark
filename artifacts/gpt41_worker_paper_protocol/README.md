# GPT-4.1 worker experiment — published evaluation protocol

Experiment ID: `20260928_gpt41_worker_paper_protocol`.

This is a seven-task, one-run augmentation experiment with GPT-4.1 as the fixed worker. Each task has nine assistant-guidance conditions and one unassisted GPT-4.1 condition. Guidance is reused from the tracked `20260610_scaffold_strict_v4` experiment. Final worker outputs are from the September GPT-4.1 pilots; no date context was added.

## Evaluation rule

The judge panel is GPT-4.1, Claude Opus 4.8, Gemini 3.1 Pro, and DeepSeek V3.1. Eligibility follows the original GPT-3.5 Turbo augmentation implementation: mask the judge if its provider family matches either candidate's **assistant family**. The fixed worker's family is not included in the mask. Under that original implementation, OpenAI judgments are eligible for pairs among non-OpenAI assistance conditions and the plain condition.

Travel planning reuses its ten already-saved OpenAI judgments. The other six tasks add only their ten missing eligible OpenAI judgments each. All worker outputs and other judges' responses are reused. Final per-task records are in `results/<task>/20260928_gpt41_worker_paper_protocol/`.

## Rankings and figures

Per-judge wins are converted into win rates and judge-specific ranks. The original implementation's aggregate leaderboard sorts average eligible-judge **win rates**, while also retaining average judge ranks as a separate diagnostic column. These results use that original aggregate-rank calculation for consistency with the published tables. `n_judges` counts judges with an actual score, excluding masked/missing entries.

- `augmentation_all_tasks.csv`: all new augmentation leaderboard values.
- `augmentation_task_ranks_and_average.csv`: task ranks and their average across seven tasks.
- `augmentation_heatmap_ranks.csv`: displayed rank-of-ranks heatmap values.
- `automation_published_mean_task_ranks.csv`: the existing published automation results, averaged over ten runs.
- `automation_heatmap_ranks.csv`: displayed published automation heatmap values.
- `gpt41_worker_augmentation_paper_protocol.{png,pdf}`: new augmentation heatmap.
- `automation_published_reference.{png,pdf}`: reused published automation heatmap.

Each task heatmap row uses the published figure renderer's ordering, including its deterministic tie handling. Each Average heatmap row ranks the average of the seven task ranks. Automation was not regenerated or rejudged. Its baseline is unassisted GPT-3.5 Turbo, as in the original automation benchmark; the new augmentation baseline is unassisted GPT-4.1. Compare modes on the nine shared assistant models. Automation has ten runs; this new augmentation experiment has one run per task, so no augmentation standard error is estimated.

## Reproduce

From the repository root, use a compatible EDSL 1.0.8 environment with the existing provider credentials:

```bash
PYTHONPATH=tmp/edsl-1.0.8:src .venv/bin/python scripts/finalize_gpt41_paper_protocol.py
```

When the saved OpenAI judgments are present, this only re-aggregates saved results and renders figures. `--execute-missing` permits generating eligible OpenAI comparisons that are missing. Completed final experiment files are sufficient for offline reproduction; initial finalization uses the source pilot paths recorded in the manifests.

The earlier `gpt41_worker_pilot` figures and `strict_leave_family_out` results excluded the worker's family too. They are retained as a separate sensitivity analysis and should not be confused with this primary, paper-consistent experiment.
