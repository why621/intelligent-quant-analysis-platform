from __future__ import annotations

import os

from app import create_app

app = create_app()


def main() -> None:
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )


if __name__ == "__main__":
    main()
