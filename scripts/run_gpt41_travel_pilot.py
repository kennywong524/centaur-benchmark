"""Isolated, resumable one-run worker pilot using the existing evaluation code."""
import os
import json
import hashlib
import uuid
from types import MethodType
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
os.environ['EDSL_MAX_ATTEMPTS'] = '1'
os.environ['EDSL_API_TIMEOUT'] = '180'
os.environ['REMOTE_PROXY_TIMEOUT'] = '180'
os.environ['CENTAUR_EDSL_MODE'] = 'ep_proxy'
import pandas as pd
from edsl import Model, Coop
from centaur_benchmark.config import load_task
import centaur_benchmark.runner as runner
import centaur_benchmark.judge_pairwise as judges

RUN = ROOT / 'results/travel_planning/20260924_gpt41_worker_pilot'
SOURCE = ROOT / 'results/travel_planning/20260610_scaffold_strict_v4/augmentation/scaffolds'
OUT = RUN / 'augmentation'
OUT.mkdir(parents=True, exist_ok=True)
task = load_task(ROOT / 'tasks/travel_planning.yaml')
task.worker_model_max_tokens = 8192

def kwargs(**kw):
    return dict(use_api_proxy=True, offload_execution=False, cache=False, fresh=True,
                check_api_keys=False, progress_bar=False, print_exceptions=False,
                stop_on_exception=True, n=1)

def model(mid, **kw):
    routes = {'gpt-4.1': ('gpt-4.1', 'openai'),
              'anthropic/claude-opus-4-8': ('claude-opus-4-8', 'anthropic'),
              'google/gemini-3.1-pro': ('google/gemini-3.1-pro', 'deep_infra'),
              'deepseek-ai/DeepSeek-V3.1': ('deepseek-ai/DeepSeek-V3.1', 'deep_infra')}
    name, service = routes[mid]
    kw.pop('service_name', None)
    kw.setdefault('max_tokens', 8192)
    m = Model(name, service_name=service, **kw)
    if service == 'anthropic':
        from centaur_benchmark.edsl_runtime import _patch_anthropic_no_temperature
        _patch_anthropic_no_temperature(m)
    if service == 'deep_infra':
        # EDSL reads api_token to construct a local concurrency bucket before
        # invoking our transport. No DeepInfra credential is used by this proxy.
        m._api_token = None
        async def explicit_ep_proxy(self, user_prompt, system_prompt='', files_list=None, cache_key=None, **extra):
            import aiohttp
            if files_list:
                raise ValueError('This pilot supports text-only requests.')
            payload = {'request_id':str(uuid.uuid4()), 'inference_service':'deep_infra',
                       'model':self.model,
                       'messages':[{'role':'system','content':system_prompt}, {'role':'user','content':user_prompt}],
                       'parameters':{'max_tokens':self.max_tokens, 'temperature':getattr(self,'temperature',0.5)},
                       'gcs_files':[], 'fresh':True, 'metadata':{'pilot':'gpt41-travel-worker'}}
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
                async with session.post('https://api.expectedparrot.com/execute',json=payload,
                        headers={'Authorization':'Bearer '+os.environ['EXPECTED_PARROT_API_KEY']}) as response:
                    data=await response.json()
                    if response.status != 200 or data.get('success') is False:
                        raise RuntimeError(f'Expected Parrot proxy HTTP {response.status}: {str(data)[:600]}')
                    return data.get('response',data)
        m.async_execute_model_call=MethodType(explicit_ep_proxy,m)
    return m

runner.edsl_run_kwargs = judges.edsl_run_kwargs = kwargs
runner.make_model = judges.make_model = model
judges.use_together_deepseek = lambda _: False
# Source configuration uses the canonical slash-prefixed Opus ID.
task.evaluator_models = {'anthropic/claude-opus-4-8':'Claude-Opus-4.8', 'google/gemini-3.1-pro':'Gemini-3.1-Pro', 'deepseek-ai/DeepSeek-V3.1':'DeepSeek-V3.1'}
manifest = dict(worker='gpt-4.1', source=str(SOURCE), date_context_added=False,
                task_prompt=task.task_prompt, worker_max_tokens=8192,
                replicates=1, edsl_version='1.0.8', judges=task.evaluator_models,
                started=datetime.now(timezone.utc).isoformat(), balance_before=Coop().get_balance())
if (RUN / 'pilot_manifest.json').exists():
    manifest = json.loads((RUN / 'pilot_manifest.json').read_text())
manifest['actual_routes']={'worker_gpt41':'configured OpenAI provider key via EDSL 1.0.8',
                          'judge_gpt41':'configured OpenAI provider key via EDSL 1.0.8',
                          'judge_claude':'configured Anthropic provider key via EDSL 1.0.8',
                          'judge_gemini':'explicit Expected Parrot /execute, deep_infra',
                          'judge_deepseek':'explicit Expected Parrot /execute, deep_infra'}
(RUN / 'pilot_manifest.json').write_text(json.dumps(manifest, indent=2))
print('PILOT', json.dumps(manifest), flush=True)
rows=[]
for mid, label in [('plain','plain'), *task.assistants.items()]:
    checkpoint=OUT / ('worker_'+label+'.json')
    if checkpoint.exists():
        rows.append(json.loads(checkpoint.read_text()))
        continue
    guidance='' if mid=='plain' else (SOURCE / (label+'.md')).read_text()
    prompt=task.task_prompt if mid=='plain' else runner._compose_worker_prompt(guidance,task.task_prompt)
    condition='plain' if mid=='plain' else 'scaffold_'+runner._safe_slug(label)
    df=runner._run_worker_batch(task,worker_model='gpt-4.1',condition=condition,full_prompts=[prompt],remote_description='gpt41-worker-pilot-'+label,remote_visibility='private')
    row=df.iloc[0].to_dict()
    if not isinstance(row.get('output'),str) or len(row['output'].strip())<100:
        raise RuntimeError('Empty/invalid worker output for '+label)
    row.update(assistant_model=label,worker_model='gpt-4.1',model_id=mid,model_label=label,scaffold_text=guidance,scaffold_path='' if mid=='plain' else str(SOURCE/(label+'.md')),scaffold_sha256=hashlib.sha256(guidance.encode()).hexdigest() if guidance else '')
    checkpoint.write_text(json.dumps(row,indent=2,default=str))
    rows.append(row)
    pd.DataFrame(rows).to_csv(OUT/'outputs.csv',index=False)
    print('WORKER_DONE',label,len(row['output'].split()),flush=True)
pd.DataFrame(rows).to_csv(OUT/'outputs.csv',index=False)

original=judges._run_pairwise_survey
def checkpointed(scenarios, prompt, mid, **kw):
    frames=[]
    size = 1 if 'anthropic' in mid else 3
    for start in range(0,len(scenarios),size):
        batch=scenarios[start:start+size]
        digest=hashlib.sha256(json.dumps([dict(s) for s in batch],sort_keys=True).encode()).hexdigest()[:16]
        path=OUT/('judge_'+judges._safe_file_slug(mid)+'_'+digest+'.csv')
        if path.exists():
            frame=pd.read_csv(path)
        else:
            frame=original(batch,prompt,mid,**kw)
            report=judges.validate_judge_batch(frame)
            if not report['batch_ok']:
                frame.to_csv(path.with_suffix('.invalid.csv'),index=False)
                raise RuntimeError('Invalid judge batch '+mid+': '+str(report))
            frame.to_csv(path,index=False)
        frames.append(frame)
        print('JUDGE_PROGRESS',mid,min(start+size,len(scenarios)),len(scenarios),flush=True)
    return pd.concat(frames,ignore_index=True)
judges._run_pairwise_survey=checkpointed
judges.judge_augmentation_panel(task,RUN,n_evals=1,exclude_self_family=True)
from runpy import run_path
run_path(str(ROOT / 'scripts/recompute_gpt41_travel_leave_family_out.py'))
manifest['balance_after']=Coop().get_balance()
manifest['completed']=datetime.now(timezone.utc).isoformat()
(RUN/'pilot_manifest.json').write_text(json.dumps(manifest,indent=2))
print('COMPLETE',RUN,flush=True)
print(pd.read_csv(OUT/'leaderboard_aggregate.csv').to_string(index=False),flush=True)
