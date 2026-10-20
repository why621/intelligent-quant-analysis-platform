"""Real local HTTP replay of frozen data and candidate models; never a cloud check."""

import argparse
import hashlib
import json
import os
import shutil
import socket
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication", type=Path, required=True)
    parser.add_argument("--rl-release", type=Path, required=True)
    parser.add_argument("--model-roots", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    models = args.output / "models"
    models.mkdir()
    release = {"schemaVersion": 1, "models": []}
    source_hashes = {}
    for root in args.model_roots:
        original = json.loads((root / "release.json").read_bytes())
        for entry in original["models"]:
            folder = root / entry["modelRef"]
            for file in folder.rglob("*"):
                if file.is_file():
                    source_hashes[str(file.resolve())] = hashlib.sha256(file.read_bytes()).hexdigest()
            shutil.copytree(folder, models / entry["modelRef"])
            release["models"].append(entry)
    (models / "release.json").write_text(json.dumps(release), encoding="utf-8")

    def no_network(*_args, **_kwargs):
        raise AssertionError("offline acceptance must not connect to a network")

    with tempfile.TemporaryDirectory(prefix="cr071-local-") as temporary:
        os.environ["BACKTEST_DB_PATH"] = str(Path(temporary) / "jobs.db")
        with patch.object(socket.socket, "connect", no_network):
            from app import create_app
            from quant_platform.data.publication import load_publication

            provider = load_publication(args.publication)
            app = create_app({
                "TESTING": True, "QUANT_RL_RELEASE": str(args.rl_release.resolve()),
                "QUANT_PORTFOLIO_RELEASE": str((models / "release.json").resolve()),
            }, market_data_provider=provider)
            client = app.test_client()
            service = app.extensions["backtest_service"]
            headers = {"X-Research-Version": provider.publication_context["dataVersion"]}
            checks, jobs, allocations = [], {}, {}

            def call(method, path, payload=None, status=200):
                response = client.open(path, method=method, json=payload, headers=headers)
                assert response.status_code == status, (path, response.status_code, response.json)
                checks.append({"method": method, "path": path, "status": status})
                return response.json

            catalog = {s["id"]: s for s in call("GET", "/api/strategies")["items"]}
            old_joint = {"portfolio_ppo", "portfolio_sac", "portfolio_td3"}
            new_joint = {"portfolio_masked_ppo", "portfolio_masked_td3"}
            all_joint = old_joint | new_joint | {"portfolio_masked_sac"}
            assert set(catalog) == all_joint | {
                "ma_cross", "momentum_reversal", "ppo", "sac", "td3", "dqn"
            }
            registry = app.extensions["strategy_catalog_service"].registry()
            heldout = registry["portfolio_masked_ppo"].cross_asset_evidence["heldOutSymbols"]
            types = {a.symbol: a.asset_type for a in provider.list_assets(limit=None)}
            ten = ([s for s in heldout if types[s] == "stock"][:5]
                   + [s for s in heldout if types[s] == "etf"][:5])
            assert len(set(ten)) == 10
            start = catalog["portfolio_masked_ppo"]["modelContext"]["outOfSampleStartDate"]
            common = {
                "symbols": ten, "strategyId": "ma_cross",
                "parameters": {"shortWindow": 8, "longWindow": 30},
                "startDate": start, "endDate": provider.end.isoformat(),
                "initialCapitalCny": 120000, "cashPct": 25, "adjust": "qfq",
                "portfolioMode": "shared_account", "benchmarkMode": "buy_and_hold",
                "tradingCosts": {"commissionPct": .07, "stampDutyPct": .05,
                                 "slippagePct": .04, "stampDutyMode": "asset_date"},
            }

            def backtest(name, payload):
                submitted = call("POST", "/api/backtests", payload, 202)
                service.execute_job(submitted["jobId"])
                job = call("GET", "/api/backtests/" + submitted["jobId"])
                assert job["status"] == "succeeded", job
                result = job["result"]
                assert result["costSummary"]["tradeCount"] == len(result["trades"])
                for point in result["accountCurve"]:
                    assert point["cashCny"] >= -1e-6
                    assert abs(point["cashCny"] + sum(
                        p["marketValueCny"] for p in point["positions"]
                    ) - point["equity"]) < 1e-5
                jobs[name] = job
                (args.output / (name + "-job.json")).write_text(
                    json.dumps(job, ensure_ascii=False), encoding="utf-8"
                )
                return result

            # Historical allocation clock is explicit; never present this as today's availability.
            with patch("quant_platform.allocation._today",
                       return_value=provider.end + timedelta(days=1)):
                for sid in sorted(all_joint):
                    parameters = {"modelRef": catalog[sid]["modelContext"]["modelRef"]}
                    for count, members in [(2, [ten[0], ten[-1]]), (10, ten)]:
                        payload = {**common, "symbols": members, "strategyId": sid,
                                   "parameters": parameters}
                        result = backtest(f"{sid}-{count}", payload)
                        simulation = {k: v for k, v in payload.items()
                                      if k not in {"endDate", "portfolioMode", "benchmarkMode"}}
                        allocation = call("POST", "/api/allocation/suggestion", simulation)
                        assert allocation["request"] == simulation
                        assert abs(allocation["cashPct"] + sum(
                            p["weightPct"] for p in allocation["positions"]
                        ) - 100) < 1e-6
                        allocations[f"{sid}-{count}"] = allocation
                        if count == 10:
                            reversed_result = backtest(
                                sid + "-reverse", {**payload, "symbols": list(reversed(ten))}
                            )
                            for key in ["accountCurve", "trades", "metrics", "costSummary"]:
                                if reversed_result[key] != result[key]:
                                    (args.output / "permutation-difference.json").write_text(
                                        json.dumps({"strategyId": sid, "field": key,
                                                    "original": result[key],
                                                    "reversed": reversed_result[key]},
                                                   ensure_ascii=False, indent=2),
                                        encoding="utf-8",
                                    )
                                assert reversed_result[key] == result[key], (sid, key)
                    for change in [{"symbols": ["510300"]},
                                   {"parameters": {"modelRef": "unreviewed"}},
                                   {"startDate": "2026-07-01"}]:
                        response = client.post("/api/backtests", json={**payload, **change},
                                               headers=headers)
                        assert response.status_code in (400, 422), response.json
                ranking = call("POST", "/api/strategies/ranking", common)
                assert {r["strategyId"] for r in ranking["items"]} == all_joint | {
                    "ma_cross", "momentum_reversal"
                }
                for row in ranking["items"]:
                    sid = row["strategyId"]
                    result = (jobs[sid + "-10"]["result"] if sid in all_joint else backtest(
                        sid, {**common, "strategyId": sid, "parameters": row["parameters"]}
                    ))
                    assert row["metrics"] == result["metrics"]
                    assert row["costSummary"] == result["costSummary"]
                changes = [
                    {"cashPct": 10}, {"startDate": "2026-08-17"},
                    {"symbols": [ten[0], ten[-1]]},
                    {"tradingCosts": {**common["tradingCosts"], "commissionPct": .12}},
                ]
                hashes = {ranking["configHash"]}
                for change in changes:
                    revised = call("POST", "/api/strategies/ranking", {**common, **change})
                    assert revised["configHash"] not in hashes
                    hashes.add(revised["configHash"])
                    assert len(revised["items"]) == 8
            assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest
                       for p, digest in source_hashes.items())
            report = {
                "passed": True, "scope": "local_real_frozen_data_not_cloud_or_current_clock",
                "allocationClock": (provider.end + timedelta(days=1)).isoformat(),
                "dataContext": provider.publication_context, "catalog": sorted(catalog),
                "requests": checks, "jobs": jobs, "allocations": allocations,
                "ranking": ranking, "rankingConfigurationHashes": sorted(hashes),
                "sourceModelsUnchanged": True, "networkConnectionsAllowed": False,
            }
            (args.output / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(json.dumps({"passed": True, "catalog": len(catalog), "jobs": len(jobs),
                              "allocations": len(allocations), "rankingRows": 8,
                              "configurations": len(hashes)}), flush=True)


if __name__ == "__main__":
    main()
