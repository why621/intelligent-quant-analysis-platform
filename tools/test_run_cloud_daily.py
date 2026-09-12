import json
import sys

import pytest

from tools import daily_publication as daily
from tools import run_cloud_daily as cloud


def test_progress_is_separate_from_result(monkeypatch, capsys):
    def execute(*args, **kwargs):
        print('{"symbol":"600000","status":"complete"}')
        print('510300 complete')
        return {'decision': 'succeeded', 'state': {'attempts': []}}
    monkeypatch.setattr(daily, 'execute', execute)
    monkeypatch.setattr(daily.signal, 'signal', lambda *a: None)
    monkeypatch.setattr(daily.signal, 'alarm', lambda *a: None)
    monkeypatch.setattr(sys, 'argv', ['daily', '--trigger', 'scheduled'])
    daily.main()
    captured = capsys.readouterr()
    assert cloud.parse_outcome(captured.out)['decision'] == 'succeeded'
    assert '600000' in captured.err and '510300 complete' in captured.err
    assert '600000' not in captured.out


@pytest.mark.parametrize('output', ['', '{}', '[]', '{"decision":"unknown"}',
                                      '{"symbol":"600000"}\n{"decision":"succeeded"}'])
def test_invalid_or_mixed_output_rejected(output):
    with pytest.raises((ValueError, TypeError)):
        cloud.parse_outcome(output)


def test_existing_candidate_never_acquires(monkeypatch, tmp_path):
    root = tmp_path
    d = root / 'daily'
    c = d / 'artifacts/cr025-daily-20260910'
    (c / 'publication').mkdir(parents=True)
    (root / 'deploy/mvp/nginx-live').mkdir(parents=True)
    (d / 'audit').mkdir()
    state = c / 'state.json'
    state.write_text(json.dumps({'attempts': [{'status': 'succeeded', 'publicationId': 'a'*64}]}))
    original = state.read_bytes()
    (c / 'publication/current.json').write_text(json.dumps({'publicationId':'a'*64}))
    monkeypatch.setattr(cloud, 'ROOT', root)
    monkeypatch.setattr(cloud, 'DAILY', d)
    monkeypatch.setattr(sys, 'argv', ['runner', '--promote-existing'])
    def forbidden(*args, **kwargs):
        raise AssertionError('acquisition must never run')
    monkeypatch.setattr(cloud, 'runtime', forbidden)
    monkeypatch.setattr(cloud.subprocess, 'run', forbidden)
    monkeypatch.setattr(cloud, 'command', lambda *a, **k: 'ActiveState=active')
    monkeypatch.setattr(cloud, 'pending_jobs', lambda *a: 0)
    calls = []
    monkeypatch.setattr(cloud, 'promote', lambda *a: calls.append(a) or {'status': 'published'})
    cloud.main()
    assert len(calls) == 1 and state.read_bytes() == original
    audit = json.loads(next((d/'audit').glob('*.json')).read_text())
    assert audit['mode'] == 'manual_existing_candidate' and audit['invocationId'] is None
    assert not (root/'deploy/mvp/nginx-live/maintenance.enabled').exists()


@pytest.mark.parametrize('decision', ['succeeded', 'failed', 'already_attempted'])
def test_real_child_process_output_contract(decision):
    import subprocess
    script = """import sys
from tools import daily_publication as d
decision=sys.argv[1]
def execute(*a, **k):
    print('{"symbol":"600000"}')
    print('510300 complete')
    return {'decision':decision}
d.execute=execute
sys.argv=['daily']
d.main()
"""
    result = subprocess.run([sys.executable, '-c', script, decision], capture_output=True,
                            text=True, timeout=30, check=False)
    assert result.returncode == (1 if decision == 'failed' else 0), result.stderr
    assert cloud.parse_outcome(result.stdout) == {'decision': decision}
    assert '600000' in result.stderr and '510300 complete' in result.stderr


@pytest.mark.parametrize('scenario', ['mixed_output', 'nonzero_exit', 'version_mismatch',
                                     'promotion_failure', 'preexisting_maintenance', 'worker_timeout'])
def test_runner_failure_protection(monkeypatch, tmp_path, scenario):
    import subprocess
    from types import SimpleNamespace
    d = tmp_path / 'daily'
    c = d / 'artifacts/cr025-daily-20260910'
    (c / 'publication').mkdir(parents=True)
    (d / 'audit').mkdir()
    maintenance = tmp_path/'deploy/mvp/nginx-live/maintenance.enabled'
    maintenance.parent.mkdir(parents=True)
    state = c/'state.json'
    state.write_text(json.dumps({'attempts':[{'status':'succeeded','publicationId':'a'*64}]}))
    original = state.read_bytes()
    (c/'publication/current.json').write_text(json.dumps({'publicationId':('b' if scenario == 'version_mismatch' else 'a')*64}))
    if scenario == 'preexisting_maintenance':
        maintenance.write_text('owned by another operator')
    monkeypatch.setattr(cloud, 'ROOT', tmp_path)
    monkeypatch.setattr(cloud, 'DAILY', d)
    monkeypatch.setattr(sys, 'argv', ['runner'])
    monkeypatch.setattr(cloud, 'command', lambda *a, **k:'ActiveState=active')
    monkeypatch.setattr(cloud, 'runtime', lambda *a:['mock-worker'])
    def worker(*a, **k):
        if scenario == 'worker_timeout':
            raise subprocess.TimeoutExpired('mock-worker', 5520)
        return SimpleNamespace(returncode=1 if scenario == 'nonzero_exit' else 0,
            stdout=('510300 complete\n' if scenario == 'mixed_output' else '')+'{"decision":"succeeded"}', stderr='progress')
    monkeypatch.setattr(cloud.subprocess, 'run', worker)
    monkeypatch.setattr(cloud, 'pending_jobs', lambda *a:0)
    calls=[]
    def promote(*a):
        calls.append(True)
        raise ValueError('injected promotion failure')
    monkeypatch.setattr(cloud, 'promote', promote)
    with pytest.raises((ValueError, RuntimeError, FileExistsError, subprocess.TimeoutExpired)):
        cloud.main()
    assert calls == ([True] if scenario == 'promotion_failure' else [])
    assert state.read_bytes() == original
    if scenario == 'preexisting_maintenance':
        assert maintenance.read_text() == 'owned by another operator'
    else:
        assert not maintenance.exists()
    audit=json.loads(next((d/'audit').glob('*.json')).read_text())
    assert 'failure' in audit and 'finishedAt' in audit and 'promotion' not in audit
