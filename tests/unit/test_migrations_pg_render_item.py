import pytest

from alchemiq.migrations.postgres.render import render_item
from alchemiq.types.maybe import _MaybeType
from alchemiq.types.numeric import MinorUnits, Positive
from alchemiq.types.special import _EncryptedType
from alchemiq.types.temporal import EpochInt

pytestmark = pytest.mark.unit


class _Ctx:
    """Minimal Alembic autogen_context stub for render_item unit tests.

    Satisfies the attributes accessed by alembic.autogenerate.render._repr_type
    when rendering standard SQLAlchemy impl types (LargeBinary, BigInteger, etc.).
    """

    class _MC:
        pass  # no 'impl' attribute -> impl_rt = None inside _repr_type

    def __init__(self) -> None:
        self.migration_context = self._MC()
        self.opts: dict = {
            "render_item": None,
            "sqlalchemy_module_prefix": "sa.",
            "user_module_prefix": None,
        }
        self.imports: set[str] = set()


def test_render_item_handles_encrypted_type() -> None:
    ctx = _Ctx()
    out = render_item("type", _EncryptedType(), ctx)
    assert isinstance(out, str) and out, "expected non-empty str for _EncryptedType"


def test_render_item_handles_epoch_int() -> None:
    ctx = _Ctx()
    out = render_item("type", EpochInt(), ctx)
    assert isinstance(out, str) and out, "expected non-empty str for EpochInt"


def test_render_item_handles_minor_units() -> None:
    ctx = _Ctx()
    out = render_item("type", MinorUnits(), ctx)
    assert isinstance(out, str) and out, "expected non-empty str for MinorUnits"


def test_render_item_handles_maybe_type() -> None:
    ctx = _Ctx()
    out = render_item("type", _MaybeType(Positive()), ctx)
    assert isinstance(out, str) and out, "expected non-empty str for _MaybeType"


def test_render_item_defers_for_stock_types() -> None:
    from sqlalchemy import Integer

    assert render_item("type", Integer(), _Ctx()) is False


# --- backend unit tests (no real DB required) ---


def test_pg_backend_make_config_raises_when_postgres_none(tmp_path) -> None:
    from alchemiq.migrations.config import AlchemiqConfig
    from alchemiq.migrations.errors import MigrationConfigError
    from alchemiq.migrations.postgres.backend import _make_config

    cfg = AlchemiqConfig(root=tmp_path, models=(), postgres=None)
    with pytest.raises(MigrationConfigError, match="postgres is not configured"):
        _make_config(cfg)


def test_suppress_empty_clears_directives_and_prints(capsys) -> None:
    from alchemiq.migrations.postgres.backend import _suppress_empty

    class _FakeOps:
        def is_empty(self) -> bool:
            return True

    class _FakeDir:
        upgrade_ops = _FakeOps()

    directives = [_FakeDir()]
    _suppress_empty(None, None, directives)
    assert directives == []
    assert "No changes detected" in capsys.readouterr().out


def test_suppress_empty_keeps_non_empty_directives() -> None:
    from alchemiq.migrations.postgres.backend import _suppress_empty

    class _FakeOps:
        def is_empty(self) -> bool:
            return False

    class _FakeDir:
        upgrade_ops = _FakeOps()

    directives = [_FakeDir()]
    _suppress_empty(None, None, directives)
    assert len(directives) == 1  # not cleared


def test_alembic_repr_type_private_api_present() -> None:
    """Canary: render_item depends on Alembic's PRIVATE _repr_type. If a future
    Alembic removes/renames it, this fails loudly so we catch it on upgrade."""
    from alembic.autogenerate.render import _repr_type

    assert callable(_repr_type)


def test_pg_backend_showsql_offline_mode(tmp_path) -> None:
    """showsql (sql=True) runs Alembic in offline mode - no DB connection required."""
    from alchemiq.migrations.config import AlchemiqConfig, PostgresSettings
    from alchemiq.migrations.postgres import backend

    cfg = AlchemiqConfig(
        root=tmp_path,
        models=(),
        postgres=PostgresSettings(host="localhost", database="d", username="u", password="p"),
    )
    # With an empty versions directory there is nothing to generate, but Alembic
    # must run env.py in offline mode without raising.
    backend.showsql(cfg)
