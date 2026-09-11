"""Execute an explicitly named CR026 reviewed script with strict existing SSH identity."""
import subprocess
import sys
from pathlib import Path

from deploy_cloud_preview import OPTIONS, SSH, TARGET

SCRIPTS = {"static-transfer": "tools/cr026_static_transfer.sh", "verify-renewal": "tools/cr026_verify_renewal.sh", "renewal-setup": "tools/cr026_renewal_setup.sh", "http-preview": "tools/cr026_http_preview.sh", "prepare": "tools/cr026_cloud_prepare.sh", "fix-proxy": "tools/cr026_fix_proxy.sh", "acme-prepare": "tools/cr026_acme_prepare.sh", "cert-staging": "tools/cr026_cert_staging.sh", "cert-production": "tools/cr026_cert_production.sh"}
if len(sys.argv) != 2 or sys.argv[1] not in SCRIPTS:
    raise SystemExit("known CR026 stage required")
payload = Path(SCRIPTS[sys.argv[1]]).read_bytes()
if b"\r" in payload:
    raise SystemExit("SSH input must preserve LF")
result = subprocess.run([SSH, *OPTIONS, TARGET, "sudo -n bash -s"], input=payload, timeout=900, check=False)
raise SystemExit(result.returncode)
