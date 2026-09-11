"""Validate isolated source candidates and publish only into a local artifacts directory."""

import argparse
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from quant_platform.data.coverage import digest
from quant_platform.data.index_snapshot import load_index
from quant_platform.data.publication import checked_document, publish
from quant_platform.data.universe import load_snapshot

from tools.prepare_history_batch import load_observation, validate_observation


def build(stock_dir, etf_dir, universe_dir, index_dir):
    stock = checked_document(stock_dir / "manifest.json")
    etf = checked_document(etf_dir / "manifest.json")
    for value in (stock, etf):
        if value["candidateId"] != digest(
            {k: v for k, v in value.items() if k != "candidateId"}
        ):
            raise ValueError("candidate hash mismatch")
    universe = load_snapshot(universe_dir)
    if stock["universeVersion"] != universe.to_dict()["snapshotId"]:
        raise ValueError("stock universe mismatch")
    start, end = (
        date.fromisoformat(stock["startDate"]),
        date.fromisoformat(stock["endDate"]),
    )
    if (etf["startDate"], etf["endDate"]) != (stock["startDate"], stock["endDate"]):
        raise ValueError("candidate interval mismatch")
    index = load_index(index_dir)
    if (index.start, index.end) != (start, end):
        raise ValueError("index interval mismatch")
    histories = {}
    for directory, entries, is_stock in [
        (stock_dir, stock["entries"], True),
        (etf_dir, etf["entries"], False),
    ]:
        for entry in entries:
            symbol = entry["symbol"] if is_stock else entry["asset"]["symbol"]
            if (
                not symbol.isascii()
                or not symbol.isdigit()
                or len(symbol) != 6
                or symbol in histories
            ):
                raise ValueError("invalid or duplicate candidate identity")
            path = directory / "observations" / (symbol + ".json")
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError("source path escapes candidate")
            wrapper = load_observation(path)
            if wrapper["sha256"] != entry["observationSha256"]:
                raise ValueError("candidate observation differs")
            if is_stock and wrapper["universeVersion"] != stock["universeVersion"]:
                raise ValueError("observation universe mismatch")
            value = wrapper["observation"]
            validate_observation(value, symbol, start, end)
            if value["error"]:
                raise ValueError("source error cannot be published")
            histories[symbol] = value["records"]
    document = {
        "schemaVersion": 1,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "createdAt": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "universe": universe.to_dict(),
        "tradingEvents": stock["tradingEvents"],
        "indexRaw": (index_dir / "response.txt").read_text(),
        "sourceCandidates": [stock["candidateId"], etf["candidateId"]],
        "histories": histories,
    }
    return {**document, "publicationId": digest(document)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("stocks", "etfs", "universe", "index", "output"):
        parser.add_argument("--" + arg, required=True, type=Path)
    args = parser.parse_args()
    root = Path("artifacts").resolve()
    if args.output.resolve() == root or not args.output.resolve().is_relative_to(root):
        parser.error("local publication output must be an artifacts child")
    provider = publish(
        args.output, build(args.stocks, args.etfs, args.universe, args.index)
    )
    print(provider.publication_context)


if __name__ == "__main__":
    main()
