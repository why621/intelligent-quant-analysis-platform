"""Distinct TD3 objective, delay, smoothing and shared-account training tests."""

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from test_masked_portfolio import observation, reconstruction_batch  # noqa: E402
from test_portfolio_rl import frames  # noqa: E402

from quant_platform.rl.masked_td3 import MaskedTD3Learner, MaskedTD3Network  # noqa: E402
from quant_platform.rl.masked_train import train_masked  # noqa: E402
from quant_platform.rl.portfolio_features import MAX_ASSETS, SLOT_SIZE  # noqa: E402

pytestmark = pytest.mark.rl


@pytest.fixture(autouse=True)
def deterministic():
    torch.set_num_threads(1)
    torch.manual_seed(42)


@pytest.mark.parametrize("count", [2, 3, 10])
def test_td3_equivariance_and_noise_mask(count):
    net = MaskedTD3Network(20)
    obs = observation(count)
    scores = net.sample(obs, deterministic=True)[0]
    permutation = torch.randperm(MAX_ASSETS)
    slots = obs[:, :-1].reshape(1, MAX_ASSETS, SLOT_SIZE)
    permuted = torch.cat((slots[:, permutation].flatten(1), obs[:, -1:]), 1)
    expected = torch.cat((scores[:, :-1][:, permutation], scores[:, -1:]), 1)
    torch.testing.assert_close(net.sample(permuted, deterministic=True)[0], expected)
    for q, qp in zip(net.values(obs, scores), net.values(permuted, expected), strict=True):
        torch.testing.assert_close(q, qp)
    learner = MaskedTD3Learner(net)
    smoothed = learner.target_actions(obs.repeat(64, 1))
    assert (smoothed >= 0).all() and (smoothed <= 1).all()
    assert torch.count_nonzero(smoothed[:, count:10]) == 0
    assert ((smoothed - scores).abs() <= 0.5 + 1e-7).all()
    assert not torch.equal(smoothed[0], smoothed[1])
    polluted = slots.clone()
    polluted[:, count:, :-2] = 10000
    torch.testing.assert_close(
        net.sample(torch.cat((polluted.flatten(1), obs[:, -1:]), 1), deterministic=True)[0],
        scores,
    )


def test_td3_delayed_actor_target_and_exact_discounted_critic_objective():
    net = MaskedTD3Network(5)
    learner = MaskedTD3Learner(net)
    obs = observation(3).repeat(4, 1)
    actions = net.sample(obs, deterministic=True)[0].detach()
    rewards, done = torch.full((4, 1), .01), torch.tensor([[0.], [1.], [0.], [1.]])
    discounts = torch.full((4, 1), .99 ** 2)
    actor = {n: p.clone() for n, p in net.actor.state_dict().items()}
    target_before = {n: p.clone() for n, p in learner.target.state_dict().items()}
    loss = learner.update(obs, actions, rewards, obs, done, reconstruction_batch(),
                          discounts=discounts)
    assert np.isfinite(loss["criticLoss"])
    assert learner.actor_updates == 0
    for n, p in net.actor.state_dict().items():
        torch.testing.assert_close(actor[n], p, atol=0, rtol=0)
    for n, p in learner.target.state_dict().items():
        torch.testing.assert_close(target_before[n], p, atol=0, rtol=0)
    batch = reconstruction_batch()
    torch.manual_seed(78)
    with torch.no_grad():
        a = learner.target_actions(obs)
        q1, q2 = learner.target.values(obs, a)
        target = rewards + discounts * (1 - done) * torch.minimum(q1, q2)
        q1, q2 = net.values(obs, actions)
        expected = ((q1 - target).square().mean() + (q2 - target).square().mean()).item()
    torch.manual_seed(78)
    loss = learner.update(obs, actions, rewards, obs, done, batch, discounts=discounts)
    assert loss["criticLoss"] == pytest.approx(expected)
    assert learner.actor_updates == 1 and not hasattr(learner, "log_alpha")
    assert any(not torch.equal(actor[n], p) for n, p in net.actor.state_dict().items())
    for n, p in learner.target.state_dict().items():
        torch.testing.assert_close(p, target_before[n].lerp(net.state_dict()[n], .005))
    with pytest.raises(ValueError, match="discounts"):
        learner.update(obs, actions, rewards, obs, done, batch, discounts=torch.ones(4))


def test_small_td3_switching_train_save_load(tmp_path):
    source = frames(10, 220)
    dates = source["A0"]["date"]
    _, evidence = train_masked(
        source, asset_types=dict.fromkeys(source, "etf"),
        splits={"trainStartDate": str(dates.iloc[0].date()),
                "trainEndDate": str(dates.iloc[-1].date())},
        destination=tmp_path / "td3", steps=64, max_seconds=60,
        algorithm="masked_td3", pool_switch_interval=4,
    )
    assert evidence["actualSteps"] == 64 and evidence["optimizerUpdates"] == 33
    assert evidence["actorUpdates"] == 16 and evidence["poolEventCount"] > 0
    assert evidence["marketSteps"] > 64
