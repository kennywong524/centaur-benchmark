"""Run one GPT-4.1 worker pilot for each of the six remaining tasks."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ['counselling','market_trends','meal_plan','operations_research','tax_prep','tutoring']
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--execute', action='store_true', help='Launch inference; default performs local preflight only.')
parser.add_argument('--run-id', default='20260928_gpt41_worker_pilot')
args = parser.parse_args()

# Validate every task locally before starting any paid requests.
for task in TASKS:
    command = [sys.executable, '-u', str(ROOT/'scripts/run_gpt41_travel_pilot.py'), '--task', task, '--run-id', args.run_id]
    subprocess.run(command+['--check-only'],cwd=ROOT,check=True)
if not args.execute:
    print('ALL_PREFLIGHT_OK: six tasks, 60 worker outputs, 600 eligible judge comparisons.',flush=True)
    raise SystemExit(0)

logs = ROOT/'results/logs'/args.run_id
logs.mkdir(parents=True,exist_ok=True)
for task in TASKS:
    run = ROOT/'results'/task/args.run_id
    manifest = run/'pilot_manifest.json'
    if manifest.exists():
        metadata = json.loads(manifest.read_text())
        if metadata.get('completed') and metadata.get('strict_leave_family_out'):
            print('TASK_ALREADY_COMPLETE',task,flush=True)
            continue
    log = logs/(task+'.log')
    print('TASK_START',task,'log='+str(log),flush=True)
    command = [sys.executable,'-u',str(ROOT/'scripts/run_gpt41_travel_pilot.py'),'--task',task,'--run-id',args.run_id]
    with log.open('a') as stream:
        result = subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    if result.returncode:
        print('TASK_FAILED',task,'log='+str(log),flush=True)
        print('Fix the error and rerun the same command to resume from checkpoints.',flush=True)
        raise SystemExit(result.returncode)
    print('TASK_COMPLETE',task,flush=True)
print('ALL_COMPLETE: six additional task pilots completed with strict leave-family-out.',flush=True)
