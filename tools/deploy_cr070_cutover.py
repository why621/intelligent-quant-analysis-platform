"""Authorized CR070 service/web cutover; daily runtime and live data stay unchanged."""

import fcntl
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

root = Path("/opt/intelligent-quant-cr026-20260910")
stage = Path("/opt/intelligent-quant-cr070-20261020-r2")
daily = root / "daily-cr028"
live = root / "deploy/mvp/publication"
models = Path("/opt/intelligent-quant-cr062-20261001/models")
sys.path.insert(0, str(daily))
from tools import run_cloud_daily as cloud
from tools.cloud_publication import atomic_json, backup_restore, pending_jobs

os.chdir(daily)
os.umask(0o077)
lock = (daily / "runner.lock").open("a")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
v = json.loads((stage / "validation.json").read_text())
manifest = json.loads((stage / "release-manifest.json").read_text())
assert (
    v["passed"]
    and v["catalogCount"] == 10
    and v["applicableAssets"] == 327
    and len(v["jobs"]) == 25
)
assert all(j["status"] == "succeeded" for j in v["jobs"])
assert (
    len(v["ranking"]["items"]) == 6
    and len(v["allocations"]) == 8
    and v["cr067DailyIsolation"]["passed"]
)
pointer = (live / "current.json").read_bytes()
version = json.loads(pointer)["publicationId"]
assert version == v["context"]["dataVersion"]
old_image = cloud.command(
    ["docker", "inspect", "--format", "{{.Image}}", cloud.CONTAINER]
).strip()
baseline = json.loads((stage / "cloud-before.json").read_text())
assert old_image == baseline["backend"]["Image"]
new_image = (stage / "image-id").read_text().strip()
assert (
    new_image
    == cloud.command(
        ["docker", "image", "inspect", "--format", "{{.Id}}", "quant-mvp-backend:cr070-r2"]
    ).strip()
)
assert v["candidate"] == {
    "image": new_image,
    "revision": manifest["revision"],
    "manifestSha256": hashlib.sha256(
        (stage / "release-manifest.json").read_bytes()
    ).hexdigest(),
}


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


model_hashes = {
    str(p.relative_to(models)): digest(p) for p in models.rglob("*") if p.is_file()
}
tracked = [
    daily / "image-id",
    daily / "artifacts/cr025-daily-20260910/state.json",
    daily / "artifacts/continuous-daily/state.json",
    daily / "tools/run_cloud_daily.py",
    daily / "tools/verify_published_provider.py",
    daily / "tools/recover_daily_publication.py",
]
hashes = {str(p): digest(p) for p in tracked}
assert (daily / "image-id").read_text().strip() == baseline["dailyImage"]
timer_before = cloud.command(["systemctl", "cat", "quant-mvp-daily.timer"])
assert (
    cloud.command(["systemctl", "is-active", "quant-mvp-daily.timer"]).strip()
    == "active"
)
backup = stage / "backup"
backup.mkdir(mode=0o700)
compose = root / "deploy/mvp/compose.yml"
shutil.copy2(compose, backup / "compose.yml")
folders = ["services/algorithms/src/quant_platform", "services/backend/src/app"]
for folder in folders:
    shutil.copytree(root / folder, backup / folder)
web = root / "apps/frontend/dist"
shutil.copytree(web, backup / "web")
old_web = digest(web / "index.html")
expected_mounts = {
    ("/opt/intelligent-quant-cr062-20261001/models", "/app/models", False),
    (str(live), "/app/publication", False),
    (str(root / "deploy/mvp/jobs"), "/app/var", True),
}


def check_runtime():
    state = json.loads(cloud.command(["docker", "inspect", cloud.CONTAINER]))[0]
    assert {
        (m["Source"], m["Destination"], m["RW"]) for m in state["Mounts"]
    } == expected_mounts
    env = dict(x.split("=", 1) for x in state["Config"]["Env"])
    assert (
        env["QUANT_RL_RELEASE"] == "/app/models/rl-release.json"
        and env["QUANT_PORTFOLIO_RELEASE"] == "/app/portfolio_models/release.json"
    )


check_runtime()
config = json.loads(
    cloud.command(
        ["docker", "compose", "-f", str(compose), "config", "--format", "json"]
    )
)["services"]["backend"]
assert {
    (m["source"], m["target"], not m.get("read_only", False)) for m in config["volumes"]
} == expected_mounts
sentinel = root / "deploy/mvp/nginx-live/maintenance.enabled"
sentinel.touch(exist_ok=False)
changed = False
recovered = True


def wait_ready():
    for _ in range(40):
        if (
            cloud.command(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{.State.Health.Status}}",
                    cloud.CONTAINER,
                ]
            ).strip()
            == "healthy"
        ):
            return
        time.sleep(2)
    raise RuntimeError("candidate readiness timeout")


def publish_web(source):
    for path in source.rglob("*"):
        if path.is_file() and path.relative_to(source).as_posix() != "index.html":
            dest = web / path.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
    pending = web / "index.cr070.pending"
    shutil.copy2(source / "index.html", pending)
    os.replace(pending, web / "index.html")


def reload_gateway():
    cloud.command(["docker", "exec", "quant-mvp-cr026-gateway-1", "nginx", "-t"])
    cloud.command(
        ["docker", "exec", "quant-mvp-cr026-gateway-1", "nginx", "-s", "reload"]
    )


try:
    for _ in range(24):
        if pending_jobs(cloud.DB) == 0:
            break
        time.sleep(5)
    assert pending_jobs(cloud.DB) == 0, "pending jobs prevent cutover"
    before = backup_restore(cloud.DB, backup / "jobs")
    assert before["logicalSha256"] == baseline["jobs"]["logicalSha256"]
    text = compose.read_text()
    assert text.count("image: quant-mvp-backend:cr069-r2") == 1
    assert "/opt/intelligent-quant-cr062-20261001/models:/app/models:ro" in text
    changed = True
    recovered = False
    compose.write_text(
        text.replace(
            "image: quant-mvp-backend:cr069-r2", "image: quant-mvp-backend:cr070-r2"
        )
    )
    cloud.command(["docker", "compose", "-f", str(compose), "config", "--quiet"])
    cloud.command(
        [
            "docker",
            "compose",
            "-f",
            str(compose),
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "backend",
        ]
    )
    wait_ready()
    assert (
        cloud.command(
            ["docker", "inspect", "--format", "{{.Image}}", cloud.CONTAINER]
        ).strip()
        == new_image
    )
    check_runtime()
    reload_gateway()
    cloud.probe(version, v["overviewDate"])
    script = """import json,time,urllib.request
g=lambda p:json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/'+p,timeout=40))
s=g('strategies');catalog={x['id']:x for x in s['items']}
assert len(catalog)==10
models={k:x['modelContext']['bundleHash'] for k,x in catalog.items() if x.get('backtestEnabled')}
assert all(catalog[k]['modelContext']['assetScope']=='published_universe' for k in ['portfolio_ppo','portfolio_sac','portfolio_td3','portfolio_masked_sac'])
old=g('strategies/ranking?period=30d');assert len(old['items'])==6 and not old['unavailableStrategies']
print(json.dumps({'models':models,'legacyRankingCount':len(old['items'])}))
"""
    check = json.loads(
        cloud.command(
            ["docker", "exec", cloud.CONTAINER, "python", "-c", script], timeout=70
        )
    )
    assert check["models"] == {**v["oldModelHashes"], **v["newModelHashes"]}
    request_script = (
        "import json,time,urllib.request; payload="
        + repr(v["ranking"]["request"])
        + "; t=time.monotonic(); req=urllib.request.Request('http://127.0.0.1:8000/api/strategies/ranking',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-Research-Version':"
        + repr(version)
        + "}); result=json.load(urllib.request.urlopen(req,timeout=45)); print(json.dumps({'seconds':time.monotonic()-t,'response':result}))"
    )
    current = json.loads(
        cloud.command(
            ["docker", "exec", cloud.CONTAINER, "python", "-c", request_script],
            timeout=60,
        )
    )
    assert current["response"]["request"] == v["ranking"]["request"]
    assert current["response"]["items"] == v["ranking"]["items"]
    dry = json.loads(cloud.command(cloud.runtime(True, "continuous"), timeout=90))
    assert (
        dry["dryRun"]
        and dry["mode"] == "continuous"
        and dry["decision"] in {"waiting_new_day", "already_attempted", "eligible"}
    )
    assert (live / "current.json").read_bytes() == pointer and all(
        digest(Path(p)) == h for p, h in hashes.items()
    )
    assert model_hashes == {
        str(p.relative_to(models)): digest(p) for p in models.rglob("*") if p.is_file()
    }
    assert cloud.command(["systemctl", "cat", "quant-mvp-daily.timer"]) == timer_before
    assert (
        cloud.command(["systemctl", "is-active", "quant-mvp-daily.timer"]).strip()
        == "active"
    )
    after = backup_restore(cloud.DB, backup / "jobs-after")
    assert before["logicalSha256"] == after["logicalSha256"]
    for folder in folders:
        shutil.copytree(stage / folder, root / folder, dirs_exist_ok=True)
    publish_web(stage / "apps/frontend/dist")
    assert digest(web / "index.html") == digest(stage / "apps/frontend/dist/index.html")
    result = {
        "revision": manifest["revision"],
        "image": new_image,
        "previousImage": old_image,
        "publicationUnchanged": version,
        "oldModelsUnchanged": model_hashes,
        "newModels": v["newModelHashes"],
        "jobsBefore": before,
        "jobsAfter": after,
        "researchRankingSeconds": current["seconds"],
        "researchRankingRows": len(current["response"]["items"]),
        "dryRun": dry,
        "dailyRuntimeAndToolsUnchanged": hashes,
        "timerConfigUnchanged": True,
        "timerActive": True,
        "backup": str(backup),
        "oldWebIndexSha256": old_web,
        "webIndexSha256": digest(web / "index.html"),
        "rollbackTriggered": False,
    }
    atomic_json(stage / "deployment.json", result)
    recovered = True
    print(json.dumps(result))
except BaseException as error:
    if changed:
        recovered = False
        shutil.copy2(backup / "compose.yml", compose)
        for folder in folders:
            shutil.copytree(backup / folder, root / folder, dirs_exist_ok=True)
        publish_web(backup / "web")
        cloud.command(
            [
                "docker",
                "compose",
                "-f",
                str(compose),
                "up",
                "-d",
                "--no-deps",
                "--no-build",
                "backend",
            ]
        )
        wait_ready()
        check_runtime()
        reload_gateway()
        cloud.probe(version, v["overviewDate"])
        assert (
            cloud.command(
                ["docker", "inspect", "--format", "{{.Image}}", cloud.CONTAINER]
            ).strip()
            == old_image
        )
        assert digest(web / "index.html") == old_web
        assert (live / "current.json").read_bytes() == pointer and all(
            digest(Path(p)) == h for p, h in hashes.items()
        )
        for folder in folders:
            previous = {
                str(p.relative_to(backup / folder))
                for p in (backup / folder).rglob("*")
                if p.is_file()
            }
            for path in (stage / folder).rglob("*"):
                if (
                    path.is_file()
                    and str(path.relative_to(stage / folder)) not in previous
                ):
                    target = root / folder / path.relative_to(stage / folder)
                    assert target.resolve().is_relative_to((root / folder).resolve())
                    target.unlink(missing_ok=True)
        recovered = True
        rollback = {
            "status": "rolled_back",
            "rollbackTriggered": True,
            "previousImage": old_image,
            "failedCandidate": new_image,
            "reason": str(error),
            "oldWebIndexSha256": old_web,
            "publicationUnchanged": version,
        }
        atomic_json(stage / "rollback.json", rollback)
        if (stage / "deployment.json").exists():
            atomic_json(stage / "deployment.json", rollback)
    raise
finally:
    if recovered:
        sentinel.unlink(missing_ok=True)
