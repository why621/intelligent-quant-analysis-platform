set -euo pipefail
root=/opt/intelligent-quant-cr026-20260910/deploy/mvp
test -s "$root/certificates-staging/live/43.161.223.91/fullchain.pem"
timeout 180 docker run --rm -v "$root/certificates:/etc/letsencrypt" -v "$root/webroot:/var/www/acme" certbot/certbot:v5.4.0 certonly --non-interactive --agree-tos --register-unsafely-without-email --preferred-profile shortlived --webroot --webroot-path /var/www/acme --ip-address 43.161.223.91 --cert-name 43.161.223.91
openssl x509 -in "$root/certificates/live/43.161.223.91/fullchain.pem" -noout -issuer -dates -ext subjectAltName
cp "$root/nginx-tls.conf" "$root/nginx-live/tls.conf"
docker exec quant-mvp-cr026-gateway-1 nginx -t
docker exec quant-mvp-cr026-gateway-1 nginx -s reload
