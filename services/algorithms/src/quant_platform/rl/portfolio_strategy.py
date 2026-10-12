"""Serving adapter for a reviewed joint portfolio bundle; no independent accounts."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from quant_platform.models import BacktestResult, StrategyInfo, Trade
from quant_platform.rl.portfolio_env import PortfolioEpisode
from quant_platform.rl.portfolio_features import action_weights, encode_observation
from quant_platform.rl.portfolio_policy import (
    costs_metadata,
    inference_boundary,
    load_portfolio_bundle,
    prepare_portfolio_policy,
)


class JointPortfolioStrategy:
    joint_portfolio = True
    backtest_enabled = True
    allocation_enabled = True
    ranking_enabled = False

    def __init__(self, path, release):
        self.path = Path(path)
        self.release = dict(release)
        self.bundle = load_portfolio_bundle(self.path)
        m = self.bundle.manifest
        raw = (self.path / "evaluation.json").read_bytes()
        evidence = json.loads(raw)
        if (
            m.get("purpose") != "formal_candidate"
            or m.get("actualTimesteps", 0) < 65536
            or m.get("optimizerUpdates", 0) <= 0
            or m["bundleHash"] != release["bundleHash"]
            or hashlib.sha256(raw).hexdigest() != release["evaluationSha256"]
            or evidence.get("bundleHash") != m["bundleHash"]
            or evidence.get("ledgerPassed") is not True
            or evidence.get("simultaneousAssets") != 10
        ):
            raise ValueError("joint release lacks matching formal training/evaluation evidence")
        self.evidence = evidence

    def info(self):
        m = self.bundle.manifest
        return StrategyInfo(
            "portfolio_" + m["algo"],
            m["algo"].upper() + " 多资产组合",
            "ai",
            "experimental",
            "联合观察2–10资产并输出共享账户权重；实验模型，收益与池外泛化未获证实。",
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["modelRef"],
                "properties": {
                    "modelRef": {
                        "type": "string",
                        "enum": [m["runId"]],
                        "default": m["runId"],
                        "title": "组合模型",
                    }
                },
            },
            signal_semantics="continuous_target_weight",
            requires_trained_model=True,
        )

    def validate_parameters(self, parameters):
        if dict(parameters) != {"modelRef": self.bundle.manifest["runId"]}:
            raise ValueError("仅允许已发布的组合模型版本")

    def model_context(self):
        m = self.bundle.manifest
        return {
            "modelRef": m["runId"],
            "bundleHash": m["bundleHash"],
            **m["splits"],
            "inSampleEndDate": inference_boundary(m).isoformat(),
            "outOfSampleStartDate": (inference_boundary(m) + timedelta(days=1)).isoformat(),
            "symbols": m["trainingUniverse"],
            "trainingSymbols": m["trainingUniverse"],
            "assetScope": "training_symbols",
            "portfolioMode": "joint_portfolio",
            "minAssets": 2,
            "maxAssets": 10,
            "crossAssetValidated": False,
            "adjust": "qfq",
            "warmupBars": 140,
            "minimumBars": 142,
            "trainingDataVersion": hashlib.sha256(
                json.dumps(m["dataHashes"], sort_keys=True).encode()
            ).hexdigest(),
            "universeVersion": self.release["targetUniverseVersion"],
            "executionVersion": m["executionVersion"],
            "performanceStatus": "unproven",
            "requiredTradingCosts": m["tradingCosts"],
            "evaluation": self.evidence,
        }

    def validate_web_request(self, payload, provider):
        if payload.get("portfolioMode") != "shared_account":
            raise ValueError("联合模型必须使用共享组合账户")
        if payload.get("cashPct", 0) != 0:
            raise ValueError("组合模型自行输出现金权重，额外预留现金须为0")
        if payload.get("adjust", "qfq") != "qfq":
            raise ValueError("组合模型仅支持前复权")
        symbols = payload["symbols"]
        if not 2 <= len(symbols) <= 10 or not set(symbols).issubset(
            self.bundle.manifest["trainingUniverse"]
        ):
            raise ValueError("请选择模型训练池内2–10只不同资产")
        if date.fromisoformat(payload["startDate"]) <= inference_boundary(self.bundle.manifest):
            raise ValueError("组合回测/模拟起点必须晚于训练和验证区间")
        if (
            payload.get("tradingCosts", self.bundle.manifest["tradingCosts"])
            != self.bundle.manifest["tradingCosts"]
        ):
            raise ValueError("组合模型成本必须与训练成本一致")
        if (
            getattr(provider, "publication_context", {}).get("universeVersion")
            != self.release["targetUniverseVersion"]
        ):
            raise ValueError("组合模型发布资产目录版本不匹配")

    def run_joint(self, engine, request, *, with_target=False):
        from quant_platform.backtesting.engine import _compute_metrics

        self.validate_parameters(request.parameters)
        if (
            request.portfolio_mode != "shared_account"
            or request.cash_pct
            or request.adjust != "qfq"
        ):
            raise ValueError("组合模型需要共享账户、前复权且额外现金预留为0")
        if costs_metadata(request.trading_costs) != self.bundle.manifest["tradingCosts"]:
            raise ValueError("组合执行成本与模型不一致")
        history_start = max(
            request.start_date - timedelta(days=450), getattr(engine._provider, "start", date.min)
        )
        frames = {
            s: engine._provider.history(s, history_start, request.end_date, request.adjust)
            for s in request.symbols
        }
        prepared = prepare_portfolio_policy(
            self.bundle,
            frames,
            evaluation_start=request.start_date,
            trading_costs=request.trading_costs,
        )
        panel = prepared.panel
        # Unknown gaps must not turn next-session execution into next-available-bar execution.
        from quant_platform.data.calendar import sessions

        expected = pd.DatetimeIndex(
            pd.to_datetime(sessions(panel.dates[0].date(), request.end_date))
        )
        if not panel.dates.equals(expected):
            raise ValueError("联合模型要求完整共同交易日行情，缺口/停牌暂不支持")
        episode = PortfolioEpisode(
            panel,
            asset_types=self.bundle.manifest["assetTypes"],
            trading_costs=request.trading_costs,
            initial_capital=request.initial_capital_cny,
            random_subsets=False,
            random_start=False,
            episode_bars=len(panel.dates) - prepared.first_decision_index - 1,
            band_pct=self.bundle.manifest.get("rebalanceBandPct", 0),
            min_trade_cny=self.bundle.manifest.get("minTradeCny", 0),
        )
        obs, state = episode.reset(options={"start_index": prepared.first_decision_index})
        records, trades = [], []

        def append():
            records.append(
                engine._point(
                    panel.dates[episode.bar],
                    episode.cash,
                    episode.quantities,
                    panel.closes[episode.bar],
                    panel.symbols,
                    episode.cumulative_fees,
                    episode.cumulative_slippage,
                )
            )

        append()
        while episode.bar < episode.end_bar:
            action, _ = self.bundle.model.predict(obs, deterministic=True)
            obs, _, _, _, state = episode.step(action)
            for f in state.get("fills", []):
                trades.append(
                    Trade(
                        date.fromisoformat(state["date"]),
                        f["symbol"],
                        f["side"],
                        f["price"],
                        f["quantity"],
                        f["amount_cny"],
                        f["commission_cny"] + f["stamp_duty_cny"],
                        f["commission_cny"],
                        f["stamp_duty_cny"],
                        f["slippage_cny"],
                    )
                )
            append()
        dates = pd.to_datetime([p["date"] for p in records])
        eq = pd.Series([p["equity"] for p in records], index=dates)
        benchmark = engine._benchmark_curve(request, dates)
        curve = pd.DataFrame(
            {
                "date": dates,
                "equity": eq.values,
                "benchmarkEquity": None if benchmark is None else benchmark.values,
            }
        )
        result = BacktestResult(
            _compute_metrics(eq, benchmark, request.initial_capital_cny),
            curve,
            tuple(trades),
            {
                "signalAt": "close",
                "executeAt": "next_open",
                "calendar": "CN",
                "currency": "CNY",
                "portfolioMode": "shared_account",
                "signalSemantics": "joint_target_weights",
                "executionVersion": self.bundle.manifest["executionVersion"],
            },
            tuple(records),
            engine._cost_summary(trades),
            engine._benchmark_context(request, dates),
        )
        if not with_target:
            return result
        obs = encode_observation(
            panel.features[-1], episode.quantities, panel.closes[-1], episode.cash
        )
        action, _ = self.bundle.model.predict(obs, deterministic=True)
        weights = action_weights(action, len(panel.symbols))
        return result, dict(zip(panel.symbols, weights[: len(panel.symbols)], strict=True))
