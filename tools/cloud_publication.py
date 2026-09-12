"""Cloud promotion primitives: preserve jobs, atomically switch, rollback on failed probe."""
import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read_release(root):
    root = Path(root)
    pointer = json.loads((root / "current.json").read_text())
    version = pointer["publicationId"]
    if not re.fullmatch(r"[0-9a-f]{64}", version):
        raise ValueError("invalid release identity")
    raw = (root / "releases" / (version + ".json")).read_bytes()
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError("release oversized")
    document = json.loads(raw)
    content = {key: value for key, value in document.items() if key != "publicationId"}
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if document["publicationId"] != version or hashlib.sha256(canonical).hexdigest() != version:
        raise ValueError("release content hash mismatch")
    return pointer, document


def backup_restore(source, directory):
    """Online consistent snapshot, then actual restore into a separate database."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    with (closing(sqlite3.connect("file:" + str(Path(source).resolve()) + "?mode=ro", uri=True)) as origin,
          closing(sqlite3.connect(directory / "backup.db")) as backup):
        origin.backup(backup)
        if backup.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("backup integrity failure")
        with closing(sqlite3.connect(directory / "restored.db")) as restored:
            backup.backup(restored)
            if restored.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("restore integrity failure")
            before = list(backup.iterdump())
            after = list(restored.iterdump())
            if before != after:
                raise ValueError("restore differs from consistent backup")
            count = restored.execute("SELECT count(*) FROM backtest_jobs").fetchone()[0]
    result = {"integrity": "ok", "restoredRows": count, "logicalSha256": hashlib.sha256("\n".join(before).encode()).hexdigest()}
    atomic_json(directory / "evidence.json", result)
    return result


def pending_jobs(database):
    with sqlite3.connect("file:" + str(Path(database).resolve()) + "?mode=ro", uri=True) as connection:
        return connection.execute("SELECT count(*) FROM backtest_jobs WHERE status IN ('queued','running')").fetchone()[0]


def promote(candidate, live, backup_directory, database, restart, probe):
    """Caller must block new submissions and hold the promotion lock."""
    pointer, document = read_release(candidate)
    old_pointer, old_document = read_release(live)
    if pointer["publicationId"] == old_pointer["publicationId"]:
        return {"status": "unchanged", "publicationId": pointer["publicationId"]}
    if document["endDate"] <= old_document["endDate"]:
        raise ValueError("candidate must advance the published trading day")
    if pending_jobs(database):
        raise ValueError("active jobs prevent promotion")
    restore = backup_restore(database, backup_directory)
    live = Path(live)
    atomic_json(Path(backup_directory) / "previous-pointer.json", old_pointer)
    destination = live / "releases" / (pointer["publicationId"] + ".json")
    if destination.exists():
        if json.loads(destination.read_text()) != document:
            raise ValueError("existing release differs")
    else:
        atomic_json(destination, document)
    try:
        atomic_json(live / "current.json", pointer)
        restart()
        probe(pointer["publicationId"], document["endDate"])
    except Exception:
        atomic_json(live / "current.json", old_pointer)
        restart()
        probe(old_pointer["publicationId"], old_document["endDate"])
        raise
    return {"status": "promoted", "publicationId": pointer["publicationId"], "endDate": document["endDate"], "restore": restore}
