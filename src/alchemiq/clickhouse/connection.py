"""Process-global ClickHouse connection lifecycle (configure / dispose / lazy client)."""

from __future__ import annotations

import asyncio
from typing import Any

from alchemiq.exceptions import ClickHouseNotConfiguredError

_config: dict[str, Any] | None = None
_client: Any = None
_lock = asyncio.Lock()


def configure_clickhouse(
    dsn: str | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
    username: str = "default",
    password: str = "",
    database: str = "default",
    secure: bool = False,
    settings: dict[str, Any] | None = None,
    **client_kw: Any,
) -> None:
    r"""Store ClickHouse connection parameters; the async client connects on first use.

    Call once at application startup (e.g. inside a FastAPI/FastStream lifespan).
    Pass either a ``dsn`` URL or individual ``host``/``port`` keyword arguments.
    The client is created lazily on the first internal client-creation call and is
    shared across the process.  Call :func:`.dispose_clickhouse` on shutdown.

    E.g.::

        from alchemiq.clickhouse import configure_clickhouse, dispose_clickhouse

        # host/port form:
        configure_clickhouse(host="localhost", port=8123)

        # DSN form:
        configure_clickhouse(dsn="clickhouse://default:@localhost/default")

    :param dsn: ClickHouse DSN URL (e.g. ``clickhouse://user:pass@host/db``).
        Mutually optional with ``host``/``port`` - use one or the other.
    :param host: Server hostname.
    :param port: Server port (default ``8123`` for HTTP, ``8443`` for HTTPS).
    :param username: ClickHouse username (default ``"default"``).
    :param password: ClickHouse password (default ``""``).
    :param database: Target database name (default ``"default"``).
    :param secure: Use TLS/HTTPS if ``True`` (default ``False``).
    :param settings: Extra ClickHouse server settings passed to the client.
    :param client_kw: Additional keyword arguments forwarded to
        ``clickhouse_connect.get_async_client``.

    .. seealso:: :func:`.dispose_clickhouse` - close and reset the client on shutdown.
    """
    global _config, _client
    cfg: dict[str, Any] = {
        "username": username,
        "password": password,
        "database": database,
        "secure": secure,
    }
    if dsn is not None:
        cfg["dsn"] = dsn
    if host is not None:
        cfg["host"] = host
    if port is not None:
        cfg["port"] = port
    if settings is not None:
        cfg["settings"] = settings
    cfg.update(client_kw)
    _config = cfg
    _client = None


def is_clickhouse_configured() -> bool:
    """Return True if configure_clickhouse() has been called and not yet disposed."""
    return _config is not None


async def get_clickhouse_client() -> Any:
    """Return the process-global async client, creating it lazily on first call."""
    global _client
    if _config is None:
        raise ClickHouseNotConfiguredError(
            "ClickHouse is not configured; call configure_clickhouse(...) first"
        )
    if _client is not None:  # fast path, no lock
        return _client
    async with _lock:
        if _client is None:  # double-checked under lock
            import clickhouse_connect  # ty: ignore[unresolved-import]

            _client = await clickhouse_connect.get_async_client(**_config)
    return _client


async def dispose_clickhouse() -> None:
    """Close the process-global client and clear all connection state.

    Safe to call even if the client was never created (no-op in that case).
    Typically called in a lifespan ``finally`` block or in test teardown.

    .. seealso:: :func:`.configure_clickhouse` - reconfigure after disposing.
    """
    global _config, _client
    if _client is not None:
        await _client.close()
    _client = None
    _config = None
