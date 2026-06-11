# Task definitions (`tasks/*.yaml`)

Each file defines one benchmark task.

## Stable frontier model set (`20260609_stable_frontier_v2`)

All seven tasks share the same assistant, automation, and evaluator lists (see any `tasks/*.yaml`). Key IDs:

| Role | Model IDs |
|------|-----------|
| Worker | `gpt-3.5-turbo` |
| Assistants / automation | `gpt-4.1`, `gpt-5-mini-2025-08-07`, `deepseek-ai/DeepSeek-V3.1`, `o4-mini-2025-04-16`, `o3-mini-2025-01-31`, `openai/gpt-oss-120b`, `anthropic/claude-sonnet-4-6`, `anthropic/claude-opus-4-8`, `google/gemini-3.1-pro` |
| Evaluators | `gpt-4.1`, `anthropic/claude-opus-4-8`, `google/gemini-3.1-pro`, `deepseek-ai/DeepSeek-V3.1` |

`gpt-5-pro` was replaced with **`gpt-5-mini-2025-08-07`** (label `GPT-5-Mini`) after format-stub failures on long prompts.

Token limits:

| Role | `max_tokens` |
|------|----------------|
| Scaffold generation | `700` on all tasks (process-only; keep short) |
| Augmentation worker (`gpt-3.5-turbo`) | **omitted** — use model default |
| Automation (frontier models) | **omitted** — use model default |

Optional overrides: `scaffold_model_max_tokens`, `worker_model_max_tokens`, `automation_model_max_tokens` in YAML only if you need an explicit cap.

## YAML fields

| Field | Meaning |
|-------|---------|
| `slug` | Directory name under `results/` / `artifacts/` |
| `task_prompt` | Worker-facing task text |
| `scaffold_prompt_template` | Assistant instruction (process-only scaffold) |
| `worker_instruction` | System instruction for the worker under augmentation |
| `automation_worker_instruction` | Shorter instruction when a model solves the task alone |
| `scaffold_model_max_tokens` | Optional cap for scaffold generation (default: omitted except YAML `700`) |
| `worker_model_max_tokens` | Optional cap for augmentation worker (default: omitted) |
| `automation_model_max_tokens` | Optional cap for automation runs (default: omitted) |
| `pairwise_task_context` | Text shown to the judge as “the request” |
| `pairwise_eval_prompt` | Judge agent instruction for JSON pairwise choice, rubric scores, averages, and rationale |
| `models.assistants` | Map of `model_id: display_label` for scaffold generators |
| `models.automation` | Map of models that run the task end-to-end (`null` to skip) |
| `models.evaluators` | Map of evaluator models used for multi-judge panel evaluation |
| `pairwise.n_evals_per_pair` | Repeated blind judgments per pair (default 3; committed run used 1 via CLI override) |
| `pairwise.n_outer_runs` | Repeat full tournament N times (stability; counselling uses 5) |
| `replicates` | Output replicates per model (`meal_plan`: 3; others: 1) |
| `rubric_prompt` | Optional free-text rubric block for `centaur-benchmark rubric` |

## Regenerate from legacy notebooks

```bash
python3 scripts/build_task_yamls.py
```

See also [Adding a new task](../docs/ADDING_A_TASK.md) and the [main pipeline README](../README.md#reproducing-the-stable-frontier-run-20260609_stable_frontier_v2).
