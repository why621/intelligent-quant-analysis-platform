set -euo pipefail
root=/opt/intelligent-quant-cr026-20260910
cat > "$root/backup/http-preview.conf" <<'CONF'
server {
    listen 80;
    server_name 43.161.223.91;
    location / {
        proxy_pass http://cr026-gateway:8080;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 120s;
    }
}
CONF
docker cp "$root/backup/http-preview.conf" intelligent-quant-regression-frontend-1:/etc/nginx/conf.d/default.conf
if ! docker exec intelligent-quant-regression-frontend-1 nginx -t; then
    docker cp "$root/backup/legacy-nginx-acme.conf" intelligent-quant-regression-frontend-1:/etc/nginx/conf.d/default.conf
    exit 1
fi
docker exec intelligent-quant-regression-frontend-1 nginx -s reload
