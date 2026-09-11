"""Read-only raw Tencent unit evidence for a fixed completed trading day."""
import json
import time

import requests
from akshare.utils import demjson


def main():
    session = requests.Session()
    session.trust_env = False
    for symbol in ("sz000001", "sh600000", "sh510300", "sh000300", "sz399300"):
        time.sleep(2)
        try:
            response = session.get(
                "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
                params={"param": f"{symbol},day,2026-09-01,2026-09-07,10,qfq"},
                timeout=(5, 8), allow_redirects=False)
            response.raise_for_status()
            data = demjson.decode(response.text)["data"][symbol]
            bars = data.get("day") or data.get("qfqday") or data.get("hfqday")
            print(json.dumps({"symbol": symbol, "raw_last_bar": bars[-1],
                              "rows": len(bars)}, ensure_ascii=False), flush=True)
        except (requests.RequestException, ValueError, KeyError, TypeError, IndexError) as exc:
            print(json.dumps({"symbol": symbol, "error": type(exc).__name__}), flush=True)


if __name__ == "__main__":
    main()
