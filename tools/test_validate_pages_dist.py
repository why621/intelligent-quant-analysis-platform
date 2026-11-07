"""Regression checks for paths that must never enter the Pages archive."""

import os
import tempfile
import unittest
from pathlib import Path

from validate_pages_dist import PUBLIC_FILES, validate


class PagesContentsTest(unittest.TestCase):
    def test_release_and_unexpected_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in PUBLIC_FILES:
                (root / name).touch()
            (root / "assets").mkdir()
            (root / "assets/main-Abc_1234.js").touch()
            validate(root)
            for name in [".env", "backup.sql", "assets/secrets.js", "assets/main.js.map"]:
                with self.subTest(name=name):
                    path = root / name
                    path.touch()
                    with self.assertRaises(ValueError):
                        validate(root)
                    path.unlink()
            (root / ".git").mkdir()
            with self.assertRaises(ValueError):
                validate(root)
            (root / ".git").rmdir()
            alias = root / "assets/alias-Abc_1234.js"
            for link in [os.symlink, os.link]:
                link(root / "index.html", alias)
                with self.assertRaises(ValueError):
                    validate(root)
                alias.unlink()
            (root / "index.html").unlink()
            with self.assertRaises(ValueError):
                validate(root)


if __name__ == "__main__":
    unittest.main()
