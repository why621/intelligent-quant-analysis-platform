"""Explicitly deployed RL research models; no arbitrary model paths or training."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from quant_platform.rl.errors import RLError, RLIncompatibleModel, RLInSampleRequest
from quant_platform.rl.features import validate_history
from quant_platform.rl.policies import RL_POLICIES, RLStrategy
from quant_platform.rl.store import ModelStore

from app.services.errors import ServiceError, ValidationError


class RLServiceError(ServiceError):
    status = 422

    def __init__(self, error, *, details=None):
        messages = {
            "RL_DEPENDENCIES_MISSING": "RL运行环境尚未就绪，请稍后重试",
            "RL_MODEL_NOT_FOUND": "已部署的RL模型不可用，请联系维护人员",
            "RL_INCOMPATIBLE_MODEL": "RL模型版本或完整性不匹配，已拒绝执行",
            "RL_IN_SAMPLE_REQUEST": "回测起始日必须晚于模型训练截止日",
            "RL_INSUFFICIENT_HISTORY": "RL至少需要22根行情，其中前20根用于预热",
            "RL_NOT_TRAINED": "RL模型尚未就绪",
        }
        self.code = error.code
        message = messages.get(error.code, "RL实验回测失败")
        if details and details.get("symbol"):
            message = f"资产 {details['symbol']}：{message}"
        super().__init__(message, details=details)


def load_web_models(release_path):
    """A trusted deployment file selects bundles; requests cannot choose paths."""
    path = Path(release_path)
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("invalid RL release configuration")
    if set(config) == {"modelRef", "bundleHash", "symbols", "adjust"}:
        entries = [dict(config, algo="ppo")]
    elif (
        set(config) == {"schemaVersion", "models"}
        and type(config["schemaVersion"]) is int
        and config["schemaVersion"] == 2
    ):
        entries = config["models"]
        if not isinstance(entries, list) or not 1 <= len(entries) <= len(RL_POLICIES):
            raise ValueError("release must contain one to four models")
    else:
        raise ValueError("invalid RL release configuration")
    seen = set()
    strategies = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "algo",
            "modelRef",
            "bundleHash",
            "symbols",
            "adjust",
        }:
            raise ValueError("invalid RL model release")
        algo = entry["algo"]
        if not isinstance(algo, str) or algo not in RL_POLICIES or algo in seen:
            raise ValueError("unknown or duplicate release algorithm")
        seen.add(algo)
        strategies.append(WebRL(entry, path.parent))
    return strategies


class WebRL(RLStrategy):
    def __init__(self, release, models_root):
        if release["symbols"] != ["510300"] or release["adjust"] != "qfq":
            raise ValueError("release must retain reviewed training provenance and qfq")
        self.release = release
        super().__init__(RL_POLICIES[release["algo"]], store=ModelStore(models_root))
        bundle = self.checked_bundle()
        self.manifest = bundle.manifest
        self.backtest_enabled = all(
            importlib.util.find_spec(name) is not None
            for name in ("torch", "stable_baselines3", "gymnasium")
        )

    def checked_bundle(self):
        bundle = self._store.load(self.release["modelRef"])
        self._verify_bundle(bundle)
        if bundle.manifest["bundleHash"] != self.release["bundleHash"]:
            raise RLIncompatibleModel("release bundle hash mismatch")
        return bundle

    def info(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["modelRef"],
            "properties": {
                "modelRef": {
                    "type": "string",
                    "title": "已部署模型",
                    "enum": [self.release["modelRef"]],
                    "default": self.release["modelRef"],
                }
            },
        }
        return replace(super().info(), parameter_schema=schema)

    def model_context(self):
        m = self.manifest
        return {
            "modelRef": self.release["modelRef"],
            "bundleHash": m["bundleHash"],
            "trainStartDate": m["trainStartDate"],
            "trainEndDate": m["trainEndDate"],
            "outOfSampleStartDate": (
                date.fromisoformat(m["trainEndDate"]) + timedelta(days=1)
            ).isoformat(),
            "symbols": self.release["symbols"],
            "trainingSymbols": self.release["symbols"],
            "assetScope": "published_universe",
            "portfolioMode": "equal_cash_independent",
            "crossAssetValidated": False,
            "adjust": self.release["adjust"],
            "warmupBars": 20,
            "minimumBars": 22,
            "trainingDataVersion": m["dataVersion"],
            "universeVersion": m["universeVersion"],
            "executionVersion": m["executionVersion"],
        }

    def create_for_request(self, parameters):
        self.checked_bundle()
        return super().create_for_request(parameters)

    def validate_parameters(self, parameters):
        super().validate_parameters(parameters)
        if parameters["modelRef"] != self.release["modelRef"]:
            raise ValueError("仅可选择网页已部署模型")

    def validate_web_request(self, payload, provider):
        self.checked_bundle()
        if payload.get("adjust", "qfq") != "qfq":
            raise ValidationError("RL模型仅支持前复权回测")
        start, end = (date.fromisoformat(str(payload[k])) for k in ("startDate", "endDate"))
        if start <= date.fromisoformat(self.manifest["trainEndDate"]):
            raise RLInSampleRequest("training overlap")
        context = getattr(provider, "publication_context", {})
        if context.get("universeVersion") != self.manifest["universeVersion"]:
            raise RLIncompatibleModel("universe mismatch")
        for symbol in payload["symbols"]:
            try:
                validate_history(provider.history(symbol, start, end, "qfq"))
            except RLError as exc:
                raise RLServiceError(exc, details={"symbol": symbol}) from exc


def validate_web_model(catalog, payload, provider):
    strategy = catalog.get_strategy(str(payload["strategyId"]))
    if isinstance(strategy, WebRL):
        try:
            strategy.validate_web_request(payload, provider)
        except RLError as exc:
            raise RLServiceError(exc) from exc
        return strategy.model_context()
    return None
