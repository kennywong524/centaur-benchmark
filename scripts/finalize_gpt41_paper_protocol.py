"""Apply the original assistant-family-only protocol to the GPT-4.1 worker pilots."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
from dotenv import load_dotenv
import centaur_benchmark.judge_pairwise as judge
from centaur_benchmark.config import load_task
import make_paper_figures as paper

ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')
os.environ['CENTAUR_EDSL_MODE']='direct'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--execute-missing',action='store_true')
args=parser.parse_args()
EXPERIMENT='20260928_gpt41_worker_paper_protocol'
ART=ROOT/'artifacts/gpt41_worker_paper_protocol'
ART.mkdir(parents=True,exist_ok=True)

def direct_model(mid,**kw):
    from edsl import Model
    return Model('gpt-4.1',service_name='openai',max_tokens=4096)

judge.make_model=direct_model
judge.edsl_run_kwargs=lambda **kw:dict(use_api_proxy=False,offload_execution=False,disable_remote_inference=True,
    cache=False,fresh=True,check_api_keys=False,progress_bar=False,print_exceptions=False,stop_on_exception=True,n=1)

combined=[]
for slug in paper.TASK_ORDER:
    source_run='20260924_gpt41_worker_pilot' if slug=='travel_planning' else '20260928_gpt41_worker_pilot'
    source=ROOT/'results'/slug/source_run/'augmentation'
    dest=ROOT/'results'/slug/EXPERIMENT/'augmentation'
    dest.mkdir(parents=True,exist_ok=True)
    outputs=pd.read_csv(dest/'outputs.csv' if (dest/'outputs.csv').exists() else source/'outputs.csv').reset_index(drop=True)
    assert len(outputs)==10 and outputs.worker_model.eq('gpt-4.1').all()
    task=load_task(ROOT/'tasks'/(slug+'.yaml'))
    available=pd.read_csv(dest/'pairwise_judgments_by_judge.csv' if (dest/'pairwise_judgments_by_judge.csv').exists() else source/'pairwise_judgments_by_judge.csv')
    openai_path=dest/'pairwise_judgments_GPT-4.1.csv'
    historical=source/'pairwise_judgments_GPT-4.1.csv'
    if openai_path.exists():
        openai=pd.read_csv(openai_path)
    elif historical.exists():
        openai=pd.read_csv(historical)
    else:
        if not args.execute_missing:
            raise RuntimeError('Missing OpenAI judgments for '+slug+'; pass --execute-missing to generate them.')
        scenarios=judge._build_scenarios_augmentation(outputs,task.pairwise_task_context,1)
        scenarios=judge._filter_scenarios_for_judge(scenarios,'gpt-4.1',exclude_self_family=True)
        assert len(scenarios)==10
        frames=[]
        for index,scenario in enumerate(scenarios):
            digest=hashlib.sha256(json.dumps(dict(scenario),sort_keys=True).encode()).hexdigest()[:16]
            checkpoint=dest/('openai_'+digest+'.csv')
            if checkpoint.exists():
                frame=pd.read_csv(checkpoint)
            else:
                for attempt in range(3):
                    frame=judge._run_pairwise_survey([scenario],judge._build_judge_instruction(task),'gpt-4.1',
                        include_run_id=False,remote_description=EXPERIMENT+'-'+slug,remote_visibility='private')
                    validation=judge.validate_judge_batch(frame)
                    if validation['batch_ok']:
                        break
                    frame.to_csv(checkpoint.with_suffix(f'.attempt{attempt+1}.invalid.csv'),index=False)
                if not validation['batch_ok']:
                    raise RuntimeError('Incomplete OpenAI judgment '+slug+': '+str(validation))
                frame['judge_label']='GPT-4.1'
                frame.to_csv(checkpoint,index=False)
            frames.append(frame)
            print('OPENAI_PROGRESS',slug,index+1,10,flush=True)
        openai=pd.concat(frames,ignore_index=True)
    openai['judge_label']='GPT-4.1'
    openai.to_csv(openai_path,index=False)
    available=available.loc[available.judge_model.ne('gpt-4.1')]
    responses=pd.concat([available,openai],ignore_index=True)
    assert len(responses)==110 and responses.parse_ok.all()
    for row in responses.itertuples():
        families={judge._model_family(outputs.loc[int(i),'model_id'],outputs.loc[int(i),'model_label'])
                  for i in [row.left_idx,row.right_idx]}
        assert judge._model_family(row.judge_model) not in families
    scored=[]
    validations={}
    for model,frame in responses.groupby('judge_model'):
        validation=judge.validate_judge_batch(frame)
        assert validation['batch_ok'],(slug,model,validation)
        validations[model]={k:v for k,v in validation.items() if k!='issues_by_row'}
        s=judge._score_from_pairwise(outputs,frame)
        s['judge_model']=model
        s['judge_label']=frame.judge_label.iloc[0]
        scored.append(s)
        frame.to_csv(dest/('pairwise_judgments_'+frame.judge_label.iloc[0]+'.csv'),index=False)
    scored=pd.concat(scored,ignore_index=True)
    # Missing scores remain missing; n_judges counts contributing judges only.
    board=judge._leaderboard_from_panel_scored(scored.loc[scored.total_games.gt(0)])
    aggregate=judge._aggregate_panel_leaderboard(board)
    outputs.to_csv(dest/'outputs.csv',index=False)
    responses.to_csv(dest/'pairwise_judgments_by_judge.csv',index=False)
    scored.to_csv(dest/'pairwise_ranked_by_judge.csv',index=False)
    board.to_csv(dest/'leaderboard_by_judge.csv',index=False)
    aggregate.to_csv(dest/'leaderboard_aggregate.csv',index=False)
    judge._write_panel_matrices(dest,board,aggregate)
    judge._write_score_summaries(dest,outputs,responses)
    (dest/'judge_validation.json').write_text(json.dumps({'protocol':'assistant-family-only, matching published GPT-3.5 Turbo augmentation implementation',
        'worker_family_masked':False,'judgments':110,'judges':validations,'aggregation':'rank average eligible-judge win rates, matching published pipeline'},indent=2))
    (dest.parent/'experiment_manifest.json').write_text(json.dumps({'experiment':EXPERIMENT,'task':slug,'worker':'gpt-4.1',
        'source_worker_outputs':str(source.relative_to(ROOT)),'saved_assistance_source':f'results/{slug}/20260610_scaffold_strict_v4/augmentation/scaffolds',
        'replicates':1,'date_context_added':False,'new_worker_generations':0,'new_judgments':'OpenAI eligible pairs only; travel planning reused',
        'openai_judge_route':'configured OpenAI provider key',
        'completed':datetime.now(timezone.utc).isoformat()},indent=2))
    for row in aggregate.itertuples():
        combined.append({'task_slug':slug,'task':paper.TASK_LABELS[slug],'model':row.model_label,
                         'rank':row.aggregate_rank,'mean_judge_rank':row.avg_rank_across_judges,
                         'mean_win_rate':row.avg_win_rate_across_judges,'n_judges':row.n_judges})
    print('TASK_FINALIZED',slug,flush=True)

pd.DataFrame(combined).to_csv(ART/'augmentation_all_tasks.csv',index=False)
bundle={'runs_by_id':{'gpt41-pilot':{'aggregate':[
    {'mode':'augmentation','task_slug':r['task_slug'],'model_label':r['model'],
     'rank_value':r['rank'],'score':r['mean_win_rate']} for r in combined]}}}
figure_rows=paper.rank_rows(bundle,'gpt41-pilot','augmentation')
figure_rows.to_csv(ART/'augmentation_paper_heatmap_task_ordering.csv',index=False)
aug=figure_rows.pivot(index='task',columns='model',values='rank')
aug=aug.loc[[paper.TASK_LABELS[t] for t in paper.TASK_ORDER]]
aug=aug[paper.column_release_order(aug.columns,mode='augmentation')]
aug=pd.concat([aug,pd.DataFrame([aug.mean()],index=['Average'])])
aug_display=paper.rank_of_ranks_matrix(aug)
data=paper.load_data()
auto,_,n=paper.mean_rank_matrix(data,'automation')
auto_display=paper.rank_of_ranks_matrix(auto)
aug.to_csv(ART/'augmentation_task_ranks_and_average.csv')
aug_display.to_csv(ART/'augmentation_heatmap_ranks.csv')
auto.to_csv(ART/'automation_published_mean_task_ranks.csv')
auto_display.to_csv(ART/'automation_heatmap_ranks.csv')
original_mean=paper.mean_rank_matrix
paper.OUT=ART
paper.MODEL_DISPLAY['plain']='GPT-4.1 (plain)'
paper.mean_rank_matrix=lambda data,mode:(aug,aug*0,1) if mode=='augmentation' else (auto,auto*0,n)
paper.draw_heatmap_rank_of_ranks({},'augmentation','gpt41_worker_augmentation_paper_protocol')
paper.draw_heatmap_rank_of_ranks({},'automation','automation_published_reference')
print('AUGMENTATION_AVERAGE_RANKS',aug_display.loc['Average'].sort_values().to_dict(),flush=True)
print('AUTOMATION_AVERAGE_RANKS',auto_display.loc['Average'].sort_values().to_dict(),flush=True)
print('ALL_FINALIZED',EXPERIMENT,flush=True)
