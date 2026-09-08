"""Offline validation only; no SSH or cloud mutations."""
import subprocess
from unittest.mock import patch

import deploy_cloud_preview as deploy
import pytest


@pytest.mark.parametrize("action", ["backup", "build", "cutover", "rollback"])
def test_remote_plans_are_valid_bash_and_keep_data(action):
    revision = "a" * 40
    with patch("sys.argv", ["deploy", action, "--revision", revision]), patch.object(
        deploy, "remote"
    ) as remote:
        deploy.main()
    script = deploy.PREFIX + remote.call_args.args[0]
    subprocess.run(["bash", "-n"], input=script, text=True, check=True)
    assert "down" not in script
    assert "quant-data-update" not in script
    assert "reset --hard" not in script
    assert "rm " not in script
    if action == "backup":
        assert "src.backup(dst)" in script
        assert "PRAGMA integrity_check" in script
    if action == "build":
        assert "merge --ff-only" in script
    if action == "cutover":
        assert "rollback-cr015" in script


def test_revision_rejects_shell_input():
    with patch("sys.argv", ["deploy", "build", "--revision", "HEAD;true"]), patch.object(
        deploy, "remote"
    ) as remote, pytest.raises(SystemExit):
        deploy.main()
    remote.assert_not_called()
