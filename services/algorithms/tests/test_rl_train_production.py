"""生产化训练路径的离线钉桩（需要 ``[rl]`` extra；合成数据，无网络）。

验证 T-035d 准备阶段给 ``train_run`` 加的五件事：进度行输出、验证窗选优
（weightSelection/bestEvalReward）、超参覆盖入 manifest、run-id 防覆盖、
零梯度更新拒绝保存。全部合成固定种子行情，不含任何绩效结论。
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("stable_baselines3")
pytest.importorskip("gymnasium")
pytestmark = pytest.mark.rl

from quant_platform.rl.errors import RLError  # noqa: E402
from quant_platform.rl.store import ModelStore  # noqa: E402
from quant_platform.rl.train import parse_overrides, train_run  # noqa: E402


def _synthetic_ohlc(*, first_day: date, rows: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0002, 0.01, size=rows)
    close = 100.0 * np.cumprod(1.0 + rets)
    open_ = np.empty(rows)
    open_[0] = close[0] * (1 + rets[0] * 0.1)
    open_[1:] = close[:-1]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.004, size=rows))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.004, size=rows))
    dates = pd.date_range(first_day, periods=rows, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1e6,
            "amount": close * 1e6,
        }
    )


def _window_provider(frame: pd.DataFrame, publication_date: date):
    """按日期窗切片的桩 provider——训练/验证各拿各的真实切片。"""
    context = {
        "publicationDate": publication_date.isoformat(),
        "universeVersion": "prod-smoke-universe",
        "dataVersion": "b" * 64,
        "consistency": "synthetic_pipeline_smoke",
    }

    def history(symbol, start, end, adjust="qfq"):
        mask = (frame["date"] >= pd.Timestamp(start)) & (frame["date"] <= pd.Timestamp(end))
        return frame[mask].reset_index(drop=True)

    return SimpleNamespace(history=history, publication_context=context)


def test_progress_lines_and_validation_best_selection(tmp_path, capsys):
    frame = _synthetic_ohlc(first_day=date(2015, 1, 5), rows=2400, seed=7)
    models_root = tmp_path / "models"
    run_id = "dqn-prod-0001"
    model_dir = train_run(
        publication_root=tmp_path / "unused",
        models_root=models_root,
        run_id=run_id,
        algo="dqn",
        symbol="SYNTH",
        start=date(2015, 1, 5),
        end=date(2018, 6, 30),
        val_start=date(2018, 7, 1),
        val_end=date(2019, 12, 31),
        test_start=date(2020, 1, 1),
        test_end=date(2021, 6, 30),
        seed=42,
        total_timesteps=600,
        eval_freq=200,
        progress_every=100,
        hyper_overrides={"learning_rate": 0.005},
        provider=_window_provider(frame, date(2026, 9, 18)),
    )
    out = capsys.readouterr().out
    assert "[600/600" in out, out
    assert "ep_rew100" in out
    assert "elapsed" in out and "eta" in out

    manifest = ModelStore(models_root).load(run_id).manifest
    assert manifest["weightSelection"] == "validation-best"
    assert isinstance(manifest["bestEvalReward"], float)
    assert manifest["hyperparameters"]["learning_rate"] == 0.005
    # 未被覆盖的超参保持 spec 默认（CR-059 把 off-policy 的 buffer 由 100k 降到 20k，
    # 因为一个训练窗只有约 850 根K线，20 万容量的回放池是同一批 transition 的重复）
    assert manifest["hyperparameters"]["buffer_size"] == 20_000
    assert manifest["symbol"] == "SYNTH"
    assert manifest["requestedTimesteps"] == 600
    assert manifest["actualTimesteps"] >= 600
    assert manifest["gradientUpdates"] > 0
    assert (model_dir / "model.zip").exists()
    # 验证评估的 CSV/npz 落在训练日志目录，不进 bundle
    log_dir = models_root / "_trainlogs" / run_id
    assert (log_dir / "best_model.zip").exists()
    assert (log_dir / "evaluations.npz").exists()


def test_zero_gradient_update_save_is_refused(tmp_path):
    frame = _synthetic_ohlc(first_day=date(2015, 1, 5), rows=1200, seed=5)
    with pytest.raises(RLError, match="梯度更新为 0"):
        train_run(
            publication_root=tmp_path / "unused",
            models_root=tmp_path / "models",
            run_id="sac-prod-zero",
            algo="sac",
            symbol="SYNTH",
            start=date(2015, 1, 5),
            end=date(2018, 6, 30),
            seed=42,
            total_timesteps=50,  # SAC learning_starts=100 → 0 次更新
            eval_freq=0,
            provider=_window_provider(frame, date(2026, 9, 18)),
        )
    assert not (tmp_path / "models" / "sac-prod-zero").exists()


def test_run_id_overwrite_requires_explicit_flag(tmp_path):
    frame = _synthetic_ohlc(first_day=date(2015, 1, 5), rows=1200, seed=9)
    kwargs = dict(
        publication_root=tmp_path / "unused",
        models_root=tmp_path / "models",
        run_id="dqn-prod-dup",
        algo="dqn",
        symbol="SYNTH",
        start=date(2015, 1, 5),
        end=date(2018, 6, 30),
        seed=42,
        total_timesteps=200,
        eval_freq=0,
        provider=_window_provider(frame, date(2026, 9, 18)),
    )
    train_run(**kwargs)
    with pytest.raises(RLError, match="拒绝静默覆盖"):
        train_run(**kwargs)
    train_run(**{**kwargs, "overwrite": True})  # 显式放行


def test_parse_overrides_values():
    parsed = parse_overrides(["learning_rate=3e-4", "policy=MlpPolicy", "n=7"])
    assert parsed == {"learning_rate": 3e-4, "policy": "MlpPolicy", "n": 7}
    assert parse_overrides(None) == {}
    with pytest.raises(ValueError, match="KEY=VALUE"):
        parse_overrides(["oops"])


def test_train_start_header_is_json(tmp_path, capsys):
    """CLI 起跑头是单行 JSON，服务器日志可 grep。"""
    from quant_platform.rl.train import main

    frame = _synthetic_ohlc(first_day=date(2015, 1, 5), rows=1200, seed=3)
    provider = _window_provider(frame, date(2026, 9, 18))
    import quant_platform.rl.train as train_module

    original = train_module.train_run

    def spy(**kwargs):
        return original(provider=provider, **kwargs)

    train_module.train_run = spy
    try:
        code = main([
            "--history-root", str(tmp_path / "hist"),
            "--models-root", str(tmp_path / "models"),
            "--run-id", "dqn-prod-cli",
            "--algo", "dqn",
            "--symbol", "SYNTH",
            "--start", "2015-01-05",
            "--end", "2018-06-30",
            "--timesteps", "200",
            "--eval-freq", "0",
            "--set", "learning_rate=1e-3",
        ])
    finally:
        train_module.train_run = original
    assert code == 0
    first = capsys.readouterr().out.splitlines()[0]
    header = json.loads(first)
    assert header["event"] == "train-start"
    assert header["overrides"] == {"learning_rate": 1e-3}
