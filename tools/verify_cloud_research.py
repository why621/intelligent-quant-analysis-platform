"""Explicit HTTP acceptance: creates one research backtest job, never real orders."""
import argparse
import json
import time
from datetime import date
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    end = str(args.end_date)

    def call(path, payload=None, expected=200):
        request = Request(base + "/api" + path,
                          data=json.dumps(payload).encode() if payload else None,
                          headers={"Content-Type": "application/json"} if payload else {})
        try:
            response = urlopen(request, timeout=15)
        except HTTPError as exc:
            response = exc
        with response:
            status = response.status
            body = json.load(response)
        assert status == expected, (path, status, body)
        print(json.dumps({"path": path.split("?")[0], "status": status}), flush=True)
        return body

    call("/health")
    status = call("/data/status")
    print(json.dumps({"dataStatus": status}, ensure_ascii=False), flush=True)
    history = call(f"/assets/000001/history?startDate=2026-09-01&endDate={end}")
    assert history["items"][-1]["date"] == end
    if end == "2026-09-07":
        assert history["items"][-1]["volume"] == 108727600
    symbols = ["000001", "600036"]
    call("/analytics/correlation", {"symbols": symbols, "startDate": "2026-06-01", "endDate": end})
    job = call("/backtests", {"symbols": symbols, "strategyId": "ma_cross",
                             "parameters": {"shortWindow": 5, "longWindow": 20},
                             "startDate": "2026-06-01", "endDate": end,
                             "benchmark": "510300"}, expected=202)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = call("/backtests/" + job["jobId"])
        if result["status"] in ("succeeded", "failed"):
            break
        time.sleep(2)
    assert result["status"] == "succeeded" and result["result"], result
    assert call("/strategies/ranking?period=30d")["items"]
    allocation = call("/allocation/suggestion", {
        "symbols": symbols, "strategyId": "ma_cross", "cashPct": 10})
    assert allocation["basisDate"] == end, allocation
    assert abs(sum(p["weightPct"] for p in allocation["positions"])
               + allocation["cashPct"] - 100) < 1e-8
    print(json.dumps({"research": "passed", "backtestJob": job["jobId"],
                      "basisDate": allocation["basisDate"], "benchmark": "510300 ETF",
                      "overview": status.get("components", {}).get("overview"),
                      "limits": "not full CSI300, not browser/HTTPS acceptance"},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
