"""Independent cross-asset evidence gate; never rewrites a training manifest."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from quant_platform.rl.portfolio_policy import inference_boundary


def validated_serving_scope(path, manifest, release):
    """Return the reviewed scope only when complete, bundle-bound replay evidence exists."""
    scope = release.get("assetScope", "training_symbols")
    if scope == "training_symbols":
        if release.get("costPolicy", "training_fixed") != "training_fixed":
            raise ValueError("legacy joint release must retain fixed training costs")
        return None, None
    if scope != "published_universe" or release.get("costPolicy") != "request_configurable":
        raise ValueError("invalid joint release scope or cost policy")
    types = release.get("supportedAssetTypes")
    if (
        not isinstance(types, dict)
        or len(types) < 10
        or any(not isinstance(s, str) or not s for s in types)
        or set(types.values()) != {"stock", "etf"}
        or not set(manifest["trainingUniverse"]).issubset(types)
        or any(types[s] != kind for s, kind in manifest["assetTypes"].items())
        or set(manifest["assetTypes"].values()) != {"stock", "etf"}
    ):
        raise ValueError(
            "published scope requires an explicit stock/ETF catalog and mixed training"
        )
    raw = (path / "cross-asset-evaluation.json").read_bytes()
    evidence = json.loads(raw)
    if (
        hashlib.sha256(raw).hexdigest() != release.get("crossAssetEvidenceSha256")
        or evidence.get("evidenceKind") != "real_market_cross_asset_replay"
        or evidence.get("bundleHash") != manifest["bundleHash"]
        or evidence.get("targetUniverseVersion") != release.get("targetUniverseVersion")
        or not release.get("scopeDataVersion")
        or evidence.get("scopeDataVersion") != release["scopeDataVersion"]
        or evidence.get("supportedAssetTypes") != types
        or any(
            evidence.get(flag) is not True
            for flag in (
                "ledgerPassed",
                "permutationPassed",
                "mixedAssetTypesPassed",
                "costAdaptationPassed",
                "cashReservePassed",
            )
        )
    ):
        raise ValueError("published scope lacks matching cross-asset evaluation evidence")
    coverage, held_out = evidence.get("coverageSymbols"), evidence.get("heldOutSymbols")
    if (
        not isinstance(coverage, list)
        or len(coverage) != len(set(coverage))
        or set(coverage) != set(types)
        or not isinstance(held_out, list)
        or len(set(held_out)) < 2
        or not set(held_out).issubset(set(types) - set(manifest["trainingUniverse"]))
    ):
        raise ValueError("cross-asset coverage must include the full catalog and held-out assets")
    observed, mixed = set(), False
    for replay in evidence.get("replays", []):
        symbols = replay.get("symbols", [])
        if (
            not isinstance(symbols, list)
            or not 2 <= len(symbols) <= 10
            or len(symbols) != len(set(symbols))
            or not set(symbols).issubset(types)
            or replay.get("ledgerPassed") is not True
            or replay.get("permutationPassed") is not True
            or not (
                inference_boundary(manifest)
                < date.fromisoformat(replay["startDate"])
                < date.fromisoformat(replay["endDate"])
            )
        ):
            raise ValueError("invalid cross-asset replay ledger or chronological window")
        observed.update(symbols)
        mixed |= len({types[s] for s in symbols}) == 2
    if observed != set(types) or not mixed:
        raise ValueError("cross-asset replays do not cover the published catalog and mixed assets")
    return dict(release), evidence
