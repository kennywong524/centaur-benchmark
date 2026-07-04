#!/usr/bin/env bash
# Judge all public replicate runs sequentially; health report after each run.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a && source .env && set +a
export PYTHONPATH=src:scripts
export CENTAUR_TOGETHER_SDK_ONLY=1

RUNS=(
  20260629_public_rep4
  20260629_public_rep5
  20260629_public_rep6
  20260629_public_rep7
  20260629_public_rep8
  20260629_public_rep9
  20260629_public_rep10
)

POOL_LOG=results/logs/judge_public_pool.log
mkdir -p results/logs

ensure_together() {
  local ep="${CENTAUR_TOGETHER_DEEPSEEK_ENDPOINT:-}"
  if [[ -z "$ep" ]]; then
    echo "CENTAUR_TOGETHER_DEEPSEEK_ENDPOINT unset; skipping Together start"
    return 0
  fi
  echo "=== Together endpoint start/wait: $ep ===" | tee -a "$POOL_LOG"
  PYTHONPATH=src .venv/bin/python scripts/together_deepseek_endpoint.py start "$ep" >>"$POOL_LOG" 2>&1 || true
  PYTHONPATH=src .venv/bin/python scripts/together_deepseek_endpoint.py wait "$ep" --timeout 1800 >>"$POOL_LOG" 2>&1
}

stop_together() {
  local ep="${CENTAUR_TOGETHER_DEEPSEEK_ENDPOINT:-}"
  if [[ -n "$ep" ]]; then
    echo "=== Together endpoint stop: $ep ===" | tee -a "$POOL_LOG"
    PYTHONPATH=src .venv/bin/python scripts/together_deepseek_endpoint.py stop "$ep" >>"$POOL_LOG" 2>&1 || true
  fi
}

judge_run() {
  local run_id="$1"
  local resume_flag=(--no-resume)
  if [[ "${JUDGE_RESUME:-0}" == "1" ]]; then
    resume_flag=()
  fi
  echo "=== JUDGE START $run_id $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$POOL_LOG"
  .venv/bin/python scripts/run_resumable_batch.py \
    --run-id "$run_id" \
    --phase judge \
    --n-evals 1 \
    "${resume_flag[@]}" \
    --verify \
    --continue-on-error \
    --max-step-failures 6 \
    --max-consecutive-failures 30 \
    2>&1 | tee "results/logs/judge_${run_id}.log"
  echo "=== HEALTH $run_id ===" | tee -a "$POOL_LOG"
  .venv/bin/python scripts/judge_health_report.py --run-id "$run_id" || true
  echo "=== JUDGE DONE $run_id $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$POOL_LOG"
}

ensure_together
trap stop_together EXIT

for run_id in "${RUNS[@]}"; do
  # Skip if already fully judged (all 14 task/mode validations present and checkpoint judge/notes done)
  if [[ "${JUDGE_FORCE:-0}" != "1" ]]; then
    done_steps=$(python3 - <<PY
import json
from pathlib import Path
p = Path("results/logs/batch_${run_id}.json")
if not p.exists():
    print(0)
    raise SystemExit
state = json.loads(p.read_text())
completed = [s for s in state.get("completed", []) if s.startswith("judge/")]
print(1 if "judge/notes" in completed else 0)
PY
)
    if [[ "$done_steps" == "1" && "${JUDGE_SKIP_COMPLETE:-1}" == "1" ]]; then
      echo "SKIP complete run $run_id (set JUDGE_FORCE=1 to redo)" | tee -a "$POOL_LOG"
      .venv/bin/python scripts/judge_health_report.py --run-id "$run_id" || true
      continue
    fi
  fi
  if [[ "$run_id" == "20260629_public_rep4" && -n "${SKIP_REP4_IF_RUNNING:-}" ]]; then
    if pgrep -f "run_resumable_batch.py --run-id 20260629_public_rep4 --phase judge" >/dev/null 2>&1; then
      echo "SKIP rep4; already running separately" | tee -a "$POOL_LOG"
      continue
    fi
  fi
  judge_run "$run_id"
done

echo "=== FINAL HEALTH ALL RUNS ===" | tee -a "$POOL_LOG"
.venv/bin/python scripts/judge_health_report.py \
  --run-id "${RUNS[@]}" \
  --json-out results/logs/judge_health_public_all.json \
  --csv-out results/logs/judge_health_public_all.csv || true
