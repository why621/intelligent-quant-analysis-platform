"""Mechanism tests; synthetic fixtures are not financial performance evidence."""

import copy

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from test_portfolio_rl import frames, manifest  # noqa: E402

from quant_platform.models import TradingCosts  # noqa: E402
from quant_platform.rl.masked_portfolio import (  # noqa: E402
    FEATURES,
    MaskedSACLearner,
    MaskedSACNetwork,
)
from quant_platform.rl.masked_train import (  # noqa: E402
    combine_pool_transition,
    evaluate_research,
    load_research,
    sample_reconstruction,
    save_research,
    train_masked,
)
from quant_platform.rl.portfolio_features import (  # noqa: E402
    MAX_ASSETS,
    SLOT_SIZE,
    action_weights,
    encode_observation,
    prepare_panel,
)
from quant_platform.rl.portfolio_train import training_frames  # noqa: E402

pytestmark = pytest.mark.rl


@pytest.fixture(autouse=True)
def reproducible():
    torch.set_num_threads(1)
    torch.manual_seed(17)


def observation(count):
    features = np.random.default_rng(3).normal(size=(count, FEATURES))
    return torch.tensor(encode_observation(features, np.ones(count), np.ones(count), 5))[None]


@pytest.mark.parametrize("count", [2, 3, 10])
def test_true_network_equivariance_and_padding(count):
    net = MaskedSACNetwork(20).eval()
    obs = observation(count)
    scores, _ = net.sample(obs, deterministic=True)
    assert torch.count_nonzero(scores[:, count:MAX_ASSETS]) == 0
    weights = action_weights(scores.detach().numpy()[0], count)
    assert weights.sum() == pytest.approx(1)
    permutation = torch.randperm(MAX_ASSETS)
    slots = obs[:, :-1].reshape(1, MAX_ASSETS, SLOT_SIZE)
    permuted = torch.cat((slots[:, permutation].flatten(1), obs[:, -1:]), 1)
    reordered, _ = net.sample(permuted, deterministic=True)
    expected = torch.cat((scores[:, :-1][:, permutation], scores[:, -1:]), 1)
    torch.testing.assert_close(reordered, expected, atol=2e-6, rtol=2e-6)
    for original, changed in zip(
        net.values(obs, scores), net.values(permuted, expected), strict=True
    ):
        torch.testing.assert_close(original, changed, atol=2e-6, rtol=2e-6)
    polluted = slots.clone()
    polluted[:, count:, :FEATURES] = 100000
    changed = torch.cat((polluted.flatten(1), obs[:, -1:]), 1)
    torch.testing.assert_close(net.sample(changed, deterministic=True)[0], scores)


def reconstruction_batch():
    features = torch.randn(4, 5, FEATURES)
    active = torch.ones(4, 5, dtype=torch.bool)
    hidden = torch.zeros_like(active)
    hidden[:, 1:4] = True
    ids = torch.arange(5).expand(4, -1)
    return features, active, hidden, ids


def test_hidden_values_cannot_leak_and_reconstruction_learns():
    net = MaskedSACNetwork(5)
    features, active, hidden, ids = reconstruction_batch()
    before = net.reconstruct(features, active, hidden, ids)
    changed = features.clone()
    changed[hidden] += 1000
    torch.testing.assert_close(before, net.reconstruct(changed, active, hidden, ids))
    optimizer = torch.optim.Adam(net.parameters(), lr=0.003)
    first = float(net.reconstruction_loss(features, active, hidden, ids).detach())
    for _ in range(25):
        optimizer.zero_grad()
        loss = net.reconstruction_loss(features, active, hidden, ids)
        loss.backward()
        optimizer.step()
    assert float(net.reconstruction_loss(features, active, hidden, ids).detach()) < first
    assert net.encoder.project.weight.grad.abs().sum() > 0
    assert net.mask_token.grad.abs().sum() > 0
    with pytest.raises(ValueError, match="visible"):
        net.reconstruct(features, active, active, ids)


def test_sac_updates_actor_critic_encoder_and_finite_entropy():
    net = MaskedSACNetwork(5)
    learner = MaskedSACLearner(net)
    obs = observation(3).repeat(4, 1)
    before = {key: value.clone() for key, value in net.state_dict().items()}
    actions = net.sample(obs)[0].detach()
    losses = learner.update(
        obs, actions, torch.zeros(4, 1), obs, torch.zeros(4, 1), reconstruction_batch()
    )
    assert np.isfinite(list(losses.values())).all()
    for key in ("actor.0.weight", "q1.0.weight", "encoder.project.weight"):
        assert not torch.equal(before[key], net.state_dict()[key])
    assert learner.updates == 1


def test_diagnostics_preserve_rng_and_parameter_updates():
    net = MaskedSACNetwork(5)
    measured = copy.deepcopy(net)
    plain = MaskedSACLearner(net)
    instrumented = MaskedSACLearner(measured)
    obs = observation(3).repeat(4, 1)
    action = net.sample(obs)[0].detach()
    batch = (obs, action, torch.full((4, 1), 0.002), obs, torch.zeros(4, 1),
             reconstruction_batch())
    torch.manual_seed(99)
    plain.update(*batch)
    expected_rng = torch.get_rng_state()
    torch.manual_seed(99)
    result = instrumented.update(*batch, diagnose=True)
    assert torch.equal(expected_rng, torch.get_rng_state())
    for key, value in net.state_dict().items():
        torch.testing.assert_close(value, measured.state_dict()[key], atol=0, rtol=0)
    assert np.isfinite(list(result.values())).all()
    assert result["maeEncoderDeltaNorm"] > 0


def test_auxiliary_zero_rate_preserves_rl_encoder_while_decoder_learns():
    masked = MaskedSACNetwork(5)
    reference = copy.deepcopy(masked)
    reference.variant = "attention"
    learner = MaskedSACLearner(masked, mae_encoder_learning_rate=0)
    control = MaskedSACLearner(reference)
    obs = observation(3).repeat(4, 1)
    batch = (obs, torch.full((4, 11), 0.5), torch.full((4, 1), 0.002),
             obs, torch.zeros(4, 1), reconstruction_batch())
    decoder_before = masked.decoder.weight.detach().clone()
    for seed in (99, 100, 101):
        torch.manual_seed(seed)
        control.update(*batch)
        torch.manual_seed(seed)
        diagnostics = learner.update(*batch, diagnose=True)
        assert diagnostics["maeEncoderDeltaNorm"] == 0
        assert diagnostics["criticEncoderDeltaNorm"] > 0
        for key, value in reference.state_dict().items():
            if key.startswith(("encoder.", "actor.", "q1.", "q2.")):
                torch.testing.assert_close(value, masked.state_dict()[key], atol=0, rtol=0)
    assert not torch.equal(decoder_before, masked.decoder.weight)


def test_auxiliary_default_compatibility_and_reduced_step():
    template = MaskedSACNetwork(5)
    obs = observation(3).repeat(4, 1)
    batch = (obs, torch.full((4, 11), 0.5), torch.zeros(4, 1),
             obs, torch.zeros(4, 1), reconstruction_batch())
    results = []
    for rate in (None, 3e-4, 3e-5):
        net = copy.deepcopy(template)
        learner = MaskedSACLearner(net, mae_encoder_learning_rate=rate)
        torch.manual_seed(99)
        results.append((net, learner.update(*batch, diagnose=True)))
    for key, value in results[0][0].state_dict().items():
        torch.testing.assert_close(value, results[1][0].state_dict()[key], atol=0, rtol=0)
    assert results[2][1]["maeEncoderDeltaNorm"] == pytest.approx(
        results[1][1]["maeEncoderDeltaNorm"] * 0.1, rel=0.002
    )


def test_two_session_target_uses_discounted_reward_and_bootstrap():
    net = MaskedSACNetwork(5)
    learner = MaskedSACLearner(net)
    obs = observation(3).repeat(4, 1)
    actions = torch.full((4, 11), 0.5)
    reward, discount = combine_pool_transition(0.03, -0.02)
    assert reward == pytest.approx(0.0102)
    rewards = torch.full((4, 1), reward)
    discounts = torch.full((4, 1), discount)
    done = torch.tensor([[0.0], [1.0], [0.0], [1.0]])
    batch = reconstruction_batch()
    torch.manual_seed(123)
    with torch.no_grad():
        next_action, logp = net.sample(obs)
        q1, q2 = learner.target.values(obs, next_action)
        target = rewards + discounts * (1 - done) * (
            torch.minimum(q1, q2) - learner.log_alpha.exp() * logp
        )
        current1, current2 = net.values(obs, actions)
        expected = ((current1 - target).square().mean()
                    + (current2 - target).square().mean()).item()
    torch.manual_seed(123)
    result = learner.update(obs, actions, rewards, obs, done, batch, discounts=discounts)
    assert result["criticLoss"] == pytest.approx(expected)
    with pytest.raises(ValueError, match="discounts"):
        learner.update(obs, actions, rewards, obs, done, batch,
                       discounts=torch.ones(4))  # Broadcasting is explicitly forbidden.


def test_masked_serving_bundle_roundtrip_and_smoke_release_rejection(tmp_path):
    import hashlib
    import json

    from quant_platform.rl.masked_serving import MaskedServingPolicy
    from quant_platform.rl.portfolio_policy import load_portfolio_bundle, save_portfolio_bundle
    from quant_platform.rl.portfolio_strategy import JointPortfolioStrategy

    metadata = manifest(frames(5))
    metadata.update(algo="masked_sac", architecture="masked-set-sac-research-v1",
                    encoderWidth=32, variant="masked_attention", purpose="local_smoke_only",
                    actualTimesteps=256, optimizerUpdates=225)
    model = MaskedServingPolicy(MaskedSACNetwork(5))
    path = save_portfolio_bundle(model, tmp_path, metadata)
    restored = load_portfolio_bundle(path)
    np.testing.assert_array_equal(
        model.predict(observation(5).numpy())[0],
        restored.model.predict(observation(5).numpy())[0],
    )
    evidence = json.dumps({"bundleHash": restored.manifest["bundleHash"],
                          "ledgerPassed": True, "simultaneousAssets": 10}).encode()
    (path / "evaluation.json").write_bytes(evidence)
    release = {"bundleHash": restored.manifest["bundleHash"],
               "evaluationSha256": hashlib.sha256(evidence).hexdigest()}
    with pytest.raises(ValueError, match="formal training"):
        JointPortfolioStrategy(path, release)
    weights = path / "model.zip"
    weights.write_bytes(weights.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="integrity"):
        load_portfolio_bundle(path)


def test_training_switches_pools_reproducibly_and_saves_configuration(tmp_path):
    source = frames(5, 200)
    splits = {"trainStartDate": "2024-01-02",
              "trainEndDate": source["A0"]["date"].iloc[179].date().isoformat()}
    outputs = []
    for run in ("one", "two"):
        outputs.append(train_masked(
            source, asset_types=dict.fromkeys(source, "stock"), splits=splits,
            destination=tmp_path / run, steps=64, max_seconds=60, episode_bars=8,
            pool_switch_interval=2, checkpoints=(32,),
        ))
    first, second = outputs
    assert first[1]["poolEventCount"] > 0
    assert first[1]["marketSteps"] == 64 + first[1]["poolEventCount"]
    assert first[1]["poolEvents"] == second[1]["poolEvents"]
    assert all(not e["actionApplied"] for e in first[1]["poolEvents"])
    for key, value in first[0].state_dict().items():
        torch.testing.assert_close(value, second[0].state_dict()[key], rtol=0, atol=0)
    _, metadata = load_research(tmp_path / "one")
    _, checkpoint = load_research(tmp_path / "one-step-32")
    assert metadata["poolSwitchInterval"] == checkpoint["poolSwitchInterval"] == 2
    assert metadata["poolChanges"] == "in_episode_exogenous_transition"


@pytest.mark.parametrize("rate", [-1, float("nan"), float("inf"), 1.01])
def test_invalid_auxiliary_rates_rejected(rate):
    with pytest.raises(ValueError, match="auxiliary encoder"):
        MaskedSACLearner(MaskedSACNetwork(5), mae_encoder_learning_rate=rate)


@pytest.mark.parametrize("scale", [0, -1, float("nan"), float("inf"), 1001])
def test_invalid_reward_scales_rejected(scale):
    with pytest.raises(ValueError, match="reward scale"):
        MaskedSACLearner(MaskedSACNetwork(5), reward_scale=scale)


@pytest.mark.parametrize("variant", ["mlp", "attention", "masked_attention"])
def test_ablation_and_variant_roundtrip(variant, tmp_path):
    net = MaskedSACNetwork(5, variant=variant)
    learner = MaskedSACLearner(net)
    obs = observation(3).repeat(4, 1)
    before = net.decoder.weight.detach().clone()
    action = net.sample(obs)[0].detach()
    result = learner.update(
        obs, action, torch.zeros(4, 1), obs, torch.zeros(4, 1), reconstruction_batch()
    )
    if variant == "masked_attention":
        assert not torch.equal(before, net.decoder.weight)
        assert result["reconstructionLoss"] > 0
    else:
        torch.testing.assert_close(before, net.decoder.weight, rtol=0, atol=0)
        assert result["reconstructionLoss"] == 0
    save_research(net, tmp_path / variant, {})
    restored, _ = load_research(tmp_path / variant)
    assert restored.variant == variant
    np.testing.assert_array_equal(net.predict(obs.numpy())[0], restored.predict(obs.numpy())[0])


def test_reconstruction_sampling_cannot_use_future_partition():
    source = frames(3, 240)
    boundary = source["A0"]["date"].iloc[179].date().isoformat()
    splits = {"trainStartDate": "2024-01-02", "trainEndDate": boundary}
    panel = prepare_panel(training_frames(source, splits))
    modified = {key: value.copy() for key, value in source.items()}
    for value in modified.values():
        value.loc[180:, ["open", "high", "low", "close"]] *= 100
    future_changed = prepare_panel(training_frames(modified, splits))
    assert panel.data_hashes == future_changed.data_hashes
    original = sample_reconstruction(panel, np.random.default_rng(42))
    changed = sample_reconstruction(future_changed, np.random.default_rng(42))
    for left, right in zip(original, changed, strict=True):
        torch.testing.assert_close(left, right)


def test_training_slice_save_load_oos_and_corruption(tmp_path):
    source = frames(3, 240)
    dates = source["A0"]["date"]
    splits = {
        "trainStartDate": dates.iloc[0].date().isoformat(),
        "trainEndDate": dates.iloc[179].date().isoformat(),
        "valStartDate": dates.iloc[180].date().isoformat(),
        "valEndDate": dates.iloc[199].date().isoformat(),
        "testStartDate": dates.iloc[200].date().isoformat(),
        "testEndDate": dates.iloc[-1].date().isoformat(),
    }
    types = dict.fromkeys(source, "stock")
    network, report = train_masked(
        source, asset_types=types, splits=splits, destination=tmp_path / "smoke",
        steps=64, max_seconds=60, episode_bars=8,
        reward_scale=100, diagnostic_interval=32, checkpoints=(32,),
        mae_encoder_learning_rate=3e-5,
    )
    assert report["optimizerUpdates"] == 33
    assert report["maeEncoderLearningRate"] == 3e-5
    assert all(item["endDate"] <= splits["trainEndDate"] for item in report["sampling"])
    assert report["validationExecuted"] is False
    assert report["checkpointSteps"] == [32]
    assert len(report["diagnostics"]) == 2
    for row in report["diagnostics"]:
        assert row["scaledRewardAbsMean"] == pytest.approx(row["rawRewardAbsMean"] * 100)
    _, checkpoint = load_research(tmp_path / "smoke-step-32")
    assert checkpoint["actualSteps"] == 32 and checkpoint["rewardScale"] == 100
    assert checkpoint["maeEncoderLearningRate"] == 3e-5
    replay = evaluate_research(
        network, source, asset_types=types, costs=TradingCosts(),
        start=splits["testStartDate"], end=splits["testEndDate"],
        in_sample_end=splits["valEndDate"],
    )
    assert len(replay["curve"]) == 40
    assert all(item["cash"] >= 0 for item in replay["curve"])
    with pytest.raises(ValueError, match="out of sample"):
        evaluate_research(
            network, source, asset_types=types, costs=TradingCosts(),
            start=splits["trainEndDate"], end=splits["testEndDate"],
            in_sample_end=splits["valEndDate"],
        )
    restored, metadata = load_research(tmp_path / "smoke")
    assert metadata["releaseEligible"] is False
    assert metadata["maeEncoderLearningRate"] == 3e-5
    np.testing.assert_array_equal(
        network.predict(observation(3)[0].numpy())[0],
        restored.predict(observation(3)[0].numpy())[0],
    )
    weights = tmp_path / "smoke" / "research.pt"
    weights.write_bytes(weights.read_bytes() + b"corruption")
    with pytest.raises(ValueError, match="corrupt"):
        load_research(tmp_path / "smoke")
