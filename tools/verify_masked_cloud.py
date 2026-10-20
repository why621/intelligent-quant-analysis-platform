"""CR070 cloud candidate gate. Run in a network-disabled container with read-only inputs.

Uses actual published prices, deployed candidate weights and the real business
clock. All HTTP requests are Flask test-client calls; job stores are temporary.
No production database, publication pointer, model file or network is mutated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(a, b, label, atol=1e-6):
    if not math.isclose(float(a), float(b), rel_tol=1e-10, abs_tol=atol):
        raise AssertionError((label, a, b))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication", type=Path, required=True)
    parser.add_argument("--rl-release", type=Path, required=True)
    parser.add_argument("--portfolio-release", type=Path, required=True)
    parser.add_argument(
        "--verify-script",
        type=Path,
        default=Path("/app/tools/verify_published_provider.py"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-date", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # This intentionally precedes importing the application factory.
    temp = tempfile.TemporaryDirectory(prefix="cr069-cloud-")
    temp_root = Path(temp.name)
    os.environ["BACKTEST_DB_PATH"] = str(temp_root / "not-production.db")
    from app import create_app
    from quant_platform.data.calendar import latest_session, sessions
    from quant_platform.data.publication import load_publication
    from quant_platform.rl.errors import RLInsufficientHistory
    from quant_platform.rl.portfolio_policy import prepare_portfolio_policy
    from quant_platform.rl.portfolio_strategy import JointPortfolioStrategy

    pointer = args.publication / "current.json"
    version = json.loads(pointer.read_bytes())["publicationId"]
    publication_file = args.publication / "releases" / (version + ".json")
    readonly_files = {
        pointer,
        publication_file,
        args.rl_release,
        args.portfolio_release,
    }
    for release in (args.rl_release, args.portfolio_release):
        for entry in json.loads(release.read_text())["models"]:
            readonly_files.update(
                p
                for p in (release.parent / entry["modelRef"]).rglob("*")
                if p.is_file()
            )
    before_hashes = {str(p): digest(p) for p in sorted(readonly_files)}
    provider = load_publication(args.publication)
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    assert provider.end == args.expected_date, (provider.end, args.expected_date)
    assert latest_session(now.date() - timedelta(days=1)) == provider.end, (
        "actual cloud business clock requires another publication",
        now.isoformat(),
        provider.end,
    )
    availability = provider.availability
    incomplete = [
        s for s, state in availability["assets"].items() if state["state"] != "ready"
    ]
    assert availability["complete"] == (not incomplete), availability
    app = create_app(
        {
            "TESTING": True,
            "QUANT_RL_RELEASE": str(args.rl_release),
            "QUANT_PORTFOLIO_RELEASE": str(args.portfolio_release),
        },
        market_data_provider=provider,
    )
    service = app.extensions["backtest_service"]
    job_db = Path(service._store._db_path).resolve()
    assert job_db.is_relative_to(Path(tempfile.gettempdir()).resolve()), job_db
    assert not job_db.is_relative_to(args.publication.resolve()), job_db
    client = app.test_client()
    headers = {"X-Research-Version": provider.publication_context["dataVersion"]}
    responses, failures, jobs, allocation_results, complete_jobs = [], [], [], {}, {}
    expected_failed_jobs = set()

    def call(method, path, payload=None, expected=200):
        response = client.open(path, method=method, json=payload, headers=headers)
        body = response.get_json()
        assert response.status_code == expected, (
            method,
            path,
            response.status_code,
            body,
        )
        if body and "dataContext" in body:
            assert body["dataContext"] == provider.publication_context
        responses.append(
            {"method": method, "path": path, "status": response.status_code}
        )
        return body

    def reject(name, payload, path="/api/backtests", allowed=(400, 404, 422)):
        response = client.post(path, json=payload, headers=headers)
        assert response.status_code in allowed, (
            name,
            response.status_code,
            response.json,
        )
        assert response.json["error"]["code"] not in {
            "INTERNAL_ERROR",
            "UPSTREAM_UNAVAILABLE",
        }
        failures.append(
            {
                "name": name,
                "status": response.status_code,
                "error": response.json["error"],
            }
        )

    def job_count():
        with sqlite3.connect(job_db) as connection:
            return connection.execute("SELECT count(*) FROM backtest_jobs").fetchone()[
                0
            ]

    def validate_ledger(result, payload):
        records, trades = result["accountCurve"], result["trades"]
        assert len(records) == len(result["equityCurve"]) >= 2
        assert records[0]["date"] == result["equityCurve"][0]["date"]
        assert all(p["benchmarkEquity"] is not None for p in result["equityCurve"])
        summary = result["costSummary"]
        assert summary["tradeCount"] == len(trades)
        close(sum(t["feeCny"] for t in trades), summary["feesCny"], "fee summary")
        close(
            sum(t["slippageCny"] for t in trades),
            summary["slippageCny"],
            "slippage summary",
        )
        close(
            summary["feesCny"] + summary["slippageCny"],
            summary["totalTradingCostCny"],
            "total cost",
        )
        cash, quantity = (
            float(payload["initialCapitalCny"]),
            dict.fromkeys(payload["symbols"], 0.0),
        )
        fills = {}
        for trade in trades:
            fills.setdefault(trade["date"], []).append(trade)
        for record in records:
            for trade in fills.get(record["date"], []):
                symbol, day = trade["symbol"], date.fromisoformat(trade["date"])
                assert day not in provider.nontrading_sessions(symbol, day, day)
                sign = 1 if trade["side"] == "buy" else -1
                quantity[symbol] += sign * trade["quantity"]
                cash -= sign * trade["amountCny"] + trade["feeCny"]
            close(cash, record["cashCny"], "independent cash ledger")
            close(
                record["cashCny"]
                + sum(p["marketValueCny"] for p in record["positions"]),
                record["equity"],
                "account equity",
            )
            assert record["cashCny"] >= -1e-6
            for position in record["positions"]:
                close(
                    position["quantity"],
                    quantity[position["symbol"]],
                    "independent quantity",
                )
            close(
                sum(p["weightPct"] for p in record["positions"])
                + record["cashCny"] / record["equity"] * 100,
                100,
                "weights",
            )
        assert all(
            value is None or math.isfinite(value)
            for value in result["metrics"].values()
        )

    def run(name, payload):
        job = call("POST", "/api/backtests", payload, 202)
        service.execute_job(job["jobId"])
        job = call("GET", "/api/backtests/" + job["jobId"])
        assert job["status"] == "succeeded", (name, job)
        assert job["request"] == payload, (
            name,
            "request snapshot altered",
            job["request"],
        )
        validate_ledger(job["result"], payload)
        jobs.append(
            {
                "name": name,
                "jobId": job["jobId"],
                "status": job["status"],
                "assets": len(payload["symbols"]),
                "points": len(job["result"]["accountCurve"]),
                "tradeCount": len(job["result"]["trades"]),
                "metrics": job["result"]["metrics"],
            }
        )
        complete_jobs[name] = job
        emit({"case": name, "passed": True, "trades": len(job["result"]["trades"])})
        return job["result"]

    status = call("GET", "/api/data/status")
    assert status["latestTradeDate"] == provider.end.isoformat()
    overview = call("GET", "/api/market/overview")
    coverage = call("GET", "/api/data/coverage")
    assert len(coverage["items"]) == 327
    items = call("GET", "/api/strategies")["items"]
    catalog = {item["id"]: item for item in items}
    expected_ids = {
        "ma_cross",
        "momentum_reversal",
        "ppo",
        "dqn",
        "sac",
        "td3",
        "portfolio_ppo",
        "portfolio_sac",
        "portfolio_td3",
        "portfolio_masked_sac",
    }
    assert set(catalog) == expected_ids, set(catalog)
    kinds = {a.symbol: a.asset_type for a in provider.list_assets(limit=None)}
    assert len(kinds) == 327 and set(kinds.values()) == {"stock", "etf"}
    strategy_registry = app.extensions["strategy_catalog_service"].registry()
    joint_ids = (
        "portfolio_ppo",
        "portfolio_sac",
        "portfolio_td3",
        "portfolio_masked_sac",
    )
    held_out = strategy_registry["portfolio_ppo"].cross_asset_evidence["heldOutSymbols"]
    stocks = sorted(s for s in kinds if kinds[s] == "stock" and s not in incomplete)
    etfs = sorted(s for s in kinds if kinds[s] == "etf" and s not in incomplete)
    held_stock = next(s for s in held_out if kinds[s] == "stock")
    held_etf = next(s for s in held_out if kinds[s] == "etf")
    selected_stocks = list(
        dict.fromkeys(
            [s for s in ["001280", held_stock, *stocks] if s not in incomplete]
        )
    )[:5]
    selected_etfs = list(dict.fromkeys([held_etf, "510300", "510500", *etfs]))[:5]
    two, ten = [held_stock, held_etf], selected_stocks + selected_etfs
    assert len(set(ten)) == 10 and set(two).isdisjoint(
        catalog["portfolio_ppo"]["modelContext"]["trainingSymbols"]
    )
    start = max(
        date.fromisoformat(catalog[s]["modelContext"]["outOfSampleStartDate"])
        for s in joint_ids
    )
    long_start = max(provider.start, provider.end - timedelta(days=365))
    costs = {
        "commissionPct": 0.07,
        "stampDutyPct": 0.05,
        "slippagePct": 0.04,
        "stampDutyMode": "asset_date",
    }
    common = {
        "symbols": ten,
        "strategyId": "ma_cross",
        "parameters": {"shortWindow": 8, "longWindow": 30},
        "startDate": start.isoformat(),
        "endDate": provider.end.isoformat(),
        "initialCapitalCny": 120000,
        "cashPct": 25,
        "adjust": "qfq",
        "portfolioMode": "shared_account",
        "benchmarkMode": "buy_and_hold",
        "tradingCosts": costs,
    }
    call(
        "POST",
        "/api/analytics/correlation",
        {
            "symbols": ten,
            "startDate": common["startDate"],
            "endDate": common["endDate"],
        },
    )
    for sid in ("ma_cross", "momentum_reversal"):
        parameters = {
            k: v["default"]
            for k, v in catalog[sid]["parameterSchema"]["properties"].items()
        }
        run(sid, {**common, "strategyId": sid, "parameters": parameters})

    old_hashes, new_hashes = {}, {}
    for sid in ("ppo", "dqn", "sac", "td3"):
        context = catalog[sid]["modelContext"]
        assert context["assetScope"] == "training_symbols" and context["symbols"] == [
            "510300"
        ]
        old_hashes[sid] = context["bundleHash"]
        payload = {
            **common,
            "strategyId": sid,
            "symbols": ["510300"],
            "cashPct": 0,
            "parameters": {"modelRef": context["modelRef"]},
            "portfolioMode": "legacy_independent",
            "startDate": long_start.isoformat(),
            "tradingCosts": context["requiredTradingCosts"],
        }
        run("legacy_" + sid, payload)
        reject(sid + "_cross_asset_forbidden", {**payload, "symbols": ["510500"]})
        reject(
            sid + "_shared_forbidden", {**payload, "portfolioMode": "shared_account"}
        )

    for sid in joint_ids:
        context = catalog[sid]["modelContext"]
        assert context["assetScope"] == "published_universe"
        assert context["supportedAssetTypes"] == kinds
        assert (
            set(context["symbols"]) == set(kinds)
            and len(context["trainingSymbols"]) < 327
        )
        assert (
            context["costPolicy"] == "request_configurable"
            and "requiredTradingCosts" not in context
        )
        assert context["performanceStatus"] == "unproven"
        assert context["crossAssetValidationStatus"] == "execution_validated"
        new_hashes[sid] = context["bundleHash"]
        for symbols in (two, ten):
            payload = {
                **common,
                "symbols": symbols,
                "strategyId": sid,
                "parameters": {"modelRef": context["modelRef"]},
            }
            name = sid + "_" + str(len(symbols))
            result = run(name, payload)
            assert result["assumptions"]["costsDifferFromTraining"] == "true"
            assert result["assumptions"]["portfolioMode"] == "shared_account"
            for trade in result["trades"]:
                close(
                    trade["commissionCny"],
                    trade["amountCny"] * 0.0007,
                    "requested commission",
                )
                expected_tax = (
                    trade["amountCny"] * 0.0005
                    if kinds[trade["symbol"]] == "stock" and trade["side"] == "sell"
                    else 0
                )
                close(trade["stampDutyCny"], expected_tax, "stock/ETF actual tax type")
            allocation_payload = {
                k: v
                for k, v in payload.items()
                if k not in {"endDate", "portfolioMode", "benchmarkMode"}
            }
            response = call("POST", "/api/allocation/suggestion", allocation_payload)
            assert response["request"] == allocation_payload
            assert response["basisDate"] == provider.end.isoformat()
            assert len(response["positions"]) == len(symbols)
            close(
                response["cashPct"]
                + sum(p["weightPct"] for p in response["positions"]),
                100,
                "allocation total",
            )
            assert response["cashPct"] >= 25 - 1e-7
            allocation_results[name] = response
            if len(symbols) == 10:
                reverse = run(
                    name + "_reverse", {**payload, "symbols": list(reversed(symbols))}
                )
                assert reverse["accountCurve"] == result["accountCurve"]
                assert reverse["trades"] == result["trades"]
                assert reverse["costSummary"] == result["costSummary"]
                for metric in (
                    "totalReturnPct",
                    "annualizedReturnPct",
                    "maxDrawdownPct",
                    "sharpe",
                ):
                    assert reverse["metrics"][metric] == result["metrics"][metric]
        reject(sid + "_one_asset", {**payload, "symbols": ["510300"]})
        reject(
            sid + "_training_overlap", {**payload, "startDate": context["valEndDate"]}
        )
        reject(
            sid + "_model_identity",
            {**payload, "parameters": {"modelRef": "unreviewed"}},
        )
        for missing in incomplete:
            rejected = call(
                "POST",
                "/api/backtests",
                {**payload, "symbols": [missing, "510300"]},
                202,
            )
            service.execute_job(rejected["jobId"])
            rejected = call("GET", "/api/backtests/" + rejected["jobId"])
            assert rejected["status"] == "failed" and rejected["result"] is None, (
                rejected
            )
            assert rejected["error"]["error"]["code"] == "UPSTREAM_UNAVAILABLE", (
                rejected
            )
            expected_failed_jobs.add(rejected["jobId"])
            failures.append(
                {
                    "name": sid + "_declared_incomplete_" + missing,
                    "kind": "async_unknown_gap_rejected",
                    "jobId": rejected["jobId"],
                    "error": rejected["error"],
                }
            )

    ranking_payload = {
        **common,
        "strategyId": "portfolio_ppo",
        "parameters": {
            "modelRef": catalog["portfolio_ppo"]["modelContext"]["modelRef"]
        },
    }
    before_count = job_count()
    ranking = call("POST", "/api/strategies/ranking", ranking_payload)
    assert job_count() == before_count, "read-only ranking created a task"
    assert ranking["request"] == ranking_payload
    assert ranking["evaluationSymbols"] == ten
    assert ranking["tradingCosts"] == costs
    assert (
        ranking["evaluationStartDate"] == sessions(start, provider.end)[0].isoformat()
    )
    assert ranking["evaluationEndDate"] == provider.end.isoformat()
    assert ranking["observationCount"] == len(sessions(start, provider.end))
    assert {row["strategyId"] for row in ranking["items"]} == {
        "ma_cross",
        "momentum_reversal",
        *joint_ids,
    }
    assert {row["strategyId"] for row in ranking["unavailableStrategies"]} == {
        "ppo",
        "dqn",
        "sac",
        "td3",
    }
    for row in ranking["items"]:
        candidate = {
            **ranking_payload,
            "strategyId": row["strategyId"],
            "parameters": row["parameters"],
        }
        reference = run("ranking_reference_" + row["strategyId"], candidate)
        assert reference["metrics"] == row["metrics"], (
            row["strategyId"],
            "ranking metrics mismatch",
        )
        assert reference["costSummary"] == row["costSummary"], (
            row["strategyId"],
            "ranking costs mismatch",
        )
        assert reference["benchmarkContext"] == row["benchmarkContext"]
    repeat_count = job_count()
    assert call("POST", "/api/strategies/ranking", ranking_payload) == ranking
    assert job_count() == repeat_count
    changed_payload = {
        **ranking_payload,
        "cashPct": 30,
        "tradingCosts": {**costs, "commissionPct": 0.08},
        "symbols": two,
    }
    changed = call("POST", "/api/strategies/ranking", changed_payload)
    assert changed["configHash"] != ranking["configHash"]
    assert changed["request"] == changed_payload and changed["evaluationSymbols"] == two
    assert job_count() == repeat_count
    legacy_ranking = call("GET", "/api/strategies/ranking?period=30d")
    assert (
        len(legacy_ranking["items"]) == 6
        and not legacy_ranking["unavailableStrategies"]
    )
    assert legacy_ranking["evaluationSymbols"] == ["510300"]

    for name, patch in (
        ("duplicates", {"symbols": [two[0], two[0]]}),
        ("over_ten", {"symbols": list(kinds)[:11]}),
        ("outside_catalog", {"symbols": [two[0], "999999"]}),
        ("negative_cash", {"cashPct": -1}),
        ("wrong_adjust", {"adjust": "none"}),
    ):
        reject(name, {**ranking_payload, **patch})
    reject(
        "ranking_wrong_model",
        {**ranking_payload, "parameters": {"modelRef": "unknown"}},
        path="/api/strategies/ranking",
    )
    short_frames = {
        s: provider.history(s, provider.start, provider.end).iloc[-60:].copy()
        for s in two
    }
    current_strategy = strategy_registry["portfolio_ppo"]
    try:
        prepare_portfolio_policy(
            current_strategy.bundle,
            short_frames,
            evaluation_start=start,
            serving_scope=current_strategy.serving_scope,
            nontrading_sessions={
                s: provider.nontrading_sessions(s, provider.start, provider.end)
                for s in two
            },
            evaluation_end=provider.end,
        )
    except RLInsufficientHistory as error:
        assert getattr(error, "symbol", None) in two
        failures.append(
            {
                "name": "real_prices_truncated_warmup",
                "code": error.code,
                "symbol": error.symbol,
                "kind": "isolated_algorithm_guard",
            }
        )
    else:
        raise AssertionError("short actual history was silently accepted")
    try:
        JointPortfolioStrategy(
            current_strategy.path,
            {**current_strategy.release, "crossAssetEvidenceSha256": "0" * 64},
        )
    except ValueError:
        failures.append(
            {
                "name": "mismatched_cross_asset_evidence",
                "kind": "isolated_release_guard",
            }
        )
    else:
        raise AssertionError("scope without matching evidence was loaded")

    suspension = None
    for event in provider.trading_events:
        if event.reason == "suspension" and event.asset_id.split(":")[-1] in kinds:
            day = max(event.start, start)
            verified_end = min(event.end, provider.end)
            if day <= verified_end and len(sessions(day, verified_end)) >= 2:
                suspension = event, day, verified_end
    assert suspension is not None, (
        "expected a verified suspension in the frozen publication"
    )
    event, suspended_day, verified_end = suspension
    suspended_symbol = event.asset_id.split(":")[-1]
    suspended_payload = {
        **ranking_payload,
        "symbols": [suspended_symbol, "510300"],
        "startDate": suspended_day.isoformat(),
        "endDate": verified_end.isoformat(),
    }
    suspended = run("verified_suspension_first_day_benchmark", suspended_payload)
    assert suspended["equityCurve"][0]["benchmarkEquity"] == 1
    assert not any(
        t["symbol"] == suspended_symbol
        and event.start <= date.fromisoformat(t["date"]) <= event.end
        for t in suspended["trades"]
    )

    # CR067 regression: data publication verification must ignore inherited serving
    # model configuration and must not import optional serving/training packages.
    assert args.verify_script.is_file(), args.verify_script
    daily_code = r"""
import importlib.abc, importlib.util, json, sys
from pathlib import Path
class RejectServingML(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch', 'stable_baselines3', 'gymnasium'}:
            raise ImportError('daily gate must not import serving ML dependencies')
sys.meta_path.insert(0, RejectServingML())
from quant_platform.data.publication import load_publication
spec = importlib.util.spec_from_file_location('cr069_daily_gate', sys.argv[1])
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
provider = load_publication(Path(sys.argv[2]))
app = module.publication_app(provider)
ids = [s['id'] for s in app.test_client().get('/api/strategies').json['items']]
assert set(ids) == {'ma_cross', 'momentum_reversal'}
result = module.verify(provider)
assert result['dataContext'] == provider.publication_context
print(json.dumps({'passed':True, 'servingModelsDisabled':True, 'mlImportsBlocked':True,
                  'strategies':ids, 'dataContext':result['dataContext'],
                  'verification':result}))
"""
    env = {
        **os.environ,
        "QUANT_RL_RELEASE": "/not-present/single-release.json",
        "QUANT_PORTFOLIO_RELEASE": "/not-present/joint-release.json",
        "BACKTEST_DB_PATH": str(temp_root / "daily-isolated.db"),
    }
    daily = subprocess.run(
        [
            sys.executable,
            "-c",
            daily_code,
            str(args.verify_script),
            str(args.publication),
        ],
        env=env,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert daily.returncode == 0, (
        "daily dependency isolation failed",
        daily.stdout,
        daily.stderr,
    )
    daily_result = json.loads(daily.stdout.strip().splitlines()[-1])
    assert {str(p): digest(p) for p in sorted(readonly_files)} == before_hashes
    with sqlite3.connect(job_db) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        actual_failures = {
            row[0]
            for row in connection.execute(
                "SELECT job_id FROM backtest_jobs WHERE status='failed'"
            )
        }
        assert actual_failures == expected_failed_jobs
        assert (
            connection.execute(
                "SELECT count(*) FROM backtest_jobs WHERE status NOT IN ('succeeded','failed')"
            ).fetchone()[0]
            == 0
        )
    result = {
        "passed": True,
        "clock": "actual_cloud_business_date_not_patched",
        "observedAt": now.isoformat(),
        "context": provider.publication_context,
        "network": "disabled_by_container_required",
        "catalogCount": len(catalog),
        "catalog": sorted(catalog),
        "applicableAssets": len(kinds),
        "dataAvailability": {
            "complete": availability["complete"],
            "incompleteSymbols": incomplete,
        },
        "stockEtfPair": two,
        "mixedTen": ten,
        "oldModelHashes": old_hashes,
        "newModelHashes": new_hashes,
        "temporaryJobDatabase": str(job_db),
        "jobs": jobs,
        "negativeCases": failures,
        "ranking": ranking,
        "changedRanking": changed,
        "legacyRanking": legacy_ranking,
        "allocations": allocation_results,
        "cr067DailyIsolation": daily_result,
        "sourceAndModelHashesUnchanged": True,
        "sourceAndModelHashes": before_hashes,
        "requests": responses,
        "overviewDate": overview["tradeDate"],
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    args.output.with_name("backtests.json").write_text(
        json.dumps(complete_jobs, ensure_ascii=False) + "\n"
    )
    emit(
        {
            "passed": True,
            "jobCount": len(jobs),
            "strategies": len(catalog),
            "newModelCases": 8,
            "allocationCases": len(allocation_results),
            "rankingRows": len(ranking["items"]),
            "rejections": len(failures),
            "dailyIsolation": daily_result["passed"],
        }
    )
    temp.cleanup()


if __name__ == "__main__":
    main()
