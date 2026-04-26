# Centaur benchmark (reproducible harness)

Simulation benchmark for **automation** (model solves the task) vs **augmentation** (assistant produces a process-only scaffold, then a fixed worker produces the deliverable), with **pairwise LLM judging** and optional **rubric** grading. Built on [Expected Parrot / EDSL](https://www.expectedparrot.com/getting-started) ([docs](https://docs.expectedparrot.com/en/latest)).

This repo refactors Colab notebooks into:

- **Task configs** under [`tasks/`](tasks/) (prompts, scaffold template, judge instructions, model lists).
- **One CLI** to run, judge, and export artifacts.
- **Clean directories**: raw runs → `results/` (gitignored); figures + summary CSVs → [`artifacts/`](artifacts/) (committed when you export).

## Requirements

- **Python 3.10+** (EDSL on PyPI targets 3.10–3.12).
- Expected Parrot account / API setup per [Getting started](https://www.expectedparrot.com/getting-started).

## Install (editable)

```bash
cd centaur-benchmark-code
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

## Authenticate (terminal)

```bash
centaur-benchmark login
```

This runs `edsl.login()` so you can paste keys / complete the browser flow from the terminal (same as `from edsl import login; login()` in Colab).

## Run an experiment

```bash
# Full factorial: plain worker + each assistant scaffold; then each model automating the task
centaur-benchmark run --task meal_plan --mode all

# Only augmentation, subset of assistants (comma-separated model ids)
centaur-benchmark run --task counselling --mode augmentation --assistants gpt-4.1,deepseek-ai/DeepSeek-V3.1

# Custom run id (otherwise auto: UTC + short uuid)
centaur-benchmark run --task meal_plan --mode augmentation --run-id my_run_01
```

Outputs:

- `results/<task_slug>/<run_id>/config.json`
- `results/<task_slug>/<run_id>/augmentation/outputs.csv`
- `results/<task_slug>/<run_id>/automation/outputs.csv` (if automation ran)

## Judge (pairwise)

```bash
centaur-benchmark judge --task meal_plan --run <RUN_ID> --subset both --eval-model gpt-5 --n-evals 3
```

For tasks with repeated tournaments (e.g. counselling), the YAML sets `pairwise.n_outer_runs`; override with `--n-outer-runs`.

## Optional rubric grading

If `rubric_prompt` is set in the task YAML:

```bash
centaur-benchmark rubric --task meal_plan --run <RUN_ID> --subset augmentation
```

## Export paper-ready artifacts

```bash
centaur-benchmark summarize --task meal_plan --run <RUN_ID>
# optional: --to path/to/dir   --no-plot
```

Copies leaderboards / ranked CSVs into `artifacts/<task>/<run>/` and writes bar charts.

## Legacy folders (optional cleanup)

The original per-task directories (`menu planning/`, `counselling/`, etc.) are kept for reference alongside `*-result/` outputs. The canonical runnable copies live in [`notebooks/legacy/`](notebooks/legacy/) (stripped outputs) and [`tasks/*.yaml`](tasks/). Once you are confident nothing is missing, you may delete the old folders to reduce clutter.

## Repo layout

| Path | Purpose |
|------|---------|
| [`src/centaur_benchmark/`](src/centaur_benchmark/) | Runner, pairwise judge, CLI |
| [`tasks/*.yaml`](tasks/) | Per-task prompts + model lists |
| [`notebooks/legacy/`](notebooks/legacy/) | Stripped Colab exports (reference only) |
| [`notebooks/01_run_task.ipynb`](notebooks/01_run_task.ipynb) | Thin wrapper calling the CLI |
| [`scripts/build_task_yamls.py`](scripts/build_task_yamls.py) | Regenerate YAML from legacy notebooks if you edit them |
| [`docs/ADDING_A_TASK.md`](docs/ADDING_A_TASK.md) | How to add a new task |

## GitHub

```bash
git init
git add .
git commit -m "Initial centaur-benchmark harness"
# create repo on GitHub, then:
git remote add origin https://github.com/<you>/centaur-benchmark.git
git push -u origin main
```

## Citation

If you use this benchmark, cite the working paper *Centaur Benchmarking* (Haas / UC Berkeley) and [Expected Parrot / EDSL](https://www.expectedparrot.com/getting-started).
