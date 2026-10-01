"""Explicitly deployed RL research models; no arbitrary model paths or training."""

from __future__ import annotations

import importlib.util
import json
import re
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from quant_platform.models import BacktestRequest, TradingCosts
from quant_platform.ranking import _start_date
from quant_platform.rl.errors import (
    RLError,
    RLIncompatibleModel,
    RLInSampleRequest,
    RLInsufficientHistory,
)
from quant_platform.rl.features import MIN_WARMUP, validate_history
from quant_platform.rl.policies import RL_POLICIES, RLStrategy
from quant_platform.rl.splits import in_sample_end
from quant_platform.rl.store import ModelStore

from app.services.errors import ServiceError, ValidationError


class RLServiceError(ServiceError):
    status = 422

    def __init__(self, error, *, details=None):
        messages = {
            "RL_DEPENDENCIES_MISSING": "RL运行环境尚未就绪，请稍后重试",
            "RL_MODEL_NOT_FOUND": "已部署的RL模型不可用，请联系维护人员",
            "RL_INCOMPATIBLE_MODEL": "RL模型版本或完整性不匹配，已拒绝执行",
            "RL_IN_SAMPLE_REQUEST": "回测起始日必须晚于模型训练及验证截止日",
            "RL_INSUFFICIENT_HISTORY": (
                f"RL至少需要{MIN_WARMUP + 2}根行情，其中前{MIN_WARMUP}根用于预热"
            ),
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
    target_universe = None
    if type(config.get("schemaVersion")) is int and config["schemaVersion"] == 3:
        if set(config) != {"schemaVersion", "models", "targetUniverseVersion"}:
            raise ValueError("invalid reviewed research release")
        target_universe = config["targetUniverseVersion"]
        if (not isinstance(target_universe, str)
                or not re.fullmatch(r"[a-f0-9]{64}", target_universe)):
            raise ValueError("research release must pin the target universe")
        config = {"schemaVersion": 2, "models": config["models"]}
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
        strategies.append(WebRL(entry, path.parent, target_universe=target_universe))
    return strategies


class WebRL(RLStrategy):
    def __init__(self, release, models_root, *, target_universe=None):
        if release["symbols"] != ["510300"] or release["adjust"] != "qfq":
            raise ValueError("release must retain reviewed training provenance and qfq")
        self.release = release
        self.target_universe = target_universe
        super().__init__(RL_POLICIES[release["algo"]], store=ModelStore(models_root))
        bundle = self.checked_bundle()
        self.manifest = bundle.manifest
        if target_universe is not None:
            m = self.manifest
            if (m.get("consistency") != "research_backfill_unpublished"
                    or m.get("universeVersion") != "research-backfill-root"
                    or m.get("symbol") != "510300"
                    or not m.get("valEndDate") or not m.get("testEndDate")):
                raise RLIncompatibleModel("unreviewed research provenance")
        self.backtest_enabled = all(
            importlib.util.find_spec(name) is not None
            for name in ("torch", "stable_baselines3", "gymnasium")
        )

    @property
    def ranking_enabled(self):
        return self.backtest_enabled

    def ranking_request(self, as_of_date, period, provider):
        evaluation_start = _start_date(as_of_date, period)
        out_of_sample = date.fromisoformat(self.model_context()["outOfSampleStartDate"])
        if evaluation_start < out_of_sample:
            raise RLInSampleRequest("ranking window overlaps training")
        start = max(evaluation_start - timedelta(days=max(90, MIN_WARMUP * 2 + 30)), out_of_sample)
        payload = {
            "symbols": ["510300"],
            "startDate": start.isoformat(),
            "endDate": as_of_date.isoformat(),
            "adjust": "qfq",
        }
        self.validate_web_request(payload, provider)
        prices = provider.history("510300", start, as_of_date, "qfq").reset_index(drop=True)
        import pandas as pd

        dates = pd.to_datetime(prices["date"])
        window = (
            prices.tail(2) if period == "1d" else prices[dates >= pd.Timestamp(evaluation_start)]
        )
        if len(window) < 2 or window.index[0] < MIN_WARMUP:
            raise RLInsufficientHistory("insufficient out-of-sample pre-window warmup")
        return BacktestRequest(
            symbols=("510300",),
            strategy_id=self._spec.algo_id,
            start_date=start,
            end_date=as_of_date,
            parameters={"modelRef": self.release["modelRef"]},
            trading_costs=TradingCosts(stamp_duty_pct=0),
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
            "inSampleEndDate": in_sample_end(m),
            **{key: m[key] for key in (
                "valStartDate", "valEndDate", "testStartDate", "testEndDate", "valFolds"
            ) if key in m},
            "outOfSampleStartDate": (
                date.fromisoformat(in_sample_end(m)) + timedelta(days=1)
            ).isoformat(),
            "symbols": self.release["symbols"],
            "trainingSymbols": self.release["symbols"],
            "assetScope": "training_symbols" if self.target_universe else "published_universe",
            **({"trainingConsistency": "research_backfill_unpublished",
                "targetUniverseVersion": self.target_universe,
                "performanceStatus": "unproven",
                "requiredTradingCosts": {"commissionPct": 0.03, "stampDutyPct": 0,
                                         "slippagePct": 0.02},
                "trainingTradingCosts": {"commissionPct": 0.03, "stampDutyPct": 0.05,
                                         "slippagePct": 0.02}} if self.target_universe else {}),
            "portfolioMode": "equal_cash_independent",
            "crossAssetValidated": False,
            "adjust": self.release["adjust"],
            "warmupBars": MIN_WARMUP,
            "minimumBars": MIN_WARMUP + 2,
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
        if start <= date.fromisoformat(in_sample_end(self.manifest)):
            raise RLInSampleRequest("training overlap")
        context = getattr(provider, "publication_context", {})
        expected_universe = self.target_universe or self.manifest["universeVersion"]
        if context.get("universeVersion") != expected_universe:
            raise RLIncompatibleModel("universe mismatch")
        if self.target_universe:
            if payload["symbols"] != self.release["symbols"]:
                raise ValidationError("本批研究模型仅支持训练资产510300，不支持跨资产回测")
            costs = self.model_context()["requiredTradingCosts"]
            if payload.get("tradingCosts") not in (None, costs):
                raise ValidationError("本批ETF模型回评固定佣金0.03%、印花税0%、滑点0.02%")
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
