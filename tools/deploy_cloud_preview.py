"""Explicit CR-015 deployment driver: strict SSH, backups, no data refresh or push.

Run only with a reviewed Git bundle whose sole head matches --revision.
Actions are separate so failed build/transport never silently triggers a cutover.
"""
import argparse
import re
import shlex
import subprocess
from pathlib import Path

SSH = "C:/Windows/System32/OpenSSH/ssh.exe"
SCP = "C:/Windows/System32/OpenSSH/scp.exe"
OPTIONS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
           "-o", "HostKeyAlias=43.161.219.65", "-o",
           "UserKnownHostsFile=C:/Users/wangh/.ssh/known_hosts",
           "-o", "ConnectTimeout=10", "-o", "ConnectionAttempts=1",
           "-o", "IdentitiesOnly=yes", "-i", "D:/quantserver.pem"]
TARGET = "ubuntu@43.161.223.91"
REPO = "/opt/intelligent-quant-regression"
BACKUP = "/opt/intelligent-quant-backups/cr015-preview-20260908"
BASE = "b4634d18abd2409fde9c9cd533dc811dd4ca2f1f"
COMPOSE = "docker compose -f compose.regression.yml"
PREFIX = f"set -eu\ncd {REPO}\nexport FRONTEND_BIND_ADDRESS=0.0.0.0 FRONTEND_PORT=80 VITE_API_BASE_URL=/api\n"
BACKEND = "intelligent-quant-regression-backend"
FRONTEND = "intelligent-quant-regression-frontend"


def remote(script, timeout=180):
    result = subprocess.run([SSH, *OPTIONS, TARGET, "sudo -n bash -s"],
                            input=PREFIX + script, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "upload", "build", "cutover", "rollback"])
    parser.add_argument("--revision", required=True)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("full reviewed Git revision required")
    revision = args.revision
    if args.action == "backup":
        backup_code = '''import json, sqlite3
from pathlib import Path
root = Path("/tmp/cr015-preview-backup")
root.mkdir(mode=0o700)
for source, name in [("/app/data/processed/market_data.db", "market_data.db"),
                     ("/app/var/backtests.db", "backtests.db")]:
    src = sqlite3.connect("file:" + source + "?mode=ro", uri=True, timeout=15)
    dst = sqlite3.connect(root / name)
    src.backup(dst)
    result = dst.execute("PRAGMA integrity_check").fetchall()
    assert result == [("ok",)], result
    print(json.dumps({"backup": name, "integrity": result}), flush=True)
    dst.close()
    src.close()
'''
        remote(f'''test "$(git rev-parse HEAD)" = {BASE}
test -z "$(git status --porcelain)"
test ! -e {BACKUP}
mkdir -m 700 {BACKUP}
git bundle create {BACKUP}/repository.bundle --all
docker inspect {BACKEND}-1 {FRONTEND}-1 > {BACKUP}/containers.json
chmod 600 {BACKUP}/containers.json
docker image tag $(docker inspect --format '{{{{.Image}}}}' {BACKEND}-1) {BACKEND}:rollback-cr015
docker image tag $(docker inspect --format '{{{{.Image}}}}' {FRONTEND}-1) {FRONTEND}:rollback-cr015
docker exec -u 0 {BACKEND}-1 python -B -c {shlex.quote(backup_code)}
docker cp {BACKEND}-1:/tmp/cr015-preview-backup/. {BACKUP}/
chmod 600 {BACKUP}/*.db
test -s {BACKUP}/market_data.db
test -s {BACKUP}/backtests.db
printf '%s\\n' 'BACKUP COMPLETE: {BACKUP}'
''')
    elif args.action == "upload":
        if not args.bundle or not args.bundle.is_file():
            parser.error("existing reviewed bundle required")
        subprocess.run([SCP, *OPTIONS, str(args.bundle.resolve()),
                        TARGET + ":/home/ubuntu/quant-preview-cr015.bundle"], check=True, timeout=120)
    elif args.action == "build":
        remote(f'''test -s {BACKUP}/market_data.db
test -s {BACKUP}/backtests.db
test "$(git rev-parse HEAD)" = {BASE}
test -z "$(git status --porcelain)"
git bundle verify /home/ubuntu/quant-preview-cr015.bundle
test "$(git bundle list-heads /home/ubuntu/quant-preview-cr015.bundle | wc -l)" = 1
test "$(git bundle list-heads /home/ubuntu/quant-preview-cr015.bundle | cut -d' ' -f1)" = {revision}
git fetch /home/ubuntu/quant-preview-cr015.bundle HEAD
git merge --ff-only FETCH_HEAD
test "$(git rev-parse HEAD)" = {revision}
{COMPOSE} build backend frontend
docker image tag {BACKEND}:latest {BACKEND}:release-{revision[:8]}
docker image tag {FRONTEND}:latest {FRONTEND}:release-{revision[:8]}
printf '%s\\n' 'BUILD COMPLETE; old containers still running'
''', timeout=1800)
    elif args.action == "cutover":
        remote(f'''test "$(git rev-parse HEAD)" = {revision}
test -s {BACKUP}/market_data.db
test -s {BACKUP}/backtests.db
docker image inspect {BACKEND}:release-{revision[:8]} > /dev/null
docker image inspect {FRONTEND}:release-{revision[:8]} > /dev/null
if {COMPOSE} up -d --no-build --wait --wait-timeout 120 backend frontend; then
  {COMPOSE} ps
  curl --fail --silent --show-error --max-time 10 http://127.0.0.1/api/health
else
  docker image tag {BACKEND}:rollback-cr015 {BACKEND}:latest
  docker image tag {FRONTEND}:rollback-cr015 {FRONTEND}:latest
  {COMPOSE} up -d --no-build --force-recreate --wait --wait-timeout 120 backend frontend
  exit 1
fi
''', timeout=360)
    else:
        remote(f'''docker image tag {BACKEND}:rollback-cr015 {BACKEND}:latest
docker image tag {FRONTEND}:rollback-cr015 {FRONTEND}:latest
{COMPOSE} up -d --no-build --force-recreate --wait --wait-timeout 120 backend frontend
{COMPOSE} ps
''', timeout=360)


if __name__ == "__main__":
    main()
