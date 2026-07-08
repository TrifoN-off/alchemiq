from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

import alchemiq

pytestmark = pytest.mark.unit

_PKG_DIR = Path(alchemiq.__file__).parent
_REPO_ROOT = _PKG_DIR.parent.parent  # src/alchemiq/__init__.py -> repo root


def test_py_typed_is_shipped() -> None:
    assert (_PKG_DIR / "py.typed").is_file()


def test_license_file_exists() -> None:
    license_path = _REPO_ROOT / "LICENSE"
    if not license_path.is_file():
        pytest.skip("LICENSE not present in installed tree")
    assert "MIT" in license_path.read_text(encoding="utf-8")


def test_pyproject_metadata() -> None:
    pp = _REPO_ROOT / "pyproject.toml"
    if not pp.is_file():
        pytest.skip("pyproject.toml not in installed tree")
    data = tomllib.loads(pp.read_text(encoding="utf-8"))
    classifiers = data["project"]["classifiers"]
    assert "Typing :: Typed" in classifiers
    assert "Programming Language :: Python :: 3.12" in classifiers
    assert "Programming Language :: Python :: 3.14" in classifiers
    assert data["project"]["requires-python"] == ">=3.12"
    assert data["project"]["license"] == "MIT"
    assert "LICENSE" in data["project"]["license-files"]
    assert data["project"]["authors"][0]["name"] == "Trifonov Nikita"


def test_optional_dependencies_ship_working_drivers() -> None:
    pp = _REPO_ROOT / "pyproject.toml"
    if not pp.is_file():
        pytest.skip("pyproject.toml not in installed tree")
    data = tomllib.loads(pp.read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    # [postgres] provides the asyncpg driver every postgresql+asyncpg DSN needs.
    assert any(dep.startswith("asyncpg") for dep in extras["postgres"])
    # [clickhouse] must pull clickhouse-connect[async] (aiohttp) for get_async_client.
    assert any(dep.startswith("clickhouse-connect[async]") for dep in extras["clickhouse"])
    # [all] must include the postgres driver extra.
    assert any("postgres" in dep for dep in extras["all"])
    # The sqlite extra must ship the async driver, and [all] must include it.
    assert any(dep.startswith("aiosqlite") for dep in extras["sqlite"])
    assert any("sqlite" in dep for dep in extras["all"])


def test_scaffold_templates_are_shipped() -> None:
    templates = _PKG_DIR / "scaffold" / "templates"
    assert (templates / "single" / "pyproject.toml.tmpl").is_file()
    assert (templates / "monorepo_root" / "pyproject.toml.tmpl").is_file()


def test_scaffold_templates_packaged() -> None:
    pp = _REPO_ROOT / "pyproject.toml"
    if not pp.is_file():
        pytest.skip("pyproject.toml not in installed tree")
    data = tomllib.loads(pp.read_text(encoding="utf-8"))
    wheel = data["tool"]["hatch"]["build"]["targets"]["wheel"]
    # packages=["src/alchemiq"] makes hatchling include all package data
    # (scaffold/templates/*.tmpl, the .mako, py.typed) - no force-include needed.
    assert wheel["packages"] == ["src/alchemiq"]
    assert "force-include" not in wheel  # removed: was redundant + broke hatchling >=1.27


def test_alchemiq_init_entrypoint() -> None:
    pp = _REPO_ROOT / "pyproject.toml"
    if not pp.is_file():
        pytest.skip("pyproject.toml not in installed tree")
    data = tomllib.loads(pp.read_text(encoding="utf-8"))
    assert data["project"]["scripts"]["alchemiq"] == "alchemiq.cli:main"
