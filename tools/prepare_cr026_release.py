"""Build a reviewed local deployment archive with an explicit file allowlist."""
import hashlib
import io
import json
import tarfile
from pathlib import Path

OUTPUT = Path("artifacts/cr026-cloud-20260910")
PUBLICATION = Path("artifacts/cr024-publication-20260910")
CONFIGS = ["Dockerfile.backend", "compose.yml", "nginx.conf", "nginx-api.conf", "nginx-proxy.conf", "nginx-tls.conf"]


def main():
    OUTPUT.mkdir(exist_ok=False)
    files = {}
    for folder in ["services/algorithms/src", "services/backend/src"]:
        for path in Path(folder).rglob("*.py"):
            files[path.as_posix()] = path.read_bytes()
    for path in Path("apps/frontend/dist").rglob("*"):
        if path.is_file():
            files[path.as_posix()] = path.read_bytes()
    for name in CONFIGS:
        path = Path("deploy/mvp") / name
        files[path.as_posix()] = path.read_bytes()
    pointer = json.loads((PUBLICATION / "current.json").read_text())
    version = pointer["publicationId"]
    for relative in ["current.json", "releases/" + version + ".json"]:
        files["deploy/mvp/publication/" + relative] = (PUBLICATION / relative).read_bytes()
    manifest = {"publicationId": version, "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    files["release-manifest.json"] = json.dumps(manifest, sort_keys=True).encode()
    archive = OUTPUT / "release.tar.gz"
    with tarfile.open(archive, "w:gz") as target:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            target.addfile(info, io.BytesIO(data))
    summary = {"sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "fileCount": len(files), "publicationId": version}
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
