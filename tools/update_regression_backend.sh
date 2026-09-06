#!/usr/bin/env bash
# Run as root from the existing server checkout after a reviewed fast-forward pull.
set -eu
cd /opt/intelligent-quant-regression

# Only the backend image changes. Preserve both named data volumes and the
# existing frontend/proxy container; do not republish a frontend on this server.
docker compose -f compose.regression.yml build backend
docker compose -f compose.regression.yml up -d --no-deps --wait --wait-timeout 120 backend
# Nginx resolves the backend's container address at startup/reload.
docker compose -f compose.regression.yml exec -T frontend nginx -s reload

update_status=0
docker compose -f compose.regression.yml exec -T backend quant-data-update \
  > /var/log/quant-data-update.log 2>&1 || update_status=$?
tail -n 60 /var/log/quant-data-update.log
printf '\nData refresh exit code: %s (0=ready, 2=degraded, 1=failed)\n' "$update_status"
curl --fail --silent --show-error --max-time 10 http://127.0.0.1/api/health
printf '\n'
curl --fail --silent --show-error --max-time 10 http://127.0.0.1/api/data/status \
  | python3 -m json.tool
exit "$update_status"
