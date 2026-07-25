from __future__ import annotations

import os
from uuid import uuid4

from flask import Flask, Response, g, request

from app.api.routes import api

__version__ = "0.1.0"


def create_app(test_config: dict[str, object] | None = None) -> Flask:
    """Create and configure the Flask application."""
    application = Flask(__name__)
    application.config.from_mapping(
        APP_VERSION=__version__,
        ALLOWED_ORIGINS=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173"),
    )
    if test_config:
        application.config.update(test_config)

    allowed_origins = {
        origin.strip()
        for origin in str(application.config["ALLOWED_ORIGINS"]).split(",")
        if origin.strip()
    }

    @application.before_request
    def attach_trace_id() -> None:
        g.trace_id = f"req_{uuid4().hex[:16]}"

    @application.after_request
    def add_cors_headers(response: Response) -> Response:
        request_origin = request.headers.get("Origin", "")
        if request_origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = request_origin
            response.headers["Vary"] = "Origin"
        return response

    application.register_blueprint(api, url_prefix="/api")
    return application
