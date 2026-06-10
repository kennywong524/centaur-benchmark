# Centaur benchmark (reproducible harness)

Simulation benchmark for **automation** (model solves the task) vs **augmentation** (assistant produces a process-only scaffold, then a fixed worker produces the deliverable), with **panel pairwise LLM judging** and optional **rubric** grading. Built on [Expected Parrot / EDSL](https://www.expectedparrot.com/getting-started) ([docs](https://docs.expectedparrot.com/en/latest)).

This repo refactors Colab notebooks into:

- **Task configs** under [`tasks/`](tasks/) (prompts, scaffold template, judge instructions, model lists).
- **Pipeline scripts** under [`scripts/`](scripts/) for multi-task generation, audit, judging, and cross-task matrices.
- **One CLI** (`centaur-benchmark`) for single-task runs.
- **Clean directories**: raw runs → `results/` (gitignored); summary CSVs + heatmaps → [`artifacts/`](artifacts/) (committed when exported).

## Requirements

- **Python 3.10+** (EDSL on PyPI targets 3.10–3.12).
- Expected Parrot account with API credits ([Getting started](https://www.expectedparrot.com/getting-started)).
- Dependencies include `edsl`, `pandas`, `matplotlib`, and `seaborn` (see [`pyproject.toml`](pyproject.toml)).

## Install

```bash
cd centaur-benchmark-code
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

## Authenticate

Create a `.env` file in the repo root (gitignored):

```bash
EXPECTED_PARROT_API_KEY=your_key_here
EXPECTED_PARROT_URL=https://www.expectedparrot.com
```

Or log in via the CLI:

```bash
centaur-benchmark login
```

EDSL also stores a key at `~/Library/Application Support/edsl/ep_api_key.txt` on macOS. The pipeline loads `.env` automatically when you use `scripts/run_full_pipeline.py`.

### Execution mode (local proxy vs remote Jobs)

By default the harness runs **locally with the Expected Parrot API proxy** (`CENTAUR_EDSL_REMOTE=0`). This bills the account tied to your `EXPECTED_PARROT_API_KEY`.

To use **remote Expected Parrot Jobs** (where shared-key priority on the website may apply), set:

```bash
export CENTAUR_EDSL_REMOTE=1
```

and enable **Run surveys remotely** in your Expected Parrot account settings. The stable frontier run below used **local proxy**.

Recommended timeouts for long tasks:

```bash
export EDSL_API_TIMEOUT=600
export REMOTE_PROXY_TIMEOUT=600
export EDSL_MAX_ATTEMPTS=8
```

---

## Reproducing the stable frontier run (`20260609_stable_frontier_v2`)

This is the reference multi-task run committed in [`artifacts/cross_task/20260609_stable_frontier_v2/`](artifacts/cross_task/20260609_stable_frontier_v2/).

### What it covers

| Item | Value |
|------|--------|
| **Run ID** | `20260609_stable_frontier_v2` |
| **Tasks** | `counselling`, `market_trends`, `meal_plan`, `operations_research`, `tax_prep`, `travel_planning`, `tutoring` |
| **Worker** (augmentation) | `gpt-3.5-turbo` (plain baseline + scaffold conditions) |
| **Assistants** (scaffold) | GPT-4.1, GPT-5-Mini, DeepSeek-V3.1, GPT-O4-Mini, GPT-O3-Mini, GPT-OSS-120B, Claude-Sonnet-4.6, Claude-Opus-4.8, Gemini-3.1-Pro |
| **Automation models** | GPT-3.5-Turbo, GPT-4.1, GPT-5-Mini, DeepSeek-V3.1, GPT-O4-Mini, GPT-O3-Mini, GPT-OSS-120B, Claude-Sonnet-4.6, Claude-Opus-4.8, Gemini-3.1-Pro |
| **Judge panel** | GPT-4.1, Claude-Opus-4.8, Gemini-3.1-Pro, DeepSeek-V3.1 |
| **Leave-one-family-out** | On (OpenAI judge skips OpenAI outputs, etc.) |
| **Pairwise replicates** | `n_evals=1` for the committed run (YAML default is 3) |
| **Replicates** | 1 per model (except `meal_plan`: 3) |

Model IDs and token limits live in each [`tasks/*.yaml`](tasks/). Notable overrides: `tax_prep` uses `scaffold_model_max_tokens: 6000` and `automation_model_max_tokens: 6000`; `meal_plan` uses 4096 for both.

### Full pipeline (generation → judge → summarize)

From the repo root, with `.env` loaded:

```bash
set -a && source .env && set +a
export CENTAUR_EDSL_REMOTE=0
export EDSL_API_TIMEOUT=600 REMOTE_PROXY_TIMEOUT=600 EDSL_MAX_ATTEMPTS=8
export PYTHONPATH=src

RUN_ID=20260609_stable_frontier_v2

# 1) Generate augmentation + automation outputs for all tasks
.venv/bin/python scripts/run_full_pipeline.py \
  --run-id "$RUN_ID" \
  --mode generation

# 2) Audit before judging (outputs + scaffolds, min 250 chars)
.venv/bin/python scripts/audit_run.py \
  --run-id "$RUN_ID" \
  --min-chars 250

# 3) Retry any failed rows reported by the audit (optional)
.venv/bin/python scripts/retry_failed.py --run-id "$RUN_ID" --min-chars 250

# Re-audit until ready_for_judging=true and failures=0

# 4) Panel judging (use --n-evals 1 for a cheaper first pass; 3 matches task YAML defaults)
.venv/bin/python scripts/run_full_pipeline.py \
  --run-id "$RUN_ID" \
  --mode judge \
  --n-evals 1

# 5) Cross-task rank / win-rate matrices + heatmaps
.venv/bin/python scripts/run_full_pipeline.py \
  --run-id "$RUN_ID" \
  --mode summarize
```

Or run everything in one shot (after a clean audit):

```bash
.venv/bin/python scripts/run_full_pipeline.py \
  --run-id 20260609_stable_frontier_v2 \
  --mode all \
  --n-evals 1
```

### Smoke-test a single task

```bash
.venv/bin/python scripts/run_full_pipeline.py \
  --run-id 20260609_stable_frontier_v2 \
  --mode judge \
  --tasks counselling \
  --only-mode automation \
  --n-evals 1
```

### Audit and validation

| Script | Purpose |
|--------|---------|
| [`scripts/audit_run.py`](scripts/audit_run.py) | Checks missing models, empty/short outputs, format stubs, bad scaffolds. Writes `results/audit_<run_id>.json`. |
| [`scripts/retry_failed.py`](scripts/retry_failed.py) | Re-runs failed model rows from the audit report. |
| [`scripts/validate_judging.py`](scripts/validate_judging.py) | Confirms all judge artifact CSVs exist; writes `results/judging_notes_<run_id>.md`. |

Judging is blocked if the audit reports `ready_for_judging=false`.

### Patching specific models

If only some assistant/automation rows are bad, regenerate them without re-running the full task:

```python
from centaur_benchmark.config import load_task
from centaur_benchmark.io import ensure_run_dir
from centaur_benchmark.runner import patch_augmentation_models, patch_automation_models

run_id = "20260609_stable_frontier_v2"
task = load_task("tasks/tax_prep.yaml")
root = ensure_run_dir(task.slug, run_id)

patch_automation_models(task, root, ["o3-mini-2025-01-31"])
patch_augmentation_models(task, root, ["gpt-5-mini-2025-08-07"])
```

Re-audit, then **delete judge CSVs** for any patched task/mode before re-judging (pairwise rankings depend on exact outputs).

### Where outputs go

**Per task** (`results/<task>/<run_id>/`):

| Path | Contents |
|------|----------|
| `augmentation/outputs.csv` | Worker outputs (plain + per-assistant scaffold) |
| `augmentation/scaffolds/*.md` | One scaffold file per assistant |
| `automation/outputs.csv` | End-to-end model outputs |
| `augmentation/` or `automation/` judge CSVs | `pairwise_judgments_<Judge>.csv`, `leaderboard_aggregate.csv`, `rubric_scores_*.csv`, etc. |

**Run-level**:

- `results/audit_<run_id>.json`
- `results/judging_notes_<run_id>.md`
- `results/judge_validation_<run_id>.json`

**Published cross-task artifacts** (committed):

- [`artifacts/cross_task/20260609_stable_frontier_v2/`](artifacts/cross_task/20260609_stable_frontier_v2/) — rank/win-rate matrices and heatmaps per judge + aggregate.

### Judge panel behavior

- Four LLM judges per task; **leave-one-family-out** filters pairs where the judge would compare its own model family (see `judge_pairwise.py`).
- Judges return strict JSON with per-dimension 1–10 rubric scores; validation excludes judges with low parse pass rates from aggregates.
- In the committed run, **Gemini-3.1-Pro** was excluded from aggregate leaderboards on most tasks due to rubric JSON parse failures; GPT-4.1, Claude-Opus-4.8, and DeepSeek-V3.1 drove aggregate rankings. See `results/judging_notes_20260609_stable_frontier_v2.md` after judging.

### Cost note

Panel judging across 7 tasks × 2 modes × 4 judges is API-intensive. A practical order: audit → `n_evals=1` judge pass → check burn rate → optionally re-run with `n_evals=3`.

---

## Single-task CLI (alternative)

For one task at a time:

```bash
# Generation
centaur-benchmark run --task meal_plan --mode all --run-id my_run_01

# Pairwise judge (single evaluator)
centaur-benchmark judge --task meal_plan --run my_run_01 --subset both --eval-model gpt-4.1 --n-evals 3

# Per-task artifact export
centaur-benchmark summarize --task meal_plan --run my_run_01
```

The multi-task pipeline in `scripts/run_full_pipeline.py` uses **panel judging** and **cross-task matrices**; the CLI uses the older single-judge paths unless you call the Python API directly.

## Optional rubric grading

If `rubric_prompt` is set in the task YAML:

```bash
centaur-benchmark rubric --task meal_plan --run <RUN_ID> --subset augmentation
```

Pairwise judging already embeds rubric scores in `rubric_scores_long.csv` / `rubric_scores_summary.csv`.

## Repo layout

| Path | Purpose |
|------|---------|
| [`src/centaur_benchmark/`](src/centaur_benchmark/) | Runner, panel judge, summarize, EDSL runtime |
| [`tasks/*.yaml`](tasks/) | Per-task prompts + model lists |
| [`scripts/`](scripts/) | `run_full_pipeline.py`, `audit_run.py`, `retry_failed.py`, `validate_judging.py` |
| [`artifacts/cross_task/`](artifacts/cross_task/) | Committed cross-task matrices / heatmaps |
| [`notebooks/legacy/`](notebooks/legacy/) | Stripped Colab exports (reference) |
| [`docs/ADDING_A_TASK.md`](docs/ADDING_A_TASK.md) | How to add a new task |

## Citation

If you use this benchmark, cite the working paper *Centaur Benchmarking* (Haas / UC Berkeley) and [Expected Parrot / EDSL](https://www.expectedparrot.com/getting-started).
