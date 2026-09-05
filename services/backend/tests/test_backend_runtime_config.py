from app import create_app


def test_cors_preflight_for_allowed_origin() -> None:
    application = create_app(
        {
            "TESTING": True,
            "ALLOWED_ORIGINS": "https://example.github.io",
        }
    )

    response = application.test_client().options(
        "/api/allocation/suggestion",
        headers={
            "Origin": "https://example.github.io",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "https://example.github.io"
    assert "Content-Type" in response.headers["Access-Control-Allow-Headers"]
    assert "POST" in response.headers["Access-Control-Allow-Methods"]
    assert response.headers["Access-Control-Max-Age"] == "600"


def test_cors_headers_are_omitted_for_unknown_origin() -> None:
    application = create_app(
        {
            "TESTING": True,
            "ALLOWED_ORIGINS": "https://example.github.io",
        }
    )

    response = application.test_client().get(
        "/api/health", headers={"Origin": "https://untrusted.example"}
    )

    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers
