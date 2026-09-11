set -euo pipefail
root=/opt/intelligent-quant-cr026-20260910/deploy/mvp
mkdir -p "$root/certificates-staging"
timeout 180 docker run --rm -v "$root/certificates-staging:/etc/letsencrypt" -v "$root/webroot:/var/www/acme" certbot/certbot:v5.4.0 certonly --staging --non-interactive --agree-tos --register-unsafely-without-email --preferred-profile shortlived --webroot --webroot-path /var/www/acme --ip-address 43.161.223.91 --cert-name 43.161.223.91
