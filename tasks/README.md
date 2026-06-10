# Task definitions (`tasks/*.yaml`)

Each file defines one benchmark task:

| Field | Meaning |
|-------|---------|
| `slug` | Directory name under `results/` / `artifacts/` |
| `task_prompt` | Worker-facing task text |
| `scaffold_prompt_template` | Assistant instruction (process-only scaffold) |
| `worker_instruction` | System instruction for the worker under augmentation |
| `automation_worker_instruction` | Shorter instruction when a model solves the task alone |
| `pairwise_task_context` | Text shown to the judge as “the request” |
| `pairwise_eval_prompt` | Judge agent instruction for JSON pairwise choice, rubric scores, averages, and rationale |
| `models.assistants` | Map of `model_id: display_label` for scaffold generators |
| `models.automation` | Map of models that run the task end-to-end (`null` to skip) |
| `models.evaluators` | Map of evaluator models used for multi-judge panel evaluation |
| `pairwise.n_evals_per_pair` | Repeated blind judgments per pair |
| `pairwise.n_outer_runs` | Repeat full tournament N times (stability; counselling uses 5) |
| `rubric_prompt` | Optional free-text rubric block for `centaur-benchmark rubric` |

Regenerate YAML from edited legacy notebooks:

```bash
python3 scripts/build_task_yamls.py
```

See also [Adding a new task](../docs/ADDING_A_TASK.md).
