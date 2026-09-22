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
from datetime import date
from pathlib import Path

from quant_platform.rl.errors import RLError, RLIncompatibleModel, RLModelNotFound

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
    "executionVersion",
)

# Bundles trained before CR-052 legitimately omit these; a bundle that records
# them must record a coherent, non-overlapping set of windows.
OPTIONAL_SPLIT_KEYS: tuple[str, ...] = (
    "valStartDate",
    "valEndDate",
    "testStartDate",
    "testEndDate",
)


@dataclass(frozen=True)
class ModelBundle:
    run_id: str
    manifest: dict[str, object]
    model_bytes: bytes


def content_hash(model_bytes: bytes) -> str:
    return hashlib.sha256(model_bytes).hexdigest()


def validate_training_dates(manifest):
    try:
        values = [manifest[k] for k in ("trainStartDate", "trainEndDate")]
        if any(not isinstance(v, str) or date.fromisoformat(v).isoformat() != v for v in values):
            raise ValueError("non-canonical date")
        if values[0] >= values[1]:
            raise ValueError("reversed training interval")
    except (KeyError, TypeError, ValueError) as exc:
        raise RLIncompatibleModel("模型训练日期缺失或无效，拒绝推理") from exc


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise RLIncompatibleModel("manifest must be an object")
    missing = set(REQUIRED_MANIFEST_KEYS) - set(manifest)
    if missing:
        raise RLIncompatibleModel(f"manifest missing keys: {sorted(missing)}")
    for key in REQUIRED_MANIFEST_KEYS:
        if key != "seed" and (not isinstance(manifest[key], str) or not manifest[key].strip()):
            raise RLIncompatibleModel(f"invalid manifest field: {key}")
    if type(manifest["seed"]) is not int or manifest["seed"] < 0:
        raise RLIncompatibleModel("invalid model seed")
    if manifest["algo"] not in {"dqn", "ppo", "sac", "ddpg"}:
        raise RLIncompatibleModel("invalid model algorithm")
    validate_training_dates(manifest)
    validate_split_dates(manifest)
    try:
        publication = manifest["publicationDate"]
        if date.fromisoformat(publication).isoformat() != publication:
            raise ValueError("non-canonical publication date")
        if publication < manifest["trainEndDate"]:
            raise ValueError("publication predates training end")
        in_sample = manifest.get("valEndDate") or manifest["trainEndDate"]
        if publication < in_sample:
            raise ValueError("publication predates validation end")
    except (TypeError, ValueError) as exc:
        raise RLIncompatibleModel("invalid publication date") from exc


def validate_split_dates(manifest):
    """Reject recorded train/validation/test windows that overlap or are misformed.

    Bundles without the CR-052 keys are left untouched so already published
    weights stay loadable; only bundles that claim a validation window are held
    to it.
    """
    recorded = [key for key in OPTIONAL_SPLIT_KEYS if key in manifest]
    if not recorded:
        return
    for key in recorded:
        if not isinstance(manifest[key], str):
            raise RLIncompatibleModel(f"invalid manifest field: {key}")
    from quant_platform.rl.splits import split_from_manifest

    try:
        split_from_manifest(manifest)
    except RLError as exc:
        raise RLIncompatibleModel(f"模型记录的样本内区间无效：{exc}") from exc


def bundle_hash(model_bytes: bytes, manifest: dict) -> str:
    metadata = {k: v for k, v in manifest.items() if k != "bundleHash"}
    encoded = json.dumps(metadata, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(len(encoded).to_bytes(8, "big") + encoded + model_bytes).hexdigest()


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
        validate_manifest(manifest)
        directory = self._dir(run_id)
        document = {
            **manifest,
            "schemaVersion": 2,
            "runId": run_id,
            "contentHash": content_hash(model_bytes),
            "modelSizeBytes": len(model_bytes),
        }
        document["bundleHash"] = bundle_hash(model_bytes, document)
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
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise RLIncompatibleModel("invalid manifest JSON") from exc
        validate_manifest(manifest)
        if type(manifest.get("schemaVersion")) is not int or manifest["schemaVersion"] != 2:
            raise RLIncompatibleModel("旧模型无元数据完整性绑定，请重新训练")
        if manifest.get("runId") != run_id or type(manifest.get("modelSizeBytes")) is not int:
            raise RLIncompatibleModel("model identity or size invalid")
        if manifest["modelSizeBytes"] != len(model_bytes):
            raise RLModelNotFound("model bundle failed content hash/size check")
        if content_hash(model_bytes) != manifest.get("contentHash"):
            raise RLModelNotFound(f"model bundle failed content hash check: {run_id!r}")
        try:
            expected = bundle_hash(model_bytes, manifest)
        except (TypeError, ValueError) as exc:
            raise RLIncompatibleModel("manifest is not canonical JSON") from exc
        if manifest.get("bundleHash") != expected:
            raise RLIncompatibleModel("model bundle metadata content hash mismatch")
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
