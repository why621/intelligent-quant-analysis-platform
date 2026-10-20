"""CR070 explicit packaging/transport/build/validation/cutover actions; never auto-publish."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shlex
import subprocess
import tarfile
from pathlib import Path

from deploy_cloud_preview import OPTIONS, SCP, SSH, TARGET

STAGE = "/opt/intelligent-quant-cr070-20261020"
UPLOAD = "/home/ubuntu/cr070-upload-20261020"
ROOT = "/opt/intelligent-quant-cr026-20260910"


def remote(code, timeout=900):
    result = subprocess.run(
        [SSH, *OPTIONS, TARGET, "sudo -n python3 -"],
        input=code.encode(),
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            result.stderr.decode(errors="replace") + result.stdout.decode()
        )
    return result.stdout


def package(output):
    revision = subprocess.check_output(
        [
            "wsl",
            "-d",
            "Ubuntu",
            "--",
            "bash",
            "-lc",
            "cd /home/wangh/projects/智能量化分析平台/artifacts/cr065-worktree && git rev-parse HEAD",
        ],
        text=True,
    ).strip()
    # Only reviewed source, builds, and explicitly listed release files are packaged.
    files = {}
    for folder in (
        "services/algorithms/src/quant_platform",
        "services/backend/src/app",
    ):
        for path in Path(folder).rglob("*.py"):
            files[path.as_posix()] = path.read_bytes()
    for path in (output / "dist-cloud").rglob("*"):
        if path.is_file():
            files[
                "apps/frontend/dist/"
                + path.relative_to(output / "dist-cloud").as_posix()
            ] = path.read_bytes()
    assert "apps/frontend/dist/index.html" in files
    previous = Path("../cr069-universe/experiment/models")
    release = json.loads((previous / "release.json").read_bytes())
    additional = json.loads((output / "models/release.json").read_bytes())
    assert len(release["models"]) == 3 and len(additional["models"]) == 1
    for directory, entries in (
        (previous, release["models"]),
        (output / "models", additional["models"]),
    ):
        for entry in entries:
            for name in (
                "model.zip",
                "manifest.json",
                "evaluation.json",
                "cross-asset-evaluation.json",
            ):
                path = directory / entry["modelRef"] / name
                files["portfolio_models/" + entry["modelRef"] + "/" + name] = (
                    path.read_bytes()
                )
    release["models"].extend(additional["models"])
    files["portfolio_models/release.json"] = json.dumps(release, indent=2).encode()
    for name in (
        "verify_published_provider.py",
        "cloud_publication.py",
        "verify_masked_cloud.py",
    ):
        files["tools/" + name] = Path("tools", name).read_bytes()
    files["cloud-before.json"] = (output / "cloud-before.json").read_bytes()
    files["Dockerfile"] = (
        b"FROM quant-mvp-backend:cr069-r2\n"
        b"COPY services/algorithms/src/quant_platform /app/code/quant_platform\n"
        b"COPY services/backend/src/app /app/code/app\n"
        b"COPY portfolio_models /app/portfolio_models\n"
        b"COPY release-manifest.json /app/cr070-release.json\n"
        b"ENV QUANT_PORTFOLIO_RELEASE=/app/portfolio_models/release.json\n"
    )
    manifest = {
        "revision": revision,
        "purpose": "CR070_masked_portfolio_release",
        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
    }
    files["release-manifest.json"] = json.dumps(manifest, indent=2).encode()
    archive = output / "release.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, raw in files.items():
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(raw), 0o644
            tar.addfile(member, io.BytesIO(raw))
    result = {
        "revision": revision,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files": len(files),
        "bytes": archive.stat().st_size,
    }
    (output / "archive.json").write_text(json.dumps(result, indent=2))
    return json.dumps(result).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("package", "upload", "build", "validate", "cutover")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.action == "package":
        result = package(output)
    elif args.action == "upload":
        subprocess.run(
            [SSH, *OPTIONS, TARGET, "mkdir -p -m 700 " + shlex.quote(UPLOAD)],
            check=True,
            timeout=30,
        )
        subprocess.run(
            [
                SCP,
                *OPTIONS,
                str(output / "release.tar.gz"),
                TARGET + ":" + UPLOAD + "/release.tar.gz",
            ],
            check=True,
            timeout=300,
        )
        result = b'{"uploaded":"release.tar.gz"}'
    elif args.action == "build":
        expected = json.loads((output / "archive.json").read_bytes())["sha256"]
        result = remote(f"""
import hashlib,json,subprocess,tarfile
from pathlib import Path
stage=Path({STAGE!r});archive=Path({UPLOAD + "/release.tar.gz"!r})
assert not stage.exists()
assert hashlib.sha256(archive.read_bytes()).hexdigest()=={expected!r}
with tarfile.open(archive) as tar:
    members=tar.getmembers()
    assert all(m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in members)
    manifest=json.load(tar.extractfile('release-manifest.json'))
    assert len(members)==len(manifest['files'])+1
    assert {{m.name for m in members}}==set(manifest['files'])|{{'release-manifest.json'}}
    for name,digest in manifest['files'].items():
        assert hashlib.sha256(tar.extractfile(name).read()).hexdigest()==digest,name
    baseline=json.load(tar.extractfile('cloud-before.json'))
    image=subprocess.check_output(['docker','image','inspect','--format','{{{{.Id}}}}','quant-mvp-backend:cr069-r2'],text=True).strip()
    assert image==baseline['backend']['Image']
    stage.mkdir(mode=0o755);tar.extractall(stage,filter='data')
subprocess.run(['docker','build','--network','none','--pull=false','-t','quant-mvp-backend:cr070',str(stage)],check=True)
image=subprocess.check_output(['docker','image','inspect','--format','{{{{.Id}}}}','quant-mvp-backend:cr070'],text=True).strip()
(stage/'image-id').write_text(image)
print(json.dumps({{'image':image,'revision':manifest['revision']}}))
""")
    elif args.action == "validate":
        result = remote(
            f"""
import hashlib,json,subprocess
from pathlib import Path
stage=Path({STAGE!r});root=Path({ROOT!r});out=stage/'candidate'
out.mkdir(exist_ok=False);subprocess.run(['chown','999:999',str(out)],check=True)
baseline=json.loads((stage/'cloud-before.json').read_bytes())
expected=baseline['api']['status']['latestTradeDate']
args=['docker','run','--rm','--network','none','--read-only','--tmpfs','/tmp:size=256m','--memory','1g','--cpus','1.5',
'-e','PYTHONDONTWRITEBYTECODE=1','-v',str(root/'deploy/mvp/publication')+':/baseline:ro',
'-v','/opt/intelligent-quant-cr062-20261001/models:/models:ro',
'-v',str(root/'daily-cr028/tools/verify_published_provider.py')+':/input/verify_published_provider.py:ro',
'-v',str(stage/'tools/verify_masked_cloud.py')+':/input/verify.py:ro',
'-v',str(out)+':/output','--entrypoint','python',(stage/'image-id').read_text().strip(),
'/input/verify.py','--publication','/baseline','--rl-release','/models/rl-release.json',
'--portfolio-release','/app/portfolio_models/release.json','--verify-script','/input/verify_published_provider.py',
'--output','/output/validation.json','--expected-date',expected]
r=subprocess.run(args,text=True,capture_output=True,timeout=900)
(stage/'validation-stdout.txt').write_text(r.stdout);(stage/'validation-stderr.txt').write_text(r.stderr)
assert r.returncode==0,(r.stdout,r.stderr)
v=json.loads((out/'validation.json').read_text())
assert v['passed'] and v['catalogCount']==10 and len(v['jobs'])==25
assert len(v['ranking']['items'])==6 and len(v['allocations'])==8 and v['cr067DailyIsolation']['passed']
v['candidate']={{'image':(stage/'image-id').read_text().strip(),'revision':json.loads((stage/'release-manifest.json').read_text())['revision'],'manifestSha256':hashlib.sha256((stage/'release-manifest.json').read_bytes()).hexdigest()}}
(stage/'validation.json').write_text(json.dumps(v,indent=2))
print(json.dumps(v))
""",
            timeout=1000,
        )
    else:
        result = remote(Path("tools/deploy_cr070_cutover.py").read_text(), timeout=900)
    (output / ("cloud-" + args.action + ".txt")).write_bytes(result)
    print(result.decode(errors="replace"))


if __name__ == "__main__":
    main()
