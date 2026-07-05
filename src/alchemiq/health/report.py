"""Health report dataclasses returned by ``check_health``."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    """Probe result for a single backend component.

    Returned as part of :class:`.HealthReport` from :func:`.check_health`.
    ``latency_ms`` is ``None`` when the probe did not complete (error or timeout).
    """

    name: str
    healthy: bool
    latency_ms: float | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Aggregate health report across all probed components.

    Returned by :func:`.check_health`.  ``healthy`` is ``True`` only when every
    :class:`.ComponentHealth` in ``components`` is healthy.

    E.g.::

        report = await check_health()
        data = report.to_dict()
        # {"status": "healthy", "checks": [{"name": "postgres", "healthy": True, ...}]}

    .. seealso:: :func:`.check_health` - produces this report.
    """

    healthy: bool
    components: tuple[ComponentHealth, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialise to a JSON-safe dict with ``status`` and ``checks`` keys."""
        return {
            "status": "healthy" if self.healthy else "unhealthy",
            "checks": [
                {
                    "name": c.name,
                    "healthy": c.healthy,
                    "latency_ms": c.latency_ms,
                    "error": c.error,
                }
                for c in self.components
            ],
        }
