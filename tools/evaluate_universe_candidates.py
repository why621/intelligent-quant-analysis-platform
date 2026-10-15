"""Evaluate frozen CR069 selections on real held-out assets; never fit or select here."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from quant_platform.models import TradingCosts
from quant_platform.rl.portfolio_evaluation import evaluate_portfolio
from quant_platform.rl.portfolio_policy import load_portfolio_bundle


def write_json(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def assert_ledger(result, frames, nontrading):
    cash = 100000.0
    quantities = {s: 0.0 for s in result["symbols"]}
    for p in result["accountCurve"]:
        when = date.fromisoformat(p["date"])
        for fill in p.get("fills", []):
            s = fill["symbol"]
            if when in nontrading.get(s, set()):
                raise AssertionError("trade on a verified nontrading session")
            sign = 1 if fill["side"] == "buy" else -1
            quantities[s] += sign * fill["quantity"]
            cash -= (
                sign * fill["amount_cny"]
                + fill["commission_cny"]
                + fill["stamp_duty_cny"]
            )
        np.testing.assert_allclose(cash, p["cash"], atol=1e-6, rtol=1e-10)
        np.testing.assert_allclose(
            [quantities[s] for s in p["symbols"]], p["quantities"], atol=1e-7
        )
        value = cash
        market_values = {}
        for s, q in quantities.items():
            f = frames[s]
            prices = f.loc[pd.to_datetime(f.date) <= pd.Timestamp(when), "close"]
            if prices.empty:
                raise AssertionError("no real prior valuation price")
            market_values[s] = q * float(prices.iloc[-1])
            value += market_values[s]
        np.testing.assert_allclose(value, p["equity"], atol=1e-6, rtol=1e-10)
        np.testing.assert_allclose(sum(p["weights"]) + p["cashWeight"], 1, atol=1e-9)
        np.testing.assert_allclose(
            p["weights"], [market_values[s] / value for s in p["symbols"]], atol=1e-9
        )
        np.testing.assert_allclose(p["cashWeight"], cash / value, atol=1e-9)
        if cash < -1e-6 or min(quantities.values()) < -1e-7:
            raise AssertionError("negative shared-account holding")


def evaluate(experiment: Path, publication: Path):
    selection_bytes = (experiment / "selection.json").read_bytes()
    selected = json.loads(selection_bytes)
    training_report = json.loads((experiment / "training-report.json").read_bytes())
    assert training_report["selected"] == selected, (
        "selection differs from frozen training report"
    )
    assert (
        training_report["planSha256"]
        == hashlib.sha256((experiment / "plan.json").read_bytes()).hexdigest()
    ), "training plan changed"
    plan = json.loads((experiment / "plan.json").read_text(encoding="utf-8"))
    source = publication / "releases" / (plan["publicationId"] + ".json")
    if hashlib.sha256(source.read_bytes()).hexdigest() != plan["sourceSha256"]:
        raise ValueError("source publication changed")
    source_doc = json.loads(source.read_bytes())
    frames = {}
    for s in plan["symbols"]:
        p = experiment / "data" / (s + ".csv")
        if hashlib.sha256(p.read_bytes()).hexdigest() != plan["dataHashes"][s]:
            raise ValueError("frozen price input changed")
        frames[s] = pd.read_csv(p)
    days = [pd.Timestamp(d).date() for d in frames["510300"].date]
    nontrading = {s: set() for s in frames}
    for event in source_doc["tradingEvents"]:
        if event["reason"] == "suspension":
            symbol = event["asset_id"].split(":")[-1]
            nontrading[symbol].update(
                d for d in days if event["start"] <= d.isoformat() <= event["end"]
            )
    symbols = sorted(frames)
    groups = {
        f"coverage-{i // 10:02}": symbols[i : i + 10]
        for i in range(0, len(symbols), 10)
    }
    held_out = plan["heldOutSymbols"]
    groups.update(
        {
            f"heldout-{i // 10}": held_out[i : i + 10]
            for i in range(0, len(held_out), 10)
        }
    )
    groups.update({"reference-" + k: v for k, v in plan["validationGroups"].items()})
    start, end = plan["splits"]["testStartDate"], plan["splits"]["testEndDate"]
    release = {"schemaVersion": 1, "models": []}
    reports = {}
    for algo, chosen in selected.items():
        path = experiment / "models" / chosen["runId"]
        bundle = load_portfolio_bundle(path)
        assert bundle.manifest["bundleHash"] == chosen["bundleHash"]
        assert not set(bundle.manifest["trainingUniverse"]) & set(held_out)
        replays, results = [], {}
        for index, (name, members) in enumerate(groups.items()):
            current = {s: frames[s] for s in members}
            common = {
                "start": start,
                "end": end,
                "asset_types": plan["assetTypes"],
                "nontrading_sessions": nontrading,
            }
            result = evaluate_portfolio(bundle, current, **common)
            reverse = evaluate_portfolio(
                bundle, dict(reversed(list(current.items()))), **common
            )
            assert_ledger(result, frames, nontrading)
            assert result == reverse, (
                "request asset order changed a canonical joint result"
            )
            results[name] = result
            if index % 10 == 0:
                print(
                    json.dumps(
                        {
                            "algorithm": algo,
                            "checkedGroups": index + 1,
                            "totalGroups": len(groups),
                        }
                    ),
                    flush=True,
                )
            replays.append(
                {
                    "name": name,
                    "symbols": result["symbols"],
                    "startDate": result["startDate"],
                    "endDate": result["endDate"],
                    "ledgerPassed": True,
                    "permutationPassed": True,
                    "metrics": result["metrics"],
                }
            )
        mixed = {s: frames[s] for s in plan["validationGroups"]["mixed"]}
        custom = TradingCosts(
            commission_pct=0.07,
            stamp_duty_pct=0.05,
            slippage_pct=0.04,
            stamp_duty_mode="asset_date",
        )
        extra = evaluate_portfolio(
            bundle,
            mixed,
            start=start,
            end=end,
            asset_types=plan["assetTypes"],
            nontrading_sessions=nontrading,
            trading_costs=custom,
            cash_pct=25,
        )
        assert_ledger(extra, frames, nontrading)
        for p in extra["accountCurve"]:
            for f in p.get("fills", []):
                np.testing.assert_allclose(
                    f["commission_cny"], f["amount_cny"] * 0.0007, rtol=1e-9, atol=1e-8
                )
                if plan["assetTypes"][f["symbol"]] == "etf" or f["side"] == "buy":
                    assert f["stamp_duty_cny"] == 0
        control = evaluate_portfolio(
            bundle,
            mixed,
            start=start,
            end=end,
            asset_types=plan["assetTypes"],
            nontrading_sessions=nontrading,
            trading_costs=custom,
            cash_pct=0,
        )
        assert_ledger(control, frames, nontrading)
        # At the first execution both policies see the same all-cash observation.
        # The reserve scales asset targets to 75%; fees and order minima may reduce fills further.
        original = control["accountCurve"][1]
        reserved = extra["accountCurve"][1]
        assert original.get("fills") and reserved.get("fills"), (
            "reserve/cost check requires actual trades"
        )
        assert reserved["cash"] > original["cash"]
        np.testing.assert_allclose(
            np.array(reserved["targetWeights"])[:10],
            np.array(original["targetWeights"])[:10] * 0.75,
            atol=1e-9,
        )
        np.testing.assert_allclose(
            reserved["targetWeights"][-1],
            1 - sum(reserved["targetWeights"][:10]),
            atol=1e-9,
        )
        opens = np.array(
            [
                float(
                    mixed[s]
                    .loc[
                        pd.to_datetime(mixed[s].date) == pd.Timestamp(reserved["date"]),
                        "open",
                    ]
                    .iloc[0]
                )
                for s in reserved["symbols"]
            ]
        )
        desired = np.array(reserved["targetWeights"][: len(opens)]) * 100000 / opens
        threshold = max(
            bundle.manifest.get("rebalanceBandPct", 0) * 100000,
            bundle.manifest.get("minTradeCny", 0),
        )
        desired = np.where(desired * opens >= threshold, desired, 0)
        required = float(sum(desired * opens * 1.0004 * 1.0007))
        factor = min(1, 100000 / required) if required else 0
        np.testing.assert_allclose(
            reserved["quantities"], desired * factor, rtol=1e-9, atol=1e-7
        )
        evidence = {
            "evidenceKind": "real_market_cross_asset_replay",
            "bundleHash": chosen["bundleHash"],
            "targetUniverseVersion": plan["universeVersion"],
            "scopeDataVersion": plan["publicationId"],
            "supportedAssetTypes": plan["assetTypes"],
            "coverageSymbols": symbols,
            "heldOutSymbols": held_out,
            "ledgerPassed": True,
            "permutationPassed": True,
            "mixedAssetTypesPassed": True,
            "costAdaptationPassed": True,
            "cashReservePassed": True,
            "selectionSha256": hashlib.sha256(selection_bytes).hexdigest(),
            "replays": replays,
            "configurationReplay": {
                "cashPct": 25,
                "commissionPct": 0.07,
                "slippagePct": 0.04,
                "metrics": extra["metrics"],
            },
            "limitations": plan["limitations"],
        }
        evidence_sha = write_json(path / "cross-asset-evaluation.json", evidence)
        write_json(
            path / "cross-asset-replays.json", {**results, "custom-cost-cash": extra}
        )
        reference = [
            results["reference-" + k]["metrics"] for k in plan["validationGroups"]
        ]
        mean = lambda rows: {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}
        baselines = {}
        for base in ("equal_weight_hold", "ma_cross"):
            rows = [
                evaluate_portfolio(
                    bundle,
                    {s: frames[s] for s in members},
                    start=start,
                    end=end,
                    baseline=base,
                    asset_types=plan["assetTypes"],
                    nontrading_sessions=nontrading,
                )["metrics"]
                for members in plan["validationGroups"].values()
            ]
            baselines[base] = mean(rows)
        evaluation = {
            "runId": chosen["runId"],
            "bundleHash": chosen["bundleHash"],
            "validation": mean(list(chosen["validation"].values())),
            "test": mean(reference),
            "baselines": baselines,
            "aggregation": "mean_of_three_independent_10_asset_reference_portfolios",
            "selection": plan["selection"],
            "limitations": plan["limitations"],
            "testStartDate": start,
            "testEndDate": end,
            "simultaneousAssets": 10,
            "ledgerPassed": True,
        }
        evaluation_sha = write_json(path / "evaluation.json", evaluation)
        release["models"].append(
            {
                "modelRef": chosen["runId"],
                "bundleHash": chosen["bundleHash"],
                "evaluationSha256": evaluation_sha,
                "targetUniverseVersion": plan["universeVersion"],
                "assetScope": "published_universe",
                "supportedAssetTypes": plan["assetTypes"],
                "scopeDataVersion": plan["publicationId"],
                "costPolicy": "request_configurable",
                "crossAssetEvidenceSha256": evidence_sha,
            }
        )
        reports[algo] = {
            "coverage": len(symbols),
            "groups": len(replays),
            "heldOut": len(held_out),
            "evaluation": evaluation,
        }
        write_json(experiment / "evaluation-report.json", reports)
        print(
            json.dumps(
                {
                    "algorithm": algo,
                    "coverage": len(symbols),
                    "groups": len(replays),
                    "test": evaluation["test"],
                }
            ),
            flush=True,
        )
    # Local release candidate only. No network or production writes are performed.
    write_json(experiment / "models" / "release.json", release)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--experiment", type=Path, required=True)
    p.add_argument("--publication", type=Path, required=True)
    a = p.parse_args()
    evaluate(a.experiment, a.publication)


if __name__ == "__main__":
    main()
