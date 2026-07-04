#!/usr/bin/env bash
# Wait for in-flight rep4 judge, health-check it, then judge rep5-rep10.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a && source .env && set +a
export PYTHONPATH=src:scripts
export CENTAUR_TOGETHER_SDK_ONLY=1

POOL_LOG=results/logs/judge_public_pool.log
mkdir -p results/logs

log() { echo "$*" | tee -a "$POOL_LOG"; }

wait_for_rep4() {
  log "Waiting for rep4 judge process to finish..."
  while pgrep -f "run_resumable_batch.py --run-id 20260629_public_rep4 --phase judge" >/dev/null 2>&1; do
    sleep 30
  done
  log "rep4 judge process finished."
}

ensure_together() {
  local ep="${CENTAUR_TOGETHER_DEEPSEEK_ENDPOINT:-}"
  [[ -z "$ep" ]] && return 0
  log "Together start/wait $ep"
  PYTHONPATH=src .venv/bin/python scripts/together_deepseek_endpoint.py start "$ep" >>"$POOL_LOG" 2>&1 || true
  PYTHONPATH=src .venv/bin/python scripts/together_deepseek_endpoint.py wait "$ep" --timeout 1800 >>"$POOL_LOG" 2>&1
}

stop_together() {
  local ep="${CENTAUR_TOGETHER_DEEPSEEK_ENDPOINT:-}"
  [[ -z "$ep" ]] && return 0
  log "Together stop $ep"
  PYTHONPATH=src .venv/bin/python scripts/together_deepseek_endpoint.py stop "$ep" >>"$POOL_LOG" 2>&1 || true
}

judge_run() {
  local run_id="$1"
  log "=== JUDGE START $run_id $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  .venv/bin/python scripts/run_resumable_batch.py \
    --run-id "$run_id" \
    --phase judge \
    --n-evals 1 \
    --no-resume \
    --verify \
    --continue-on-error \
    --max-step-failures 6 \
    --max-consecutive-failures 30 \
    2>&1 | tee "results/logs/judge_${run_id}.log"
  log "=== HEALTH $run_id ==="
  .venv/bin/python scripts/judge_health_report.py --run-id "$run_id" || true
  log "=== JUDGE DONE $run_id $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
}

wait_for_rep4
log "=== HEALTH rep4 (post-run) ==="
.venv/bin/python scripts/judge_health_report.py --run-id 20260629_public_rep4 || true

ensure_together
trap stop_together EXIT

for run_id in \
  20260629_public_rep5 \
  20260629_public_rep6 \
  20260629_public_rep7 \
  20260629_public_rep8 \
  20260629_public_rep9 \
  20260629_public_rep10; do
  judge_run "$run_id"
done

log "=== FINAL HEALTH ALL 7 RUNS ==="
.venv/bin/python scripts/judge_health_report.py \
  --run-id 20260629_public_rep4 \
  --run-id 20260629_public_rep5 \
  --run-id 20260629_public_rep6 \
  --run-id 20260629_public_rep7 \
  --run-id 20260629_public_rep8 \
  --run-id 20260629_public_rep9 \
  --run-id 20260629_public_rep10 \
  --json-out results/logs/judge_health_public_all.json \
  --csv-out results/logs/judge_health_public_all.csv || true

log "=== JUDGE POOL COMPLETE $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
