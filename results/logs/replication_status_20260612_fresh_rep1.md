# Replication Status: 20260612_fresh_rep1

Generated on 2026-06-12.

## Current Decision

This run is now mechanically clean and ready for judging.

The previous generation blockers have been repaired. The final run contains 140 outputs across 7 tasks, 2 regimes, and 10 candidate rows per task/regime. The output audit reports zero missing rows, zero format stubs, zero short outputs, and zero hard truncation flags.

Several repairs were required before judging:

- `tax_prep / automation / GPT-5-Mini` needed an explicit `max_tokens=12000` GPT-5-Mini call. The 6000-token attempt produced a real answer but ended mid-fragment; the 12000-token attempt passed the output-quality audit.
- `meal_plan / automation / GPT-5-Mini` needed an explicit `max_tokens=6000` call.
- `counselling`, `travel_planning`, and `tutoring` GPT-5-Mini automation rows were visually checked and repaired where the original answer ended mid-list or mid-activity.
- `meal_plan / automation / DeepSeek-V3.1` needed an explicit DeepInfra route with `max_tokens=6000`; generic high/default caps produced empty or incomplete outputs.
- Closed Gemini `<think>...</think>` prefixes were stripped from automation outputs before judging.

## Quality Audit

Latest audit file:

`results/logs/audit_20260612_fresh_rep1_final_quality.json`

Audit summary:

- Total rows: 140
- Passing rows: 140
- Failing rows: 0

Previously failing or visibly incomplete rows, now fixed:

| Task | Mode | Model | Replicate | Issue |
|---|---|---:|---:|---|
| `tax_prep` | `automation` | `GPT-5-Mini` (`gpt-5-mini-2025-08-07`) | 0 | Fixed via `default_max12000`; final output length 12,172 chars |
| `meal_plan` | `automation` | `GPT-5-Mini` (`gpt-5-mini-2025-08-07`) | 0 | Fixed via `max_tokens=6000`; final output length 8,431 chars |
| `counselling` | `automation` | `GPT-5-Mini` (`gpt-5-mini-2025-08-07`) | 0 | Repaired after visible tail check; final output length 6,458 chars |
| `travel_planning` | `automation` | `GPT-5-Mini` (`gpt-5-mini-2025-08-07`) | 0 | Repaired after visible tail check; final output length 8,566 chars |
| `tutoring` | `automation` | `GPT-5-Mini` (`gpt-5-mini-2025-08-07`) | 0 | Repaired after visible tail check; final output length 5,703 chars |
| `meal_plan` | `automation` | `DeepSeek-V3.1` (`deepseek-ai/DeepSeek-V3.1`) | 0 | Fixed via exact DeepInfra route with `max_tokens=6000`; final output length 6,882 chars |

All rows now pass the audit, including the previously problematic DeepSeek meal-planning, DeepSeek tax-prep, and GPT-5-Mini long-form automation rows.

Additional visual tail sanity check:

- Hard failures: 0
- Remaining soft flags: only rows whose final character is markdown emphasis, a closing quote, or an emoji/no-period ending. These are complete answers, not truncations.

## Variability / Cache Check

Comparison file:

`results/logs/compare_v4_vs_20260612_fresh_rep1_after_gpt5_tax_fix.json`

Summary:

- Compared rows: 140
- Identical rows vs. v4: 0
- Missing rows vs. v4: 0
- Status: `ok=true`

This indicates the fresh replicate is not simply reusing the prior v4 artifacts.

Note: because this run has one replicate, within-run replicate variability is not meaningful. The meaningful check here is cross-run non-identity against `20260610_scaffold_strict_v4`.

## GPT-5-Mini Tax-Prep Repair

The GPT-5-Mini tax-prep issue appears to have been a token/service-routing interaction rather than a model-quality problem.

Observed behavior:

- GPT-5-Mini succeeds on other tasks in this run.
- GPT-5-Mini initially failed specifically on `tax_prep / automation`.
- Exception reports showed two failure patterns:
  - default route could fall into `openai_v2` and fail with `No key found for service 'openai_v2'`;
  - forced `openai` route returned empty outputs or proxy 500s.
- A default GPT-5-Mini call with `max_tokens=6000` produced a real but truncated answer.
- A default GPT-5-Mini call with `max_tokens=12000` produced a clean answer and was upserted.

Interpretation:

The long tax-prep automation prompt needs more output headroom than the generic GPT-5-Mini/default settings provide. The clean repair used `Model("gpt-5-mini-2025-08-07", max_tokens=12000)` through remote Expected Parrot execution.

## Recommended Analysis Path

Best next step:

1. Proceed to judging for `20260612_fresh_rep1`.
2. Keep the repair note in the appendix/logs for reproducibility.
3. If launching a third replication, ensure GPT-5-Mini tax-prep automation uses an explicit 12000-token repair/fallback path if the generic run fails.

## Useful Commands

Final audit:

```bash
PYTHONPATH=src:scripts .venv/bin/python scripts/audit_all_outputs.py \
  --run-id 20260612_fresh_rep1 \
  --json-out results/logs/audit_20260612_fresh_rep1_final_quality.json
```

Compare against v4:

```bash
PYTHONPATH=src:scripts .venv/bin/python scripts/compare_rep_runs.py \
  --base-run-id 20260610_scaffold_strict_v4 \
  --new-run-id 20260612_fresh_rep1 \
  --json-out results/logs/compare_v4_vs_20260612_fresh_rep1_after_gpt5_tax_fix.json
```

Successful GPT-5-Mini tax repair probe:

```bash
set -a; source .env; set +a
export CENTAUR_EDSL_REMOTE=1 EDSL_API_TIMEOUT=1800 REMOTE_PROXY_TIMEOUT=1800 EDSL_MAX_ATTEMPTS=8 PYTHONPATH=src:scripts
.venv/bin/python scripts/repair_gpt5_tax_token_probe.py
```
