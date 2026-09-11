set -euo pipefail
root=/opt/intelligent-quant-cr026-20260910
python3 - "$root" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
p=root/'deploy/mvp/nginx-api.conf'
s=p.read_text()
assert 'gzip_types' not in s
p.write_text('gzip on;\ngzip_types application/javascript text/css;\ngzip_min_length 1024;\ngzip_vary on;\n'+s)
p=root/'backup/http-preview.conf'
s=p.read_text()
assert 'proxy_buffering off' not in s
p.write_text(s.replace('        proxy_http_version 1.1;','        proxy_http_version 1.1;\n        proxy_buffering off;'))
PY
docker exec quant-mvp-cr026-gateway-1 nginx -t
docker exec quant-mvp-cr026-gateway-1 nginx -s reload
docker cp "$root/backup/http-preview.conf" intelligent-quant-regression-frontend-1:/etc/nginx/conf.d/default.conf
docker exec intelligent-quant-regression-frontend-1 nginx -t
docker exec intelligent-quant-regression-frontend-1 nginx -s reload
