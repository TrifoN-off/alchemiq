"""Write a render plan produced by :mod:`alchemiq.scaffold.plan` to disk."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from alchemiq.scaffold.plan import RenderedFile


def render(files: Iterable[RenderedFile], dest: Path, *, force: bool) -> None:
    """Write each ``(relpath, text)`` pair in *files* under *dest*.

    Raises ``FileExistsError`` when *dest* is a non-empty directory and
    ``force=False``; parent directories are created as needed.
    """
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()) and not force:
        raise FileExistsError(f"{dest} exists and is not empty (use --force to overwrite)")
    for relpath, text in files:
        target = dest / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        if target.suffix == ".sh":
            # Shell scripts must be executable: the postgres image *runs*
            # (not sources) init scripts that carry the executable bit.
            target.chmod(0o755)
