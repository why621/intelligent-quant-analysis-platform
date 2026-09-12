"""Read restored jobs through the real service without a worker or network."""
import argparse
import json
import sqlite3
from pathlib import Path

from app import create_app
from app.services.backtests import BacktestJobStore, BacktestService
from quant_platform.backtesting.engine import BacktestEngine
from quant_platform.data.publication import load_publication


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',required=True,type=Path)
    args=parser.parse_args()
    if args.db.resolve() != Path('/restore/restored.db'):
        raise ValueError('isolated restored database required')
    provider=load_publication(Path('/app/publication'))
    app=create_app({'TESTING':True},market_data_provider=provider)
    strategies=app.extensions['strategy_catalog_service']
    app.extensions['backtest_service']=BacktestService(BacktestJobStore(str(args.db)),strategies,provider,BacktestEngine(provider,strategies.registry()))
    client=app.test_client()
    with sqlite3.connect(args.db) as db:
        rows=db.execute('SELECT job_id,status,request_json,result_json FROM backtest_jobs').fetchall()
    for identity,status,request,result in rows:
        response=client.get('/api/backtests/'+identity)
        value=response.get_json()
        if response.status_code != 200 or value['status'] != status or value['request'] != json.loads(request):
            raise ValueError('restored job metadata mismatch: '+identity)
        if result is not None and value['result'] != json.loads(result):
            raise ValueError('restored job result mismatch: '+identity)
    print(json.dumps({'restoredAPIJobs':len(rows),'publicationId':provider.cache_revision(),'allRequestsAndResultsMatch':True}))


if __name__=='__main__':
    main()
