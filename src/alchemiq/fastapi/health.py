"""Health-check routes. Requires the ``[fastapi]`` extra.

``/ready`` probes configured backends (k8s readinessProbe); ``/live`` is a dependency-free
liveness signal (k8s livenessProbe).
"""

from fastapi import APIRouter, Response

from alchemiq.health import check_health


def health_router(
    *, prefix: str = "/health", timeout: float = 5.0, include_liveness: bool = True
) -> APIRouter:
    """Build an ``APIRouter`` with ``GET /ready`` and optionally ``GET /live`` endpoints.

    ``GET /ready`` calls :func:`.check_health` and returns 200 when all components are
    healthy or 503 when any component is degraded - suitable for a Kubernetes
    ``readinessProbe``.  ``GET /live`` always returns 200 with ``{"status": "alive"}``
    and has no backend dependencies - suitable for a Kubernetes ``livenessProbe``.

    E.g.::

        from fastapi import FastAPI
        from alchemiq.fastapi import health_router

        app = FastAPI()
        app.include_router(health_router())
        # custom prefix:
        app.include_router(health_router(prefix="/probe"))
        # readiness only - omit the /live route:
        app.include_router(health_router(include_liveness=False))

    :param prefix: URL prefix for the health routes (default ``"/health"``).
    :param timeout: seconds passed to :func:`.check_health` for backend probes
        (default ``5.0``).
    :param include_liveness: when ``False``, the ``GET /live`` route is omitted.
    :return: a configured ``APIRouter`` ready to pass to ``app.include_router()``.

    .. seealso:: :func:`.check_health` - the underlying health probe implementation.
    """
    router = APIRouter(prefix=prefix, tags=["health"])

    @router.get("/ready")
    async def ready(response: Response) -> dict[str, object]:
        report = await check_health(timeout=timeout)
        response.status_code = 200 if report.healthy else 503
        return report.to_dict()

    if include_liveness:

        @router.get("/live")
        async def live() -> dict[str, str]:
            return {"status": "alive"}

    return router
