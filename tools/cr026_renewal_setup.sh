set -euo pipefail
root=/opt/intelligent-quant-cr026-20260910/deploy/mvp
cat > "$root/renew-certificate.sh" <<'SH'
#!/bin/bash
set -euo pipefail
root=/opt/intelligent-quant-cr026-20260910/deploy/mvp
exec 9>"$root/certificate-renew.lock"
flock -n 9 || exit 0
timeout 240 docker run --rm -v "$root/certificates:/etc/letsencrypt" -v "$root/webroot:/var/www/acme" certbot/certbot@sha256:c23159d30afdd9c97960578aa4654f5901de6cae394958f894074dedd55e599d renew --non-interactive --no-random-sleep-on-renew
docker exec quant-mvp-cr026-gateway-1 nginx -t
docker exec quant-mvp-cr026-gateway-1 nginx -s reload
openssl x509 -checkend 172800 -noout -in "$root/certificates/live/43.161.223.91/fullchain.pem"
SH
chmod 700 "$root/renew-certificate.sh"
test ! -e /etc/systemd/system/quant-cr026-certificate.service
test ! -e /etc/systemd/system/quant-cr026-certificate.timer
cat > /etc/systemd/system/quant-cr026-certificate.service <<'UNIT'
[Unit]
Description=CR026 certificate renewal and verified nginx reload
After=docker.service network-online.target
Requires=docker.service
[Service]
Type=oneshot
ExecStart=/opt/intelligent-quant-cr026-20260910/deploy/mvp/renew-certificate.sh
TimeoutStartSec=300
UNIT
cat > /etc/systemd/system/quant-cr026-certificate.timer <<'UNIT'
[Unit]
Description=Check six-day IP certificate twice daily
[Timer]
OnCalendar=*-*-* 03,15:00:00
RandomizedDelaySec=1800
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now quant-cr026-certificate.timer
systemctl start quant-cr026-certificate.service
systemctl show quant-cr026-certificate.service -p Result -p ExecMainStatus
systemctl list-timers quant-cr026-certificate.timer --no-pager
