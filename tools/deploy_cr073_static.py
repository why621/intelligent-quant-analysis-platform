"""Explicit CR073 static-only release, with backup and preservation assertions."""
import argparse
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path

from deploy_cloud_preview import OPTIONS, SCP, TARGET
from deploy_cr071_release import ROOT, remote

STAGE = '/opt/intelligent-quant-cr073-20261024'
UPLOAD = '/home/ubuntu/cr073-static.tar.gz'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert re.fullmatch('[0-9a-f]{40}', args.revision)
    files = {p.relative_to(args.output / 'dist-cloud').as_posix(): p.read_bytes()
             for p in (args.output / 'dist-cloud').rglob('*') if p.is_file()}
    assert 'index.html' in files and len(files) == 12
    manifest = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    files['manifest.json'] = json.dumps(manifest).encode()
    archive = args.output / 'static.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name, raw in files.items():
            item = tarfile.TarInfo(name)
            item.size, item.mode = len(raw), 0o644
            tar.addfile(item, io.BytesIO(raw))
    subprocess.run([SCP, *OPTIONS, str(archive.resolve()), TARGET + ':' + UPLOAD], check=True, timeout=120)
    result = remote(f'''
import fcntl, hashlib, json, os, shutil, sqlite3, subprocess, tarfile
from pathlib import Path
root=Path({ROOT!r}); stage=Path({STAGE!r}); web=root/'apps/frontend/dist'
assert not stage.exists(), 'Release stage already exists; inspect before retry'
archive=Path({UPLOAD!r})
assert hashlib.sha256(archive.read_bytes()).hexdigest()=={hashlib.sha256(archive.read_bytes()).hexdigest()!r}
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot():
    state=json.loads(subprocess.check_output(['docker','inspect','quant-mvp-cr026-backend-1']))[0]
    assert state['State']['Health']['Status']=='healthy'
    with sqlite3.connect('file:'+str(root/'deploy/mvp/jobs/backtests.db')+'?mode=ro',uri=True) as db:
        rows=db.execute('select * from backtest_jobs order by job_id').fetchall()
    old=json.loads(Path('/opt/intelligent-quant-cr071-20261020-r1/deployment.json').read_bytes())
    tracked={{name:digest(Path(name)) for name in old['dailyRuntimeAndToolsUnchanged']}}
    return {{'containerId':state['Id'],'image':state['Image'],'startedAt':state['State']['StartedAt'],
        'jobsCount':len(rows),'jobsHash':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),
        'publicationHash':digest(root/'deploy/mvp/publication/current.json'),'dailyFiles':tracked,
        'timer':subprocess.check_output(['systemctl','is-active','quant-mvp-daily.timer'],text=True).strip()}}
with tarfile.open(archive) as tar:
    members=tar.getmembers()
    assert all(m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in members)
    hashes=json.load(tar.extractfile('manifest.json'))
    assert len(members)==len(hashes)+1 and {{m.name for m in members}}==set(hashes)|{{'manifest.json'}}
    assert all(hashlib.sha256(tar.extractfile(n).read()).hexdigest()==h for n,h in hashes.items())
    stage.mkdir(); tar.extractall(stage/'candidate',filter='data')
before=snapshot()
(stage/'before.json').write_text(json.dumps(before,indent=2))
shutil.copytree(web,stage/'backup')
try:
    for name in hashes:
        if name!='index.html':
            target=web/name; target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(stage/'candidate'/name,target)
    pending=web/'index.cr073.pending'
    shutil.copy2(stage/'candidate/index.html',pending); os.replace(pending,web/'index.html')
    assert all(digest(web/name)==value for name,value in hashes.items())
    after=snapshot()
    assert before==after, 'Preservation snapshot changed during release'
except BaseException:
    for name in hashes:
        previous=stage/'backup'/name
        if previous.exists() and name!='index.html': shutil.copy2(previous,web/name)
    pending=web/'index.cr073.rollback'
    shutil.copy2(stage/'backup/index.html',pending); os.replace(pending,web/'index.html')
    raise
result={{'revision':{args.revision!r},'stage':str(stage),'files':hashes,'before':before,'after':after,'rollbackTriggered':False}}
(stage/'deployment.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
''', timeout=180)
    (args.output / 'cloud-deployment.json').write_bytes(result)
    print('Published 12 static files; backend, jobs, publication pointer and daily files unchanged.')


if __name__ == '__main__':
    main()
