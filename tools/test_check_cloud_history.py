"""Offline safety tests; never invoke SSH or source HTTP."""
import base64
import json
import re
from unittest.mock import patch

import pytest

from tools.check_cloud_history import prepare


@pytest.fixture
def root(tmp_path):
    (tmp_path / "artifacts").mkdir()
    modules = tmp_path / "services/algorithms/src/quant_platform/data"
    modules.mkdir(parents=True)
    for name in ("coverage", "history_probe"):
        (modules / f"{name}.py").write_text("raise AssertionError('must not execute locally')")
    return tmp_path


def test_prepare_compiles_but_never_executes_or_connects(root):
    target = root / "artifacts/new"
    with patch("subprocess.run", side_effect=AssertionError) as run:
        output, program = prepare(root, target)
    run.assert_not_called()
    assert output == target and not target.exists()
    encoded = re.search(r"base64.b64decode\('([^']+)'\)", program)[1]
    assert set(json.loads(base64.b64decode(encoded))) == {"coverage", "history_probe"}
    assert "signal.alarm(40)" in program and "maxRequests=30" in program
    assert "AkShareMarketDataProvider(" not in program


def test_reject_existing_nested_and_escape_outputs(root):
    for target in [root, root / "artifacts", root / "outside", root / "artifacts/a/b"]:
        with pytest.raises(ValueError):
            prepare(root, target)


def test_reject_symlink_escape(root, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (root / "artifacts/link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        prepare(root, root / "artifacts/link/new")
