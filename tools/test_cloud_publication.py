import hashlib
import json
import sqlite3

import pytest

from tools.cloud_publication import (
    atomic_json,
    backup_restore,
    pending_jobs,
    promote,
    read_release,
)


def release(root, day):
    root.mkdir();(root / 'releases').mkdir()
    content={'schemaVersion':1,'endDate':day}
    version=hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    document={**content,'publicationId':version}
    atomic_json(root/'releases'/(version+'.json'),document)
    atomic_json(root/'current.json',{'publicationId':version})
    return version


def jobs(path, status='succeeded'):
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE backtest_jobs(job_id TEXT PRIMARY KEY,status TEXT, result_json TEXT)')
        db.execute('INSERT INTO backtest_jobs VALUES (?,?,?)',('job',status,'{"real":1}'))


def test_actual_restore_preserves_rows_and_rejects_reused_destination(tmp_path):
    source=tmp_path/'jobs.db';jobs(source)
    assert backup_restore(source,tmp_path/'backup')['restoredRows']==1
    assert pending_jobs(source)==0
    with pytest.raises(FileExistsError):backup_restore(source,tmp_path/'backup')


def test_failed_probe_restores_old_pointer_and_preserves_jobs(tmp_path):
    old=release(tmp_path/'live','2026-09-09');new=release(tmp_path/'candidate','2026-09-10')
    db=tmp_path/'jobs.db';jobs(db);restarts=[]
    def probe(version, day):
        if version==new:raise ValueError('synthetic health failure')
        assert version==old
    with pytest.raises(ValueError,match='synthetic'):
        promote(tmp_path/'candidate',tmp_path/'live',tmp_path/'backup',db,lambda:restarts.append(True),probe)
    assert read_release(tmp_path/'live')[0]['publicationId']==old
    assert len(restarts)==2
    with sqlite3.connect(db) as connection:assert connection.execute('SELECT result_json FROM backtest_jobs').fetchone()[0]=='{"real":1}'


def test_pending_jobs_prevent_any_switch_or_restart(tmp_path):
    old=release(tmp_path/'live','2026-09-09');release(tmp_path/'candidate','2026-09-10')
    db=tmp_path/'jobs.db';jobs(db,'running')
    with pytest.raises(ValueError,match='active jobs'):
        promote(tmp_path/'candidate',tmp_path/'live',tmp_path/'backup',db,lambda:pytest.fail('restart'),lambda *args:None)
    assert read_release(tmp_path/'live')[0]['publicationId']==old
    assert not (tmp_path/'backup').exists()


def test_success_and_tamper_detection(tmp_path):
    release(tmp_path/'live','2026-09-09');new=release(tmp_path/'candidate','2026-09-10')
    db=tmp_path/'jobs.db';jobs(db)
    result=promote(tmp_path/'candidate',tmp_path/'live',tmp_path/'backup',db,lambda:None,lambda version,day:None)
    assert result['status']=='promoted' and result['publicationId']==new
    file=tmp_path/'live'/'releases'/(new+'.json');doc=json.loads(file.read_text());doc['endDate']='2026-09-11';atomic_json(file,doc)
    with pytest.raises(ValueError,match='hash'):read_release(tmp_path/'live')


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('rollback', [False, True])
def test_restrictive_umask_publication_and_rollback(tmp_path, existing, rollback):
    import os
    import stat
    old = release(tmp_path/'live', '2026-09-14')
    new = release(tmp_path/'candidate', '2026-09-15')
    live = tmp_path/'live'
    db = tmp_path/'jobs.db'
    jobs(db)
    destination = live/'releases'/(new+'.json')
    if existing:
        destination.write_bytes((tmp_path/'candidate'/'releases'/(new+'.json')).read_bytes())
        destination.chmod(0o600)
    (live/'current.json').chmod(0o600)
    seen = []
    def restart():
        version = json.loads((live/'current.json').read_text())['publicationId']
        for path in [live/'current.json', live/'releases'/(version+'.json')]:
            assert stat.S_IMODE(path.stat().st_mode) == 0o644
        seen.append(version)
    def probe(version, day):
        if rollback and version == new:
            raise ValueError('forced probe failure')
    previous = os.umask(0o077)
    try:
        if rollback:
            with pytest.raises(ValueError, match='forced probe'):
                promote(tmp_path/'candidate', live, tmp_path/'backup', db, restart, probe)
        else:
            promote(tmp_path/'candidate', live, tmp_path/'backup', db, restart, probe)
        for name in ['previous-pointer.json', 'evidence.json']:
            assert stat.S_IMODE((tmp_path/'backup'/name).stat().st_mode) == 0o600
    finally:
        os.umask(previous)
    assert seen == ([new, old] if rollback else [new])
