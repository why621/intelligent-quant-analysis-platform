set -euo pipefail
root=/opt/intelligent-quant-cr026-20260910
archive=/home/ubuntu/quant-cr026-release.tar.gz
test "$(git -C /opt/intelligent-quant-regression rev-parse HEAD)" = af02f826b7dcfd1b8a4fb9fd8bdcf56fe07b8d56
test "$(docker image inspect --format '{{.Id}}' intelligent-quant-regression-backend:release-af02f826)" = sha256:a2bd5590d0f66ef9b23ec2c6a61d5fd056620fd71d4ca4c39122fc4491656ef4
test "$(docker image inspect --format '{{.Id}}' intelligent-quant-regression-frontend:release-af02f826)" = sha256:378d4c56f9ffcd6d042f7ee86f161543f8e3263db0027ff33f45064187d80424
test ! -e "$root"
python3 - "$archive" "$root" <<'PY'
import hashlib,json,sys,tarfile
from pathlib import Path
archive,root=map(Path,sys.argv[1:])
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='694d5b4f96491cedfaf60be35bf386ddfa478e0833e3e9c658afb38b0e3ca052'
with tarfile.open(archive) as source:
    members=source.getmembers()
    assert len({m.name for m in members})==len(members)
    for m in members:
        assert m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
    manifest=json.load(source.extractfile('release-manifest.json'))
    assert set(manifest['files'])=={m.name for m in members}-{'release-manifest.json'}
    for name,digest in manifest['files'].items():
        assert hashlib.sha256(source.extractfile(name).read()).hexdigest()==digest,name
    root.mkdir(mode=0o700)
    source.extractall(root,filter='data')
print('Archive identity and all file hashes verified')
PY
mkdir -m 700 "$root/backup"
docker exec -u 0 intelligent-quant-regression-backend-1 python -c '
import sqlite3
from pathlib import Path
root=Path("/tmp/cr026-backups")
root.mkdir(mode=0o700)
for origin,name in [("/app/var/backtests.db","backtests.db"),("/app/data/processed/market_data.db","market_data.db")]:
    source=sqlite3.connect("file:"+origin+"?mode=ro",uri=True)
    dest=sqlite3.connect(root/name)
    source.backup(dest)
    assert dest.execute("PRAGMA integrity_check").fetchall()==[("ok",)]
    dest.close();source.close()
print("Two isolated SQLite backups passed integrity_check")
'
docker cp intelligent-quant-regression-backend-1:/tmp/cr026-backups/. "$root/backup/"
docker cp intelligent-quant-regression-frontend-1:/etc/nginx/conf.d/default.conf "$root/backup/legacy-nginx.conf"
chmod 600 "$root/backup/"*
cd "$root/deploy/mvp"
mkdir jobs nginx-live webroot certificates
cp "$root/backup/backtests.db" jobs/backtests.db
chown -R "$(docker exec intelligent-quant-regression-backend-1 id -u):$(docker exec intelligent-quant-regression-backend-1 id -g)" jobs
cp nginx.conf nginx-live/default.conf
docker compose -f compose.yml config --quiet
docker compose -f compose.yml build backend
docker compose -f compose.yml up -d backend gateway
printf '%s\n' 'CR026 candidate started; original services retained'
