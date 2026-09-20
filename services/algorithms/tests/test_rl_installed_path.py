from pathlib import Path

from quant_platform.rl.policies import _default_models_root


def test_short_container_install_layout_uses_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert (
        _default_models_root(Path("/app/code/quant_platform/rl/policies.py")) == tmp_path / "models"
    )


def test_source_checkout_retains_repository_models_directory():
    path = Path("/project/services/algorithms/src/quant_platform/rl/policies.py")
    assert _default_models_root(path) == Path("/project/models")
