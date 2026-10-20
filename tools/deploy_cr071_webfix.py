"""Apply the reviewed CR071 allocation wrapping fix to static assets only."""
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

from deploy_cloud_preview import OPTIONS, SCP, TARGET
from deploy_cr071_release import ROOT, STAGE, UPLOAD, remote

out = Path("artifacts/cr071-deploy-01")
files = {p.relative_to(out / "dist-cloud").as_posix(): p.read_bytes()
         for p in (out / "dist-cloud").rglob("*") if p.is_file()}
assert "index.html" in files and len(files) == 12
manifest = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
files["web-manifest.json"] = json.dumps(manifest).encode()
archive = out / "web-fix.tar.gz"
with tarfile.open(archive, "w:gz") as tar:
    for name, raw in files.items():
        item = tarfile.TarInfo(name)
        item.size, item.mode = len(raw), 0o644
        tar.addfile(item, io.BytesIO(raw))
subprocess.run([SCP, *OPTIONS, str(archive.resolve()), TARGET + ":" + UPLOAD + "/web-fix.tar.gz"], check=True, timeout=120)
result = remote(f"""
import hashlib,json,os,shutil,tarfile
from pathlib import Path
stage=Path({STAGE!r}); web=Path({ROOT!r})/'apps/frontend/dist'
a=Path({UPLOAD!r})/'web-fix.tar.gz'
assert hashlib.sha256(a.read_bytes()).hexdigest()=={hashlib.sha256(archive.read_bytes()).hexdigest()!r}
patch=stage/'web-patch-02'
with tarfile.open(a) as tar:
    members=tar.getmembers()
    assert all(m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in members)
    hashes=json.load(tar.extractfile('web-manifest.json'))
    assert {{m.name for m in members}}==set(hashes)|{{'web-manifest.json'}}
    for name,digest in hashes.items():
        assert hashlib.sha256(tar.extractfile(name).read()).hexdigest()==digest
    patch.mkdir(exist_ok=False);tar.extractall(patch,filter='data')
shutil.copy2(web/'index.html',patch/'previous-index.html')
try:
    for name in hashes:
        if name!='index.html':
            dest=web/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(patch/name,dest)
    pending=web/'index.cr071-webfix.pending';shutil.copy2(patch/'index.html',pending);os.replace(pending,web/'index.html')
    assert all(hashlib.sha256((web/name).read_bytes()).hexdigest()==digest for name,digest in hashes.items())
except BaseException:
    pending=web/'index.cr071-webfix.pending';shutil.copy2(patch/'previous-index.html',pending);os.replace(pending,web/'index.html');raise
result={{'webPatch':'CR071 allocation description wrapping','sourceCommit':'361e3a2','files':hashes,'backendUnchanged':True}}
(patch/'deployment.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
""")
(out / "web-fix-deployment.json").write_bytes(result)
print(json.dumps({"patchedFiles": len(manifest), "backendUnchanged": True}))
