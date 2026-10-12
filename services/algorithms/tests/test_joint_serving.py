"""Joint serving invariants; scripted policies are test doubles, never training evidence."""
import hashlib
import json
from dataclasses import replace
from datetime import date

import pandas as pd
import pytest
from test_portfolio_rl import ZERO_COSTS, ScriptedModel, frames, manifest

from quant_platform.backtesting.engine import BacktestEngine
from quant_platform.data.calendar import sessions
from quant_platform.models import BacktestRequest
from quant_platform.rl.portfolio_policy import PortfolioBundle, research_backtest
from quant_platform.rl.portfolio_strategy import JointPortfolioStrategy


def setup_strategy(monkeypatch, tmp_path):
    source = frames(count=10)
    dates = pd.to_datetime(sessions(date(2025, 1, 2), date(2026, 6, 30))[:300])
    for f in source.values():
        f['date'] = dates
    m = manifest(source)
    m.update(purpose='formal_candidate', actualTimesteps=65536, optimizerUpdates=1536,
             bundleHash='a'*64)
    bundle = PortfolioBundle(m, ScriptedModel(), tmp_path)
    monkeypatch.setattr('quant_platform.rl.portfolio_strategy.load_portfolio_bundle',
                        lambda _: bundle)
    evidence = dict(bundleHash='a'*64, ledgerPassed=True, simultaneousAssets=10)
    raw = json.dumps(evidence).encode()
    (tmp_path/'evaluation.json').write_bytes(raw)
    release = dict(bundleHash='a'*64, evaluationSha256=hashlib.sha256(raw).hexdigest(),
                   targetUniverseVersion='u')
    strategy = JointPortfolioStrategy(tmp_path, release)
    class Provider:
        start = dates[0].date()
        publication_context = {'universeVersion':'u'}
        def history(self, symbol, start, end, adjust):
            f = source[symbol]
            return f[(f.date >= pd.Timestamp(start)) & (f.date <= pd.Timestamp(end))].copy()
    return source, strategy, Provider(), release


def test_ten_asset_serving_matches_joint_environment(monkeypatch, tmp_path):
    source, strategy, provider, _ = setup_strategy(monkeypatch, tmp_path)
    start = date.fromisoformat(strategy.bundle.manifest['splits']['testStartDate'])
    request = BacktestRequest(tuple(reversed(source)), strategy.info().strategy_id,
        start, source['A0'].date.iloc[-1].date(), parameters={'modelRef':'test-joint'},
        trading_costs=ZERO_COSTS, portfolio_mode='shared_account', benchmark_mode='buy_and_hold')
    engine = BacktestEngine(provider, {request.strategy_id:strategy})
    result, targets = strategy.run_joint(engine, request, with_target=True)
    reference = research_backtest(strategy.bundle, source, evaluation_start=start)
    assert [p['equity'] for p in result.account_curve] == pytest.approx(
        [p['equity'] for p in reference['accountCurve']])
    assert len(targets) == 10
    assert sum(targets.values()) <= 1 + 1e-9
    assert result.trades
    assert all(p['cashCny'] >= -1e-7 for p in result.account_curve)
    with pytest.raises(ValueError, match='共享账户'):
        engine.run(replace(request, portfolio_mode='legacy_independent'))
    with pytest.raises(ValueError, match='two to ten'):
        engine.run(replace(request, symbols=('A0',)))


def test_smoke_and_tampered_evidence_cannot_be_served(monkeypatch, tmp_path):
    _, strategy, _, release = setup_strategy(monkeypatch, tmp_path)
    strategy.bundle.manifest['purpose'] = 'local_smoke_only'
    with pytest.raises(ValueError, match='evidence'):
        JointPortfolioStrategy(tmp_path, release)
    strategy.bundle.manifest['purpose'] = 'formal_candidate'
    (tmp_path/'evaluation.json').write_text('{}')
    with pytest.raises(ValueError, match='evidence'):
        JointPortfolioStrategy(tmp_path, release)


def test_joint_web_boundary_rejects_pool_cost_and_training_overlap(monkeypatch, tmp_path):
    source, strategy, provider, _ = setup_strategy(monkeypatch, tmp_path)
    payload = dict(symbols=list(source), portfolioMode='shared_account', cashPct=0,
        startDate=str(source['A0'].date.iloc[211].date()))
    strategy.validate_web_request(payload, provider)
    for changes in [dict(symbols=['unknown', 'A0']), dict(cashPct=10),
                    dict(startDate='2025-01-02'), dict(tradingCosts={}),
                    dict(portfolioMode='legacy_independent')]:
        with pytest.raises(ValueError):
            strategy.validate_web_request({**payload, **changes}, provider)
