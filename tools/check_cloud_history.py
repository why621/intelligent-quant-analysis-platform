"""Windows SSH driver for six read-only cloud history probes; no deployment.

Only generated evidence is written locally under artifacts. Helpers are executed
in cloud memory; the installed provider, production files and caches are untouched.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
from pathlib import Path

REMOTE = '''
import base64, hashlib, inspect, json, platform, signal, sys, time, types
from datetime import date, datetime
from zoneinfo import ZoneInfo
import akshare, pandas
import quant_platform.data
from quant_platform.data.akshare_provider import AkShareMarketDataProvider
sources = json.loads(base64.b64decode('__SOURCES__'))
for short in ['coverage', 'history_probe']:
    source = sources[short]
    name = 'quant_platform.data.' + short
    module = types.ModuleType(name)
    module.__file__ = '<read-only-cloud-probe/' + short + '.py>'
    sys.modules[name] = module
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
from quant_platform.data.coverage import assess_history
from quant_platform.data.history_probe import probe
def emit(event, **values):
    print(json.dumps({'event': event, 'at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                      **values}, ensure_ascii=False, allow_nan=False), flush=True)
def deadline(signum, frame):
    raise TimeoutError('cloud sample exceeded 40 seconds')
signal.signal(signal.SIGALRM, deadline)
start, end = date(2025, 9, 7), date(2026, 9, 7)
symbols = ['600000', '600519', '688981', '000001', '002594', '300750']
emit('environment', python=platform.python_version(), akshare=akshare.__version__,
     pandas=pandas.__version__, symbols=symbols, start=str(start), end=str(end),
     providerSha256=hashlib.sha256(inspect.getsource(AkShareMarketDataProvider).encode()).hexdigest(),
     helperSha256={k: hashlib.sha256(v.encode()).hexdigest() for k, v in sources.items()},
     writesProductionData=False, maxRequests=30)
for symbol in symbols:
    signal.alarm(40)
    began = time.monotonic()
    try:
        result = probe({'symbol': symbol, 'start': str(start), 'end': str(end)})
        quality = None if result['error'] else assess_history(pandas.DataFrame(result['records']), start, end)
        emit('sample', symbol=symbol, seconds=round(time.monotonic()-began, 3),
             observation=result, quality=quality)
    except Exception as exc:
        emit('sample_error', symbol=symbol, errorType=type(exc).__name__)
    finally:
        signal.alarm(0)
    time.sleep(1)
emit('finished', samples=len(symbols))
'''


def prepare(root: Path, output: Path) -> tuple[Path, str]:
    artifacts, output = (root / "artifacts").resolve(), output.resolve()
    if output.parent != artifacts or output.exists():
        raise ValueError("output must be a NEW direct child of artifacts")
    sources = {name: (root / "services/algorithms/src/quant_platform/data" /
                      f"{name}.py").read_text(encoding="utf-8")
               for name in ("coverage", "history_probe")}
    encoded = base64.b64encode(json.dumps(sources).encode()).decode("ascii")
    program = REMOTE.replace("__SOURCES__", encoded)
    compile(program, "<cloud-history-probe>", "exec")
    return output, program


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output, program = prepare(root, args.output)
    if args.prepare_only:
        print("Python payload compiled; six samples; no SSH, HTTP or file writes")
        return
    command = [
        "C:/Windows/System32/OpenSSH/ssh.exe", "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", "HostKeyAlias=43.161.219.65",
        "-o", "UserKnownHostsFile=C:/Users/wangh/.ssh/known_hosts",
        "-o", "ConnectTimeout=10", "-o", "ConnectionAttempts=1",
        "-o", "IdentitiesOnly=yes", "-o", "ServerAliveInterval=10",
        "-o", "ServerAliveCountMax=3", "-i", "D:/quantserver.pem", "ubuntu@43.161.223.91",
        ("sudo -n docker exec -i -e PYTHONDONTWRITEBYTECODE=1 "
         "intelligent-quant-regression-backend-1 python -B -u -"),
    ]
    # Reserve local evidence location before any external action; no overwrite/retry.
    output.mkdir()
    try:
        result = subprocess.run(command, input=program, text=True, encoding="utf-8",
                                capture_output=True, timeout=300, check=False)
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or b""
        (output / "cloud-events.jsonl").write_bytes(raw if isinstance(raw, bytes) else raw.encode())
        raise
    (output / "cloud-events.jsonl").write_text(result.stdout, encoding="utf-8")
    (output / "exit.json").write_text(json.dumps({"sshExitCode": result.returncode}), encoding="utf-8")
    if result.returncode:
        print(result.stderr[-4000:])
        raise RuntimeError(f"SSH/probe failed: {result.returncode}; evidence retained")
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    for event in events:
        if event["event"] == "sample":
            observation, quality = event["observation"], event["quality"]
            print(json.dumps({"symbol": event["symbol"], "seconds": event["seconds"],
                              "error": observation["error"], "httpTrace": observation["httpTrace"],
                              "quality": quality}, ensure_ascii=False))
        else:
            print(json.dumps(event, ensure_ascii=False))
    if not events or events[-1].get("event") != "finished":
        raise RuntimeError("probe incomplete; do not infer source success")


if __name__ == "__main__":
    main()
