# Working Token Policy: 20260612_fresh_rep1

Generated on 2026-06-12 after repairing generation failures in `20260612_fresh_rep1`.

## Summary

The clean run uses task-level and model-level token caps rather than a single global value. A global `128000` request can trigger Expected Parrot/provider failures for some models, while omitting `max_tokens` for GPT-5-Mini can produce empty outputs or short format stubs on longer structured tasks.

Final audit after repairs:

- Audit file: `results/logs/audit_20260612_fresh_rep1_final_quality.json`
- Rows: 140
- Passing rows: 140
- Failing rows: 0
- Strict tail sanity check: 0 hard failures. Remaining soft no-period endings were complete closings, markdown emphasis, or emoji endings rather than truncations.

## Automation Token Policy

| Model / scope | Working `max_tokens` policy | Notes |
|---|---:|---|
| `gpt-3.5-turbo` | 4,096 | EP/provider hard limit; higher values caused failures. |
| `gpt-4.1` | 32,768 | EP/provider hard limit; `128000` caused HTTP 500. |
| `gpt-5-mini-2025-08-07`, `counselling` automation | 12,000 | Remote 6k could still end mid-list; 12k produced a visually complete answer. |
| `gpt-5-mini-2025-08-07`, `meal_plan` automation | 6,000 | Default/omitted failed; 6k produced a clean full meal plan. |
| `gpt-5-mini-2025-08-07`, `tax_prep` automation | 12,000 | 6k produced a real but truncated answer; 12k passed. |
| `gpt-5-mini-2025-08-07`, `travel_planning` automation | 8,000 | Default/omitted output ended mid-itinerary; 8k passed visual check. |
| `gpt-5-mini-2025-08-07`, `tutoring` automation | 8,000 | Default/omitted output ended mid-activity; 8k passed visual check. |
| `gpt-5-mini-2025-08-07`, other automation tasks | omit | Default worked for market trends and OR. |
| `google/gemini-3.1-pro` | 65,536 provider cap | EP rejects `128000`; task cap may lower this further. |
| `deepseek-ai/DeepSeek-V3.1`, `meal_plan` automation | 6,000 | Generic high/default caps failed or truncated; explicit DeepInfra 6k passed. |
| `deepseek-ai/DeepSeek-V3.1`, other tasks | 128,000 provider cap | Task cap may lower this; some rows required retry/manual repair. |
| `o4-mini-2025-04-16` | 128,000 provider cap | Task cap may lower this. |
| `o3-mini-2025-01-31` | 128,000 provider cap | Task cap may lower this. |
| `openai/gpt-oss-120b` | 128,000 provider cap | Task cap may lower this. |
| `anthropic/claude-sonnet-4-6` | 128,000 provider cap | Task cap may lower this. |
| `anthropic/claude-opus-4-8` | 128,000 provider cap | Task cap may lower this. |

Task-level request caps in `src/centaur_benchmark/runner.py`:

| Task | Task cap |
|---|---:|
| `counselling` | 16,384 |
| `market_trends` | 16,384 |
| `tutoring` | 16,384 |
| `operations_research` | 24,576 |
| `travel_planning` | 32,768 |
| `meal_plan` | 32,768 |
| `tax_prep` | 65,536 |

Effective cap for non-GPT-5 models is `min(yaml automation_model_max_tokens, provider cap, task cap)`.

## Scaffold And Augmentation Worker Policy

| Role | Working policy |
|---|---|
| Scaffold generation | `scaffold_model_max_tokens: 700` in all task YAML files. |
| Augmentation worker (`gpt-3.5-turbo`) | Omit `max_tokens`; model default worked for this run. |

## Repairs Applied

| Row | Initial issue | Successful repair |
|---|---|---|
| `meal_plan / automation / GPT-5-Mini` | Empty output or visibly truncated meal plan under default settings. | `Model("gpt-5-mini-2025-08-07", max_tokens=6000)` |
| `tax_prep / automation / GPT-5-Mini` | Empty output under default settings; `max_tokens=6000` truncated. | `Model("gpt-5-mini-2025-08-07", max_tokens=12000)` |
| `counselling / automation / GPT-5-Mini` | Default/6k output could end mid-list. | `Model("gpt-5-mini-2025-08-07", max_tokens=12000)` was accepted in remote repair; local 6k later also produced a complete row. |
| `travel_planning / automation / GPT-5-Mini` | Default output ended mid-itinerary. | `Model("gpt-5-mini-2025-08-07", max_tokens=8000)` |
| `tutoring / automation / GPT-5-Mini` | Default output ended mid-activity setup. | `Model("gpt-5-mini-2025-08-07", max_tokens=8000)` |
| `meal_plan / automation / DeepSeek-V3.1` | Empty output/proxy failure or incomplete day-7 table. | `Model("deepseek-ai/DeepSeek-V3.1", service_name="deep_infra", max_tokens=6000)` |
| `tax_prep / automation / DeepSeek-V3.1` | Empty output/proxy failure. | Manual repair produced a clean 9,113-character output. |
| `travel_planning / automation / DeepSeek-V3.1` | Empty output/proxy failure. | Manual repair produced a clean 7,433-character output. |
| `tutoring / automation / DeepSeek-V3.1` | Initial hard truncation/empty retry. | Later repair produced a clean 5,011-character output. |

## Reuse Guidance

For future replications, keep the current `runner.py` policy. If GPT-5-Mini fails on a long automation task, first retry with an explicit task-specific `max_tokens` large enough for the expected deliverable before treating the row as a model failure.
