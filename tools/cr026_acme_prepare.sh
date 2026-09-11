set -euo pipefail
root=/opt/intelligent-quant-cr026-20260910
cd "$root/deploy/mvp"
python3 - "$root" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
original=(root/'backup/legacy-nginx.conf').read_text()
assert '    location /api/ {' in original and 'acme-challenge' not in original
challenge='    location ^~ /.well-known/acme-challenge/ {\n        proxy_pass http://cr026-gateway:8080;\n    }\n\n'
(root/'backup/legacy-nginx-acme.conf').write_text(original.replace('    location /api/ {',challenge+'    location /api/ {',1))
p=root/'deploy/mvp/webroot/.well-known/acme-challenge'
p.mkdir(parents=True,exist_ok=True)
(p/'cr026-check').write_text('cr026-acme-route-ready')
PY
docker cp "$root/backup/legacy-nginx-acme.conf" intelligent-quant-regression-frontend-1:/etc/nginx/conf.d/default.conf
if ! docker exec intelligent-quant-regression-frontend-1 nginx -t; then
    docker cp "$root/backup/legacy-nginx.conf" intelligent-quant-regression-frontend-1:/etc/nginx/conf.d/default.conf
    exit 1
fi
docker exec intelligent-quant-regression-frontend-1 nginx -s reload
curl --retry 0 --max-time 10 -fsS http://127.0.0.1/.well-known/acme-challenge/cr026-check
docker pull certbot/certbot:v5.4.0
docker run --rm certbot/certbot:v5.4.0 --version
