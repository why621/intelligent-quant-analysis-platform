import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[3] / "tools" / "validate_pages_api.py"
_SPEC = importlib.util.spec_from_file_location("pages_validation", _PATH)
validator = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(validator)


@pytest.mark.parametrize("url", ["", "/api", "http://43.161.219.65/api",
    "https://why621.github.io/api", "https://api.example.com", "https://localhost/api",
    "https://user:secret@api.example.com/api", "https://api.example.com/api?key=x",
    "https://api.example.com:bad/api"])
def test_pages_rejects_unusable_or_secret_bearing_url(url):
    with pytest.raises(ValueError):
        validator.validate(url)


def test_pages_accepts_https_backend_api_base():
    validator.validate("https://api.example.com/api")
    validator.validate("https://api.example.com/api/")
