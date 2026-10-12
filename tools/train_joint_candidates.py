"""CR066 frozen two-seed candidate experiment; explicit local inputs, no downloads."""
from pathlib import Path
import argparse
import json
import hashlib
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data-root', type=Path, required=True,
                    help='directory with data-preparation.json and training-data/SYMBOL.csv')
parser.add_argument('--output-root', type=Path, required=True)
import pandas as pd
from quant_platform.models import TradingCosts
from quant_platform.rl.portfolio_train import train_portfolio
from quant_platform.rl.portfolio_policy import load_portfolio_bundle
from quant_platform.rl.portfolio_evaluation import evaluate_portfolio
args = parser.parse_args()
out = args.output_root
out.mkdir(parents=True, exist_ok=True)
old = args.data_root
prep = json.loads((old/'data-preparation.json').read_text())
frames = {s: pd.read_csv(old/'training-data'/f'{s}.csv') for s in prep['symbols']}
plan = dict(prep, purpose='formal_candidates_for_experimental_release',
    seeds=[42,137], stepsPerCandidate=65536, maxSecondsPerCandidate=1200,
    selection='highest_validation_return_minus_max_drawdown_per_algorithm',
    limitations=['one year cached history; short validation/test',
                 'test dates previously replayed by CR065 smoke, not pristine blind evidence',
                 'no unseen asset generalization or profitability claim'])
(out/'plan.json').write_text(json.dumps(plan, indent=2))
report = {'plan':plan, 'candidates':{}, 'selected':{}, 'tests':{}}
splits=prep['splits']
for algo in ['ppo','sac','td3']:
    candidates=[]
    for seed in plan['seeds']:
        run=f'cr066-{algo}-joint-s{seed}'
        path=out/'models'/run
        if not path.exists():
            path=train_portfolio(frames, asset_types={s:'stock' for s in frames},
                trading_costs=TradingCosts(stamp_duty_mode='asset_date'),
                splits=splits, output_root=out/'models', run_id=run, algo=algo,
                total_timesteps=65536,max_seconds=1200,episode_bars=48,seed=seed,
                band_pct=0.01,min_trade_cny=100,formal_candidate=True)
        bundle=load_portfolio_bundle(path)
        if bundle.manifest['actualTimesteps'] < 65536:
            raise RuntimeError('formal candidate exhausted time before registered steps')
        val=evaluate_portfolio(bundle,frames,start=splits['valStartDate'],end=splits['valEndDate'])
        (path/'validation.json').write_text(json.dumps(val,indent=2))
        score=val['metrics']['returnPct']-val['metrics']['maxDrawdownPct']
        info={'runId':run,'bundleHash':bundle.manifest['bundleHash'],'score':score,
              'metrics':val['metrics'],'steps':bundle.manifest['actualTimesteps'],
              'optimizerUpdates':bundle.manifest['optimizerUpdates']}
        candidates.append(info); report['candidates'][run]=info
        (out/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(info),flush=True)
    report['selected'][algo]=max(candidates,key=lambda x:x['score'])
# Freeze all selections before opening any test replay.
(out/'selection.json').write_text(json.dumps(report['selected'],indent=2))
for algo, chosen in report['selected'].items():
    path=out/'models'/chosen['runId']; bundle=load_portfolio_bundle(path)
    result=evaluate_portfolio(bundle,frames,start=splits['testStartDate'],end=splits['testEndDate'])
    baselines={b:evaluate_portfolio(bundle,frames,start=splits['testStartDate'],
        end=splits['testEndDate'],baseline=b)['metrics'] for b in ['equal_weight_hold','ma_cross']}
    evidence={'runId':chosen['runId'],'bundleHash':chosen['bundleHash'],
              'validation':chosen['metrics'],'test':result['metrics'],'baselines':baselines,
              'selection':plan['selection'],'limitations':plan['limitations'],
              'testStartDate':splits['testStartDate'],'testEndDate':splits['testEndDate'],
              'simultaneousAssets':len(frames),'ledgerPassed':True}
    (path/'test-replay.json').write_text(json.dumps(result,indent=2))
    raw=json.dumps(evidence,sort_keys=True,indent=2).encode()
    (path/'evaluation.json').write_bytes(raw)
    report['tests'][algo]=dict(evidence,evaluationSha256=hashlib.sha256(raw).hexdigest())
    (out/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'test':algo,**evidence}),flush=True)
