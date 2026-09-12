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
