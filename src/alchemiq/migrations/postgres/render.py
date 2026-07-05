"""Custom Alembic render hook that strips alchemiq TypeDecorators from migrations."""

from __future__ import annotations

from typing import Any

from sqlalchemy.types import TypeDecorator


def render_item(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    """Render alchemiq custom TypeDecorators as their DDL impl type.

    Every alchemiq.types.* TypeDecorator is emitted as its underlying storage
    type (e.g. _EncryptedType -> sa.LargeBinary) so generated migrations always
    import cleanly. The TypeDecorator's Python-side behaviour (encryption, Maybe,
    epoch conversion) is enforced by the ORM at runtime, not by the DDL.
    Returning False defers to Alembic's default rendering for stock types.
    """
    if (
        type_ == "type"
        and isinstance(obj, TypeDecorator)
        and obj.__class__.__module__.startswith("alchemiq.types")
    ):
        # PRIVATE Alembic API: alembic.autogenerate.render._repr_type has no public
        # equivalent (verified on Alembic 1.18.x). Guarded by the canary test
        # test_alembic_repr_type_private_api_present - revisit if a public API appears.
        from alembic.autogenerate.render import _repr_type

        return _repr_type(obj.impl_instance, autogen_context)
    return False
