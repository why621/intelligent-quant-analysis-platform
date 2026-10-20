"""Explicit safe tensor adapters; the manifest's algorithm chooses the network."""

from types import SimpleNamespace

import torch

from quant_platform.rl.masked_portfolio import MaskedSACNetwork


class MaskedServingPolicy:
    def __init__(self, network):
        self.network = network.eval()
        self.observation_space = SimpleNamespace(shape=(161,))
        self.action_space = SimpleNamespace(shape=(11,))

    def predict(self, observation, deterministic=True):
        return self.network.predict(observation, deterministic=deterministic)

    def save(self, path):
        # The outer bundle schema retains model.zip; contents are Torch tensor weights.
        torch.save(self.network.state_dict(), path)

    @classmethod
    def load(cls, path, manifest):
        torch.set_num_threads(1)
        from quant_platform.rl.masked_ppo import MaskedPPONetwork
        from quant_platform.rl.masked_td3 import MaskedTD3Network

        network_class = {"masked_sac": MaskedSACNetwork, "masked_ppo": MaskedPPONetwork,
                         "masked_td3": MaskedTD3Network}[
            manifest["algo"]
        ]
        network = network_class(
            len(manifest["trainingUniverse"]), width=manifest["encoderWidth"],
            variant=manifest["variant"],
        )
        network.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
        return cls(network)
