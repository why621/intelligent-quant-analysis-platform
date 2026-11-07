"""Check the complete static tree before uploading it to GitHub Pages."""

import re
import stat
import sys
from pathlib import Path

PUBLIC_FILES = {"index.html", "favicon.svg", "icons.svg"}
ASSET = re.compile(r"assets/[A-Za-z0-9_-]+-[A-Za-z0-9_-]{8}\.(?:js|css|png)")


def validate(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("expected a build directory")
    seen = set()
    entries = list(root.iterdir())
    while entries:
        entry = entries.pop()
        name = entry.relative_to(root).as_posix()
        info = entry.lstat()
        if name == "assets" and stat.S_ISDIR(info.st_mode):
            entries.extend(entry.iterdir())
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError(f"unexpected file type: {name!r}")
        if name not in PUBLIC_FILES and not ASSET.fullmatch(name):
            raise ValueError(f"unexpected public path: {name!r}")
        seen.add(name)
    if PUBLIC_FILES - seen or not any(name.endswith(".js") for name in seen):
        raise ValueError("incomplete frontend build")


if __name__ == "__main__":
    validate(Path(sys.argv[1]))
