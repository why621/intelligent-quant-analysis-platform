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
from quant_platform.rl.portfolio_release import validated_serving_scope


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
        self.serving_scope, self.cross_asset_evidence = validated_serving_scope(
            self.path, m, release
        )

    def info(self):
        m = self.bundle.manifest
        return StrategyInfo(
            "portfolio_" + m["algo"],
            ("掩码注意力 SAC 多资产组合" if m["algo"] == "masked_sac"
             else m["algo"].upper() + " 多资产组合"),
            "ai",
            "experimental",
            ("借鉴EarnMore共享注意力、掩码重建与可变资产池训练；非完整复刻，未证明收益提升。"
             if m["algo"] == "masked_sac" else
             "联合观察2–10资产并输出共享账户权重；实验模型，收益与池外泛化未获证实。"),
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
        context = {
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
        if self.serving_scope:
            context.update(
                symbols=sorted(self.serving_scope["supportedAssetTypes"]),
                assetScope="published_universe",
                supportedAssetTypes=self.serving_scope["supportedAssetTypes"],
                scopeDataVersion=self.serving_scope["scopeDataVersion"],
                costPolicy="request_configurable",
                trainingTradingCosts=m["tradingCosts"],
                crossAssetValidated=True,
                crossAssetValidationStatus="execution_validated",
            )
            del context["requiredTradingCosts"]
        if m["algo"] == "masked_sac":
            context["representationLearning"] = {
                "architecture": m["architecture"],
                "method": "earnmore_inspired_masked_features",
                "poolChanges": "training_in_episode",
                "performanceImprovement": "unproven",
            }
        return context

    def validate_web_request(self, payload, provider):
        if payload.get("portfolioMode") != "shared_account":
            raise ValueError("联合模型必须使用共享组合账户")
        if not self.serving_scope and payload.get("cashPct", 0) != 0:
            raise ValueError("组合模型自行输出现金权重，额外预留现金须为0")
        if payload.get("adjust", "qfq") != "qfq":
            raise ValueError("组合模型仅支持前复权")
        symbols = payload["symbols"]
        applicable = (
            self.serving_scope["supportedAssetTypes"]
            if self.serving_scope
            else self.bundle.manifest["trainingUniverse"]
        )
        if (
            not 2 <= len(symbols) <= 10
            or len(set(symbols)) != len(symbols)
            or not set(symbols).issubset(applicable)
        ):
            raise ValueError("请选择模型适用目录内2–10只不同资产")
        if date.fromisoformat(payload["startDate"]) <= inference_boundary(self.bundle.manifest):
            raise ValueError("组合回测/模拟起点必须晚于训练和验证区间")
        if not self.serving_scope and (
            payload.get("tradingCosts", self.bundle.manifest["tradingCosts"])
            != self.bundle.manifest["tradingCosts"]
        ):
            raise ValueError("组合模型成本必须与训练成本一致")
        if (
            getattr(provider, "publication_context", {}).get("universeVersion")
            != self.release["targetUniverseVersion"]
        ):
            raise ValueError("组合模型发布资产目录版本不匹配")
        if self.serving_scope:
            actual = {a.symbol: a.asset_type for a in provider.list_assets(limit=None)}
            if actual != self.serving_scope["supportedAssetTypes"]:
                raise ValueError("组合模型适用目录或资产类型与当前发布不匹配")

    def run_joint(self, engine, request, *, with_target=False):
        from quant_platform.backtesting.engine import _compute_metrics

        self.validate_parameters(request.parameters)
        if (
            request.portfolio_mode != "shared_account"
            or (request.cash_pct and not self.serving_scope)
            or request.adjust != "qfq"
        ):
            raise ValueError("组合模型需要共享账户、前复权且额外现金预留为0")
        if (
            not self.serving_scope
            and costs_metadata(request.trading_costs) != self.bundle.manifest["tradingCosts"]
        ):
            raise ValueError("组合执行成本与模型不一致")
        history_start = max(
            request.start_date - timedelta(days=450), getattr(engine._provider, "start", date.min)
        )
        frames = {
            s: engine._provider.history(s, history_start, request.end_date, request.adjust)
            for s in request.symbols
        }
        nontrading = None
        asset_types = self.bundle.manifest["assetTypes"]
        if self.serving_scope:
            if (
                getattr(engine._provider, "publication_context", {}).get("universeVersion")
                != self.release["targetUniverseVersion"]
            ):
                raise ValueError("组合模型发布资产目录版本不匹配")
            asset_types = engine._asset_types(request.symbols)
            if asset_types != self.serving_scope["supportedAssetTypes"]:
                raise ValueError("组合模型适用目录或资产类型与当前发布不匹配")
            lookup = getattr(engine._provider, "nontrading_sessions", None)
            nontrading = {
                s: (lookup(s, history_start, request.end_date) if callable(lookup) else ())
                for s in frames
            }
        prepared = prepare_portfolio_policy(
            self.bundle,
            frames,
            evaluation_start=request.start_date,
            trading_costs=request.trading_costs,
            serving_scope=self.serving_scope,
            nontrading_sessions=nontrading,
            evaluation_end=request.end_date,
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
            asset_types=asset_types,
            trading_costs=request.trading_costs,
            initial_capital=request.initial_capital_cny,
            random_subsets=False,
            random_start=False,
            episode_bars=len(panel.dates) - prepared.first_decision_index - 1,
            band_pct=self.bundle.manifest.get("rebalanceBandPct", 0),
            min_trade_cny=self.bundle.manifest.get("minTradeCny", 0),
            cash_pct=request.cash_pct,
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
                "costPolicy": "request_configurable" if self.serving_scope else "training_fixed",
                "costsDifferFromTraining": str(
                    costs_metadata(request.trading_costs) != self.bundle.manifest["tradingCosts"]
                ).lower(),
                "nonTradingExecution": "skip_untradable_no_pending_order",
                "nonTradingValuation": "last_observed_close"
                if panel.tradable is not None and not panel.tradable.all()
                else "none",
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
        weights[: len(panel.symbols)] *= 1 - request.cash_pct / 100
        return result, dict(zip(panel.symbols, weights[: len(panel.symbols)], strict=True))
