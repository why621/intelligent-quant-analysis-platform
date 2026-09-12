"""Fixed cloud daily acceptance runner; no hidden retries or budget expansion."""
import argparse
import fcntl
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from tools.cloud_publication import atomic_json, pending_jobs, promote

ROOT = Path('/opt/intelligent-quant-cr026-20260910')
DAILY = ROOT / 'daily-cr028'
LIVE = ROOT / 'deploy/mvp/publication'
DB = ROOT / 'deploy/mvp/jobs/backtests.db'
CONTAINER = 'quant-mvp-cr026-backend-1'


def command(arguments, timeout=120):
    return subprocess.run(arguments, capture_output=True, text=True, timeout=timeout, check=True).stdout


def runtime(dry):
    image = (DAILY / 'image-id').read_text().strip()
    if not image.startswith('sha256:') or len(image) != 71:
        raise ValueError('fixed image digest required')
    args = ['docker', 'run', '--rm', '--init', '--name', 'quant-mvp-daily-cr028',
            '--user', '0:0', '--network', 'none' if dry else 'bridge', '--cpus', '1', '--memory', '768m',
            '--pids-limit', '128', '--read-only', '--tmpfs', '/tmp:size=128m',
            '--security-opt', 'no-new-privileges', '--cap-drop', 'ALL',
            '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'PYTHONPATH=/app/code:/work', '-w', '/work']
    mounts = [(DAILY / 'tools', '/work/tools', True), (DAILY / 'config', '/work/config', True),
              (DAILY / 'artifacts', '/work/artifacts', False),
              (LIVE, '/work/artifacts/cr024-publication-20260910', True)]
    for source, target, readonly in mounts:
        args += ['--mount', 'type=bind,src=' + str(source) + ',dst=' + target + (',readonly' if readonly else '')]
    trigger = 'scheduled' if os.environ.get('INVOCATION_ID') else 'manual'
    args += ['--entrypoint', 'python', image, '-m', 'tools.daily_publication', '--trigger', trigger]
    if dry:
        args.append('--dry-run')
    return args


def probe(version, end):
    script = "import json,urllib.request; s=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/data/status',timeout=10)); o=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/market/overview',timeout=10)); print(json.dumps({'status':s,'overview':o}))"
    result = json.loads(command(['docker', 'exec', CONTAINER, 'python', '-c', script], timeout=30))
    status, overview = result['status'], result['overview']
    if status['assetCount'] != 327 or status['dataContext']['dataVersion'] != version or status['latestTradeDate'] != end:
        raise ValueError('cloud status gate failed')
    if overview['dataContext'] != status['dataContext'] or overview['coverage']['priced'] != 300:
        raise ValueError('cloud overview gate failed')


def restart():
    command(['docker', 'restart', '-t', '30', CONTAINER], timeout=60)
    for _ in range(30):
        health = command(['docker', 'inspect', '--format', '{{.State.Health.Status}}', CONTAINER]).strip()
        if health == 'healthy':
            return
        time.sleep(2)
    raise TimeoutError('backend readiness timeout')


def parse_outcome(output):
    value = json.loads(output)
    decisions = {'succeeded', 'failed', 'already_attempted', 'waiting_new_day',
                 'budget_exhausted', 'two_day_candidate_requires_scheduler_audit', 'eligible'}
    if not isinstance(value, dict) or value.get('decision') not in decisions:
        raise ValueError('invalid worker outcome')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--dry-run', action='store_true')
    modes.add_argument('--promote-existing', action='store_true', help='Publish successful candidate without acquisition')
    args = parser.parse_args()
    with (DAILY / 'runner.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.dry_run:
            print(command(runtime(True), timeout=90))
            return
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        audit = {'startedAt': datetime.now(timezone.utc).isoformat(), 'invocationId': os.environ.get('INVOCATION_ID'),
                 'timerObservation': command(['systemctl', 'show', 'quant-mvp-daily.timer', '-p', 'LastTriggerUSec', '-p', 'ActiveState']).strip(),
                 'schedulerOriginVerified': False}
        sentinel = ROOT / 'deploy/mvp/nginx-live/maintenance.enabled'
        owns_sentinel = False
        try:
            if args.promote_existing:
                audit['mode'] = 'manual_existing_candidate'
                audit['invocationId'] = None
                outcome = {'decision': 'promote_existing'}
            else:
                result = subprocess.run(runtime(False), capture_output=True, text=True, timeout=5520, check=False)
                audit['workerExit'] = result.returncode
                audit['workerOutput'] = result.stdout[-20000:]
                audit['workerError'] = result.stderr[-4000:]
                if result.returncode:
                    raise RuntimeError('bounded daily worker failed; inspect persistent candidate ledger')
                outcome = parse_outcome(result.stdout)
            audit['decision'] = outcome['decision']
            state = json.loads((DAILY / 'artifacts/cr025-daily-20260910/state.json').read_text())
            if outcome['decision'] in ('budget_exhausted', 'two_day_candidate_requires_scheduler_audit'):
                command(['systemctl', 'disable', '--now', 'quant-mvp-daily.timer'])
            successes = [a for a in state['attempts'] if a['status'] == 'succeeded']
            if args.promote_existing and (not successes or state['attempts'][-1]['status'] != 'succeeded'):
                raise ValueError('latest attempt must be successful for existing-candidate publication')
            if successes:
                candidate = DAILY / 'artifacts/cr025-daily-20260910/publication'
                current = json.loads((candidate / 'current.json').read_text())['publicationId']
                if current != successes[-1]['publicationId']:
                    raise ValueError('candidate differs from success ledger')
                # Nginx configuration must block new submissions while this file exists.
                sentinel.touch(exist_ok=False)
                owns_sentinel = True
                for _ in range(24):
                    if pending_jobs(DB) == 0:
                        break
                    time.sleep(5)
                audit['promotion'] = promote(candidate, LIVE, DAILY / 'backups' / stamp, DB, restart, probe)
        except Exception as error:
            audit['failure'] = type(error).__name__ + ': ' + str(error)[:2000]
            raise
        finally:
            if owns_sentinel and sentinel.exists():
                sentinel.unlink()
            audit['finishedAt'] = datetime.now(timezone.utc).isoformat()
            atomic_json(DAILY / 'audit' / (stamp + '.json'), audit)


if __name__ == '__main__':
    main()
