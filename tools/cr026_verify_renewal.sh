set -euo pipefail
root=/opt/intelligent-quant-cr026-20260910/deploy/mvp
timeout 240 docker run --rm -v "$root/certificates:/etc/letsencrypt" -v "$root/webroot:/var/www/acme" certbot/certbot@sha256:c23159d30afdd9c97960578aa4654f5901de6cae394958f894074dedd55e599d renew --dry-run --non-interactive --no-random-sleep-on-renew
docker exec quant-mvp-cr026-gateway-1 nginx -t
docker exec quant-mvp-cr026-gateway-1 nginx -s reload
python3 - <<'PY'
import sqlite3
from pathlib import Path
root=Path('/opt/intelligent-quant-cr026-20260910')
a=sqlite3.connect('file:'+str(root/'backup/backtests.db')+'?mode=ro',uri=True)
b=sqlite3.connect('file:'+str(root/'deploy/mvp/jobs/backtests.db')+'?mode=ro',uri=True)
assert a.execute('pragma integrity_check').fetchall()==[('ok',)]
assert b.execute('pragma integrity_check').fetchall()==[('ok',)]
rows=a.execute("select job_id,status,request_json,result_json from backtest_jobs where status in ('succeeded','failed')").fetchall()
for row in rows:
    assert b.execute('select job_id,status,request_json,result_json from backtest_jobs where job_id=?',(row[0],)).fetchone()==row
print('Original completed tasks preserved:',len(rows))
PY
curl --max-time 10 -fsS -D - -o /dev/null -X OPTIONS -H 'Origin: https://why621.github.io' -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: content-type,x-research-version' http://127.0.0.1:8081/api/analytics/correlation
