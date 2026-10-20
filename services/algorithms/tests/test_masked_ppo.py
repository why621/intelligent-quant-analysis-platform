"""PPO mechanism evidence, not investment-performance evidence."""

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from test_masked_portfolio import observation, reconstruction_batch  # noqa: E402
from test_portfolio_rl import frames  # noqa: E402

from quant_platform.rl.masked_onpolicy_train import train_masked_ppo  # noqa: E402
from quant_platform.rl.masked_ppo import (  # noqa: E402
    MaskedPPOLearner,
    MaskedPPONetwork,
    generalized_advantages,
)
from quant_platform.rl.portfolio_features import MAX_ASSETS, SLOT_SIZE  # noqa: E402

pytestmark = pytest.mark.rl


@pytest.fixture(autouse=True)
def deterministic():
    torch.set_num_threads(1)
    torch.manual_seed(42)


@pytest.mark.parametrize("count", [2, 3, 10])
def test_ppo_equivariance_value_and_saved_log_probability(count):
    network = MaskedPPONetwork(20)
    obs = observation(count)
    action, latent, old_logp, value = network.act(obs[0].numpy())
    logp, v = network.policy_terms(obs, torch.tensor(latent)[None])
    assert logp.item() == pytest.approx(old_logp)
    assert v.item() == pytest.approx(value)
    assert np.count_nonzero(action[count:10]) == 0
    scores = network.predict(obs.numpy())[0]
    permutation = torch.randperm(MAX_ASSETS)
    slots = obs[:, :-1].reshape(1, MAX_ASSETS, SLOT_SIZE)
    permuted = torch.cat((slots[:, permutation].flatten(1), obs[:, -1:]), 1)
    expected = np.concatenate((scores[:, :-1][:, permutation], scores[:, -1:]), 1)
    np.testing.assert_allclose(network.predict(permuted.numpy())[0], expected, atol=2e-6)
    torch.testing.assert_close(
        network.distribution_value(obs)[1], network.distribution_value(permuted)[1]
    )
    polluted = slots.clone()
    polluted[:, count:, :-2] = 10000
    np.testing.assert_allclose(
        network.predict(torch.cat((polluted.flatten(1), obs[:, -1:]), 1).numpy())[0],
        scores, atol=1e-7,
    )


def test_gae_two_session_discount_and_terminal_reset():
    advantages, returns = generalized_advantages(
        [1, 2, 100], [0, 0, 0], [0, 0, 0], [0, 1, 1],
        [.99 ** 2, .99, .99], [2, 1, 1],
    )
    np.testing.assert_allclose(advantages, [1 + .99 ** 2 * .95 ** 2 * 2, 2, 100])
    np.testing.assert_array_equal(advantages, returns)
    advantages, _ = generalized_advantages([1], [2], [3], [0], [.99], [1])
    assert advantages[0] == pytest.approx(1 + .99 * 3 - 2)


def test_ppo_updates_policy_value_encoder_and_reconstruction():
    net = MaskedPPONetwork(5)
    learner = MaskedPPOLearner(net)
    obs = observation(3).repeat(32, 1)
    records = [net.act(o.numpy()) for o in obs]
    before = {name: p.detach().clone() for name, p in net.named_parameters()}
    losses = learner.update((
        obs, np.array([x[1] for x in records]), np.array([x[2] for x in records]),
        np.linspace(-1, 1, 32), np.linspace(-.5, .5, 32),
    ), reconstruction_batch())
    assert learner.updates == 4
    assert np.isfinite(list(losses.values())).all()
    for prefix in ["actor", "value_head", "encoder", "decoder"]:
        assert any(not torch.equal(before[n], p) for n, p in net.named_parameters()
                   if n.startswith(prefix))
    assert not hasattr(net, "q1")


def test_ppo_clip_objective_handles_both_advantage_signs():
    net = MaskedPPONetwork(5)
    learner = MaskedPPOLearner(net)
    obs = observation(3).repeat(4, 1)
    latent = torch.zeros(4, 11)
    with torch.no_grad():
        logp, _ = net.policy_terms(obs, latent)
        old_logp = logp - torch.tensor([1.5, .5, 1.5, .5]).log()
    original = old_logp.clone()
    loss = learner.update(
        (obs, latent, old_logp, [1, 1, -1, -1], [0, 0, 0, 0]),
        reconstruction_batch(), epochs=1, batch_size=4,
    )
    # min surrogate terms = [1.2, .5, -1.5, -.8]; negative mean = .15.
    assert loss["actorLoss"] == pytest.approx(.15, abs=2e-6)
    torch.testing.assert_close(old_logp, original, atol=0, rtol=0)


def test_small_ppo_switching_train_save_load(tmp_path):
    source = frames(10, 220)
    dates = source["A0"]["date"]
    _, evidence = train_masked_ppo(
        source, asset_types=dict.fromkeys(source, "etf"),
        splits={"trainStartDate": str(dates.iloc[0].date()),
                "trainEndDate": str(dates.iloc[-1].date())},
        destination=tmp_path / "ppo", steps=64, max_seconds=60,
    )
    assert evidence["actualSteps"] == 64
    assert evidence["optimizerUpdates"] == 8
    assert evidence["poolEventCount"] > 0
    assert evidence["marketSteps"] > 64
    assert evidence["replayBuffer"] is False
