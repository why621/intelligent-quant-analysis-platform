"""One bounded explicit CSI300 index request in a short-lived worker."""
import json
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from quant_platform.data.calendar import latest_session, sessions
import requests
from quant_platform.data import history_probe
from quant_platform.data.index_snapshot import SOURCE_URL


def probe(payload):
    start, end = date.fromisoformat(payload["start"]), date.fromisoformat(payload["end"])
    if start >= end or (end - start).days > 366 or end > latest_session(datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1)):
        raise ValueError("index range must be a completed bounded year")
    sessions(start, end)
    history_probe.MAX_REQUESTS = 2
    trace = []
    with history_probe.bounded_requests(trace):
        response = requests.get(SOURCE_URL,params={'_var':'kline_dayqfq',
            'param':f"sh000300,day,{payload['start']},{payload['end']},640,qfq"})
    return {'raw':response.content.decode('utf-8'),'httpTrace':trace}

if __name__=='__main__':
    print(json.dumps(probe(json.load(sys.stdin)),ensure_ascii=False))
