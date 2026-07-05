from __future__ import annotations

import pytest

from alchemiq.scaffold.render import render

pytestmark = pytest.mark.unit


def test_render_writes_files(tmp_path) -> None:
    render([("a.txt", "hi\n"), ("sub/b.txt", "yo\n")], tmp_path / "proj", force=False)
    assert (tmp_path / "proj" / "a.txt").read_text() == "hi\n"
    assert (tmp_path / "proj" / "sub" / "b.txt").read_text() == "yo\n"


def test_render_refuses_nonempty_dir(tmp_path) -> None:
    dest = tmp_path / "proj"
    dest.mkdir()
    (dest / "x").write_text("existing")
    with pytest.raises(FileExistsError):
        render([("a.txt", "hi\n")], dest, force=False)


def test_render_force_overwrites(tmp_path) -> None:
    dest = tmp_path / "proj"
    dest.mkdir()
    (dest / "x").write_text("existing")
    render([("a.txt", "hi\n")], dest, force=True)
    assert (dest / "a.txt").read_text() == "hi\n"


def test_render_marks_shell_scripts_executable(tmp_path) -> None:
    import os

    render(
        [("docker/postgres-init.sh", "#!/bin/bash\n"), ("a.txt", "hi\n")],
        tmp_path / "proj",
        force=False,
    )
    script = tmp_path / "proj" / "docker" / "postgres-init.sh"
    assert os.access(script, os.X_OK)  # postgres runs (not sources) executable init scripts
    assert not os.access(tmp_path / "proj" / "a.txt", os.X_OK)
