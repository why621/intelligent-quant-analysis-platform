"""Filesystem model repository: ``<root>/<run-id>/{model.zip, manifest.json}``.

Weights never enter git — the repo root ``/models`` is gitignored. Each bundle
records the immutable publication it was trained on so inference can prove the
backtest range is out-of-sample and refuse otherwise.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from quant_platform.rl.errors import RLModelNotFound

RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")

REQUIRED_MANIFEST_KEYS: tuple[str, ...] = (
    "algo",
    "seed",
    "featureSignature",
    "publicationDate",
    "dataVersion",
    "universeVersion",
    "trainStartDate",
    "trainEndDate",
    "codeSha",
)


@dataclass(frozen=True)
class ModelBundle:
    run_id: str
    manifest: dict[str, object]
    model_bytes: bytes


def content_hash(model_bytes: bytes) -> str:
    return hashlib.sha256(model_bytes).hexdigest()


class ModelStore:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def _dir(self, run_id: str) -> Path:
        if not RUN_ID_RE.fullmatch(run_id):
            raise RLModelNotFound(f"invalid run id: {run_id!r}")
        target = (self._root / run_id).resolve()
        if not target.is_relative_to(self._root):
            raise RLModelNotFound("run id escapes model root")
        return target

    def save(self, run_id: str, model_bytes: bytes, manifest: dict[str, object]) -> Path:
        missing = set(REQUIRED_MANIFEST_KEYS) - set(manifest)
        if missing:
            raise ValueError(f"manifest missing keys: {sorted(missing)}")
        directory = self._dir(run_id)
        document = {
            **manifest,
            "runId": run_id,
            "contentHash": content_hash(model_bytes),
            "modelSizeBytes": len(model_bytes),
        }
        directory.mkdir(parents=True, exist_ok=True)
        self._atomic_write(directory / "model.zip", model_bytes)
        payload = json.dumps(document, sort_keys=True, ensure_ascii=False).encode("utf-8")
        self._atomic_write(directory / "manifest.json", payload)
        return directory

    def load(self, run_id: str) -> ModelBundle:
        directory = self._dir(run_id)
        model_path = directory / "model.zip"
        manifest_path = directory / "manifest.json"
        if not model_path.exists() or not manifest_path.exists():
            raise RLModelNotFound(f"no trained model for {run_id!r} under {self._root}")
        model_bytes = model_path.read_bytes()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if content_hash(model_bytes) != manifest.get("contentHash"):
            raise RLModelNotFound(f"model bundle failed content hash check: {run_id!r}")
        return ModelBundle(run_id=run_id, manifest=manifest, model_bytes=model_bytes)

    def exists(self, run_id: str) -> bool:
        try:
            directory = self._dir(run_id)
        except RLModelNotFound:
            return False
        return (directory / "model.zip").exists() and (directory / "manifest.json").exists()

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        staged = tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}-", delete=False
        )
        try:
            staged.write(data)
            staged.flush()
            os.fsync(staged.fileno())
        finally:
            staged.close()
        os.replace(staged.name, path)
