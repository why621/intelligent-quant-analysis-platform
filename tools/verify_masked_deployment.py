"""Read-only deployed image/data/task preservation and exact public file checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

from deploy_masked_release import ROOT, STAGE, remote


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pages", action="store_true")
    args = parser.parse_args()
    ledger = json.loads((args.output / "browser/online-mutations.json").read_bytes())
    ids = sorted(entry["response"]["jobId"] for entry in ledger["jobs"].values())
    result = json.loads(remote(f"""
import hashlib,json,sqlite3,subprocess
from pathlib import Path
stage=Path({STAGE!r});root=Path({ROOT!r})
d=json.loads((stage/'deployment.json').read_bytes())
assert not d['rollbackTriggered']
state=json.loads(subprocess.check_output(['docker','inspect','quant-mvp-cr026-backend-1']))[0]
assert state['Image']==d['image'] and state['State']['Health']['Status']=='healthy'
for name,digest in d['dailyRuntimeAndToolsUnchanged'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
models=Path('/opt/intelligent-quant-cr062-20261001/models')
assert d['oldModelsUnchanged']=={{str(p.relative_to(models)):hashlib.sha256(p.read_bytes()).hexdigest() for p in models.rglob('*') if p.is_file()}}
pointer=json.loads((root/'deploy/mvp/publication/current.json').read_bytes())
assert pointer['publicationId']==d['publicationUnchanged']
assert subprocess.check_output(['systemctl','is-active','quant-mvp-daily.timer'],text=True).strip()=='active'
assert not (root/'deploy/mvp/nginx-live/maintenance.enabled').exists()
def rows(path):
    with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        columns=[r[1] for r in db.execute('PRAGMA table_info(backtest_jobs)')]
        index=columns.index('job_id')
        return columns,{{r[index]:r for r in db.execute('select * from backtest_jobs')}}
old_columns,old=rows(stage/'backup/jobs/backup.db')
columns,current=rows(root/'deploy/mvp/jobs/backtests.db')
assert columns==old_columns and all(current[k]==v for k,v in old.items())
assert set(current)-set(old)==set({ids!r})
assert all(current[k][columns.index('status')]=='succeeded' for k in {ids!r})
print(json.dumps({{'healthy':True,'image':state['Image'],'oldRowsPreserved':len(old),
'newAcceptanceJobs':{ids!r},'totalRows':len(current),'dailyAndDataUnchanged':True}}))
"""))
    site = ("https://why621.github.io/intelligent-quant-analysis-platform/" if args.pages
            else "https://43.161.223.91/")
    folder = args.output / ("dist-pages" if args.pages else "dist-cloud")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    hashes = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            relative = path.relative_to(folder).as_posix()
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            with opener.open(site + relative, timeout=30) as response:
                assert response.status == 200
                assert hashlib.sha256(response.read()).hexdigest() == expected, relative
            hashes[relative] = expected
    assert hashes and "index.html" in hashes
    result.update(site=site, publicFileHashes=hashes, matchedFiles=len(hashes))
    (args.output / ("pages-final-audit.json" if args.pages else "cloud-final-audit.json")).write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in result.items() if k != "publicFileHashes"}, indent=2))


if __name__ == "__main__":
    main()
