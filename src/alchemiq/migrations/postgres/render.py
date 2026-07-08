"""Custom Alembic render hook that strips alchemiq TypeDecorators from migrations."""

from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.types import TypeDecorator

# Alembic's default "type" rendering only tracks the import for the OUTER
# dialect type (e.g. adds "from sqlalchemy.dialects import postgresql" for
# JSONB/ARRAY) - a nested TypeEngine baked into that type's own __repr__
# (JSONB.astext_type, ARRAY.item_type) is left as a bare, unqualified class
# name (e.g. "Text()", "Integer()"). The generated migration then fails with
# NameError the first time it is actually executed. Track those nested
# imports ourselves; alchemiq's JSON/Array fields both use these types
# directly as their column_type() - including when wrapped in Maybe[...] -
# so this affects every project (PG or SQLite) with a JSON or Array column,
# including the always-registered Outbox model. The plain
# "from sqlalchemy import <Name>" heuristic below only needs to cover
# top-level sqlalchemy exports (Text, Integer, ...), which is all the nested
# types alchemiq's own field types produce today.
_NESTED_TYPE_ATTR: dict[type, str] = {JSONB: "astext_type", ARRAY: "item_type"}


def render_item(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    """Render alchemiq custom TypeDecorators as their DDL impl type.

    Every alchemiq.types.* TypeDecorator is emitted as its underlying storage
    type (e.g. _EncryptedType -> sa.LargeBinary) so generated migrations always
    import cleanly. The TypeDecorator's Python-side behaviour (encryption, Maybe,
    epoch conversion) is enforced by the ORM at runtime, not by the DDL.
    Returning False defers to Alembic's default rendering for stock types.
    """
    if type_ != "type":
        return False

    is_alchemiq_decorator = isinstance(obj, TypeDecorator) and obj.__class__.__module__.startswith(
        "alchemiq.types"
    )
    # Resolve the type that will actually appear in the rendered DDL: for an
    # alchemiq TypeDecorator (including Maybe[...]-wrapped fields) that is its
    # impl_instance, not obj itself - so the nested-import scan below must run
    # against the same target that gets rendered.
    target = obj.impl_instance if is_alchemiq_decorator else obj

    for dialect_type, attr in _NESTED_TYPE_ATTR.items():
        if isinstance(target, dialect_type):
            nested = getattr(target, attr, None)
            if nested is not None:
                autogen_context.imports.add(f"from sqlalchemy import {type(nested).__name__}")

    if is_alchemiq_decorator:
        # PRIVATE Alembic API: alembic.autogenerate.render._repr_type has no public
        # equivalent (verified on Alembic 1.18.x). Guarded by the canary test
        # test_alembic_repr_type_private_api_present - revisit if a public API appears.
        from alembic.autogenerate.render import _repr_type

        return _repr_type(target, autogen_context)
    return False
