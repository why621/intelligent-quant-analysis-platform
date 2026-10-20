"""Loopback-only real model demo with an explicitly historical allocation clock."""

import argparse
import json
import os
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from app import create_app
from flask import send_from_directory
from quant_platform.data.publication import load_publication
from werkzeug.serving import make_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication", type=Path, required=True)
    parser.add_argument("--rl-release", type=Path, required=True)
    parser.add_argument("--portfolio-release", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    # Windows SQLite WAL cannot safely use a WSL UNC share; keep this test DB on
    # the native temporary filesystem. It never points to a production job store.
    database = Path(tempfile.mkdtemp(prefix="cr071-browser-")) / "jobs.db"
    os.environ["BACKTEST_DB_PATH"] = str(database)
    (args.output / "database-location.json").write_text(
        json.dumps({"temporaryLocalDatabase": str(database)}), encoding="utf-8"
    )
    provider = load_publication(args.publication)
    app = create_app({
        "QUANT_RL_RELEASE": str(args.rl_release.resolve()),
        "QUANT_PORTFOLIO_RELEASE": str(args.portfolio_release.resolve()),
    }, market_data_provider=provider)
    dist = Path("apps/frontend/dist").resolve()

    @app.get("/")
    def index():
        return send_from_directory(dist, "index.html")

    @app.get("/<path:name>")
    def static_file(name):
        return send_from_directory(dist, name)

    with patch("quant_platform.allocation._today",
               return_value=provider.end + timedelta(days=1)):
        server = make_server("127.0.0.1", 18771, app, threaded=True)
        server.timeout = 1
        print("Local historical model server ready: http://127.0.0.1:18771", flush=True)
        try:
            while not (args.output / "stop").exists():
                server.handle_request()
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
