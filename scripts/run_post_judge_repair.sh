#!/usr/bin/env bash
# Wait for judge repair, then health/validate/summarize/dashboard/figures.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a && source .env && set +a
export PYTHONPATH=src:scripts

RUNS=(
  20260629_public_rep4
  20260629_public_rep5
  20260629_public_rep6
  20260629_public_rep7
  20260629_public_rep8
  20260629_public_rep9
  20260629_public_rep10
)
LOG=results/logs/judge_repair_public_all.log
NOTE=results/logs/judge_repair_status.md

log() { echo "$*" | tee -a "$LOG"; }

if pgrep -f 'repair_panel_judges_direct.py' >/dev/null 2>&1; then
  log "Waiting for repair_panel_judges_direct.py to finish..."
  while pgrep -f 'repair_panel_judges_direct.py' >/dev/null 2>&1; do
    sleep 60
  done
fi

log "=== POST-REPAIR HEALTH ==="
RUN_ID_ARGS=()
for r in "${RUNS[@]}"; do
  RUN_ID_ARGS+=(--run-id "$r")
done
.venv/bin/python scripts/judge_health_report.py \
  "${RUN_ID_ARGS[@]}" \
  --csv-out results/logs/judge_health_public_all_repaired.csv \
  --json-out results/logs/judge_health_public_all_repaired.json \
  | tee -a "$LOG" || true

log "=== VALIDATE JUDGING ==="
for r in "${RUNS[@]}"; do
  .venv/bin/python scripts/validate_judging.py --run-id "$r" | tee -a "$LOG" || true
done

log "=== SUMMARIZE ALL ==="
for r in "${RUNS[@]}"; do
  .venv/bin/python -m centaur_benchmark.cli summarize-all --run "$r" | tee -a "$LOG" || true
done

log "=== DASHBOARD + FIGURES ==="
.venv/bin/python scripts/build_dashboard_data.py | tee -a "$LOG"
MPLCONFIGDIR=/private/tmp/mplconfig .venv/bin/python scripts/make_paper_figures.py | tee -a "$LOG"

python3 <<'PY' | tee "$NOTE"
import json
from pathlib import Path
import pandas as pd

p = Path("results/logs/judge_health_public_all_repaired.json")
if not p.exists():
    print("# Judge repair status\n\nHealth JSON missing.")
    raise SystemExit(0)
payload = json.loads(p.read_text())
df = pd.DataFrame(payload["rows"])
included = df.groupby("judge_label")["included_in_aggregate"].sum()
print("# Judge repair status\n")
print("## Included judge counts (task-mode cells)")
for label, n in included.sort_index().items():
    print(f"- {label}: {int(n)}/98")
print(f"\n- Total pairwise rows: {int(df['pairwise_rows'].sum())}")
below = df[df["parse_pass_rate"] < 0.9]
print(f"\n## Cells still below 0.9 parse threshold: {len(below)} judge instances")
if len(below):
    print(below.groupby(["run_id","task","mode","judge_label"]).size().head(30).to_string())
flags = payload.get("flags") or []
print(f"\n## Health flags: {len(flags)}")
for f in flags[:20]:
    print(f"- {f}")
dash = Path("dashboard/dashboard-data.json")
figs = Path("results/figures")
print("\n## Artifacts")
print(f"- dashboard-data.json: {'ok' if dash.is_file() else 'missing'}")
print(f"- paper figures dir: {'ok' if figs.is_dir() else 'missing'}")
PY

log "=== POST-REPAIR COMPLETE ==="
