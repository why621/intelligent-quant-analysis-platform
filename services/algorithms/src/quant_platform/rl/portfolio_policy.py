"""Isolated CR065 portfolio bundles and fail-closed joint inference.

Never loads or re-labels legacy single-asset bundles. Metadata checks and hashes
run before SB3 is imported. A local research bundle does not authorize deployment.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant_platform.models import TradingCosts
from quant_platform.portfolio.execution import PORTFOLIO_EXECUTION_VERSION
from quant_platform.rl.features import MIN_WARMUP
from quant_platform.rl.portfolio_features import (
    ACTION_SIZE,
    ENVIRONMENT_VERSION,
    MAX_ASSETS,
    OBSERVATION_SIZE,
    PortfolioPanel,
    action_weights,
    encode_observation,
    insufficient_history,
    observation_signature,
    prepare_panel,
)

PORTFOLIO_ALGORITHMS = ("ppo", "sac", "td3")
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")
_HASH = re.compile(r"[a-f0-9]{64}\Z")


def costs_metadata(costs: TradingCosts) -> dict:
    values = {
        "commissionPct": costs.commission_pct,
        "stampDutyPct": costs.stamp_duty_pct,
        "slippagePct": costs.slippage_pct,
        "stampDutyMode": getattr(costs, "stamp_duty_mode", "fixed"),
    }
    if values["stampDutyMode"] not in ("fixed", "asset_date"):
        raise ValueError("unknown stamp duty mode")
    for key in ("commissionPct", "stampDutyPct", "slippagePct"):
        value = values[key]
        if isinstance(value, bool) or not np.isfinite(value) or not 0 <= value < 100:
            raise ValueError(f"invalid portfolio cost: {key}")
    return values


def costs_from_metadata(values: Mapping) -> TradingCosts:
    required = {"commissionPct", "stampDutyPct", "slippagePct", "stampDutyMode"}
    if set(values) != required:
        raise ValueError("portfolio manifest must record every trading cost")
    result = TradingCosts(
        commission_pct=values["commissionPct"],
        stamp_duty_pct=values["stampDutyPct"],
        slippage_pct=values["slippagePct"],
        stamp_duty_mode=values["stampDutyMode"],
    )
    costs_metadata(result)
    return result


def validate_splits(splits: Mapping) -> dict[str, str]:
    pairs = (
        ("trainStartDate", "trainEndDate"),
        ("valStartDate", "valEndDate"),
        ("testStartDate", "testEndDate"),
    )
    allowed = {key for pair in pairs for key in pair}
    if set(splits) - allowed or not all(key in splits for key in pairs[0]):
        raise ValueError("portfolio splits must declare training dates and known date pairs")
    previous_end = None
    parsed = {}
    for start_key, end_key in pairs:
        present = start_key in splits, end_key in splits
        if present[0] != present[1]:
            raise ValueError("split start and end must be declared together")
        if not present[0]:
            continue
        start, end = date.fromisoformat(splits[start_key]), date.fromisoformat(splits[end_key])
        if start >= end or (previous_end is not None and start <= previous_end):
            raise ValueError("portfolio time splits overlap or are not chronological")
        parsed[start_key], parsed[end_key] = start.isoformat(), end.isoformat()
        previous_end = end
    return parsed


def inference_boundary(manifest: Mapping) -> date:
    splits = validate_splits(manifest["splits"])
    return date.fromisoformat(splits.get("valEndDate", splits["trainEndDate"]))


def validate_manifest(manifest: Mapping) -> None:
    expected = {
        "schemaVersion": 1,
        "portfolioMode": "joint_portfolio",
        "environmentVersion": ENVIRONMENT_VERSION,
        "executionVersion": PORTFOLIO_EXECUTION_VERSION,
        "observationSignature": observation_signature(),
        "observationShape": [OBSERVATION_SIZE],
        "actionShape": [ACTION_SIZE],
        "maxAssets": MAX_ASSETS,
        "minAssets": 2,
        "generalization": "unverified",
        "performanceStatus": "unproven",
        "releaseEligible": False,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("incompatible joint portfolio manifest; legacy bundles are not accepted")
    if manifest.get("algo") not in PORTFOLIO_ALGORITHMS:
        raise ValueError("joint portfolio supports only PPO, SAC and TD3")
    universe = manifest.get("trainingUniverse")
    if (
        not isinstance(universe, list)
        or len(universe) < 2
        or any(not isinstance(symbol, str) or not symbol for symbol in universe)
        or len(set(universe)) != len(universe)
    ):
        raise ValueError("invalid training universe")
    types = manifest.get("assetTypes", {})
    if set(types) != set(universe) or any(
        value not in ("stock", "etf") for value in types.values()
    ):
        raise ValueError("manifest asset types must match the trained universe")
    hashes = manifest.get("dataHashes", {})
    if set(hashes) != set(universe) or any(
        not isinstance(value, str) or not _HASH.fullmatch(value) for value in hashes.values()
    ):
        raise ValueError("manifest must fingerprint each training asset")
    validate_splits(manifest.get("splits", {}))
    costs_from_metadata(manifest.get("tradingCosts", {}))
    if not _RUN_ID.fullmatch(str(manifest.get("runId", ""))):
        raise ValueError("invalid portfolio run id")
    for key in ("modelSha256", "bundleHash"):
        if key in manifest and not _HASH.fullmatch(str(manifest[key])):
            raise ValueError(f"invalid {key}")


def _bundle_digest(model_bytes: bytes, manifest: Mapping) -> str:
    metadata = {key: value for key, value in manifest.items() if key != "bundleHash"}
    encoded = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(model_bytes + encoded.encode()).hexdigest()


def save_portfolio_bundle(model, output_root: Path, manifest: Mapping) -> Path:
    """Write a new immutable run directory. Existing paths are never overwritten."""
    metadata = dict(manifest)
    validate_manifest(metadata)
    root = Path(output_root).resolve()
    destination = root / metadata["runId"]
    destination.mkdir(parents=True, exist_ok=False)
    model_path = destination / "model.zip"
    model.save(str(model_path))
    model_bytes = model_path.read_bytes()
    metadata["modelSha256"] = hashlib.sha256(model_bytes).hexdigest()
    metadata["bundleHash"] = _bundle_digest(model_bytes, metadata)
    (destination / "manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


@dataclass(frozen=True)
class PortfolioBundle:
    manifest: Mapping
    model: object
    path: Path


def load_portfolio_bundle(
    path: Path,
    *,
    model_loader: Callable[[str, Path], object] | None = None,
) -> PortfolioBundle:
    path = Path(path).resolve()
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    validate_manifest(manifest)
    if "modelSha256" not in manifest or "bundleHash" not in manifest:
        raise ValueError("joint bundle is missing integrity hashes")
    model_path = path / "model.zip"
    raw = model_path.read_bytes()
    if (
        hashlib.sha256(raw).hexdigest() != manifest["modelSha256"]
        or _bundle_digest(raw, manifest) != manifest["bundleHash"]
    ):
        raise ValueError("joint portfolio bundle integrity mismatch")
    if model_loader is None:
        try:
            from stable_baselines3 import PPO, SAC, TD3
        except ImportError as exc:
            from quant_platform.rl.errors import RLDependenciesMissing

            raise RLDependenciesMissing(
                "joint inference requires optional [rl] dependencies"
            ) from exc
        cls = {"ppo": PPO, "sac": SAC, "td3": TD3}[manifest["algo"]]
        model = cls.load(str(model_path), device="cpu")
    else:
        model = model_loader(manifest["algo"], model_path)
    if tuple(model.observation_space.shape) != (OBSERVATION_SIZE,) or tuple(
        model.action_space.shape
    ) != (ACTION_SIZE,):
        raise ValueError("model network dimensions do not match the joint manifest")
    return PortfolioBundle(manifest, model, path)


@dataclass(frozen=True)
class PreparedPortfolioPolicy:
    bundle: PortfolioBundle
    panel: PortfolioPanel
    first_decision_index: int

    @property
    def symbols(self) -> tuple[str, ...]:
        return self.panel.symbols

    def action_at(self, bar: int, cash: float, quantities: Sequence[float]) -> np.ndarray:
        if not self.first_decision_index <= bar < len(self.panel.dates) - 1:
            raise ValueError("joint decision is outside the out-of-sample tradable window")
        obs = encode_observation(self.panel.features[bar], quantities, self.panel.closes[bar], cash)
        action, _ = self.bundle.model.predict(obs, deterministic=True)
        # Validation and hard masking happen here too, before the broker is reached.
        return action_weights(action, len(self.symbols))

    def target_weights(self, bar: int, cash: float, quantities: Sequence[float]) -> np.ndarray:
        """Broker callback: weights match canonical symbols, with cash left implicit."""
        return self.action_at(bar, cash, quantities)[: len(self.symbols)]


def prepare_portfolio_policy(
    bundle: PortfolioBundle,
    frames: Mapping[str, pd.DataFrame],
    *,
    evaluation_start: date,
    trading_costs: TradingCosts | None = None,
    serving_scope: Mapping | None = None,
    nontrading_sessions: Mapping | None = None,
    evaluation_end: date | None = None,
) -> PreparedPortfolioPolicy:
    validate_manifest(bundle.manifest)
    if not 2 <= len(frames) <= MAX_ASSETS:
        raise ValueError("joint inference requires two to ten assets")
    universe = (
        serving_scope["supportedAssetTypes"]
        if serving_scope
        else bundle.manifest["trainingUniverse"]
    )
    if not set(frames).issubset(universe):
        raise ValueError("unseen asset outside the training universe; generalization is unverified")
    if evaluation_start <= inference_boundary(bundle.manifest):
        raise ValueError("joint inference cannot overlap training or validation dates")
    expected_costs = bundle.manifest["tradingCosts"]
    if (
        trading_costs is not None
        and costs_metadata(trading_costs) != expected_costs
        and not (serving_scope and serving_scope.get("costPolicy") == "request_configurable")
    ):
        raise ValueError("joint inference costs must equal the recorded training costs")
    panel = prepare_panel(
        frames,
        nontrading_sessions=nontrading_sessions,
        end_date=evaluation_end,
    )
    requested_index = int(panel.dates.searchsorted(pd.Timestamp(evaluation_start)))
    # Do not silently advance the requested evaluation window to hide missing warm-up.
    if requested_index < MIN_WARMUP or requested_index >= len(panel.dates) - 1:
        if serving_scope:
            raise insufficient_history("组合模型请求区间缺少140根真实预热行情或下一交易日行情")
        raise ValueError("requested evaluation window lacks causal warm-up or next-open history")
    if panel.observed_bars is not None and np.any(
        panel.observed_bars[requested_index] <= MIN_WARMUP
    ):
        symbol = panel.symbols[int(np.argmin(panel.observed_bars[requested_index]))]
        raise insufficient_history(
            "组合资产上市历史或实际行情不足140根预热，停牌日不计入预热", symbol
        )
    return PreparedPortfolioPolicy(bundle, panel, requested_index)


def research_backtest(
    bundle: PortfolioBundle,
    frames: Mapping[str, pd.DataFrame],
    *,
    evaluation_start: date,
    initial_capital: float = 100_000.0,
) -> dict:
    """Read-only local replay with the same observation, action and broker as training."""
    from quant_platform.rl.portfolio_env import PortfolioEpisode

    prepared = prepare_portfolio_policy(bundle, frames, evaluation_start=evaluation_start)
    episode = PortfolioEpisode(
        prepared.panel,
        asset_types=bundle.manifest["assetTypes"],
        trading_costs=costs_from_metadata(bundle.manifest["tradingCosts"]),
        initial_capital=initial_capital,
        random_subsets=False,
        random_start=False,
        episode_bars=len(prepared.panel.dates) - prepared.first_decision_index - 1,
        band_pct=bundle.manifest.get("rebalanceBandPct", 0.0),
        min_trade_cny=bundle.manifest.get("minTradeCny", 0.0),
    )
    _, info = episode.reset(options={"start_index": prepared.first_decision_index})
    records = [info]
    while episode.bar < episode.end_bar:
        action = prepared.action_at(episode.bar, episode.cash, episode.quantities)
        # action_at returns a valid simplex, which is unchanged by the env projection.
        _, _, _, _, info = episode.step(action)
        records.append(info)
    return {
        "runId": bundle.manifest["runId"],
        "portfolioMode": "joint_portfolio",
        "symbols": list(prepared.symbols),
        "accountCurve": records,
        "tradingCosts": bundle.manifest["tradingCosts"],
        "performanceStatus": "unproven",
        "evidenceKind": "local_research_replay",
    }
