set -euo pipefail
cd /opt/intelligent-quant-cr026-20260910/deploy/mvp
cp nginx-proxy.conf ../../backup/candidate-proxy-before-fix.conf
python3 - <<'PY'
from pathlib import Path
p=Path('nginx-proxy.conf')
s=p.read_text()
assert 'http://backend:8000' in s
p.write_text(s.replace('http://backend:8000','http://quant-mvp-cr026-backend-1:8000'))
PY
docker exec quant-mvp-cr026-gateway-1 nginx -t
docker exec quant-mvp-cr026-gateway-1 nginx -s reload
