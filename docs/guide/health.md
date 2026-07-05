# Health checks

alchemiq provides async health probes for all configured backends (PostgreSQL,
ClickHouse, and the cache layer).  The probes run concurrently and collect
latency measurements, making the result suitable for Kubernetes
``readinessProbe`` and ``livenessProbe`` endpoints.

The public API is importable directly from ``alchemiq.health``:

```python
from alchemiq.health import check_health, HealthReport, ComponentHealth
```

---

## Running a health check

{func}`~alchemiq.check_health` is an async function.  Call it from any async
context - a FastAPI lifespan, a background task, or a manual probe:

```python
from alchemiq.health import check_health

report = await check_health()
if not report.healthy:
    print(report.to_dict())
```

The function probes every configured backend concurrently.  Backends that are
not configured are silently skipped, so the same call works whether you have
one database or three.  When no backends are configured at all (e.g. in unit
tests that never call ``configure``), ``check_health`` returns a trivially
healthy report with an empty ``components`` tuple.  An opt-in strict-readiness
mode that treats "no backend configured" as unhealthy is on the roadmap (see
{doc}`whats-not-in-v1`).

### Timeout

Each probe is guarded by a per-call timeout (default five seconds).  Pass a
different value when a tighter budget is appropriate:

```python
report = await check_health(timeout=2.0)
```

A probe that times out or raises an exception is recorded as unhealthy rather
than propagating the error to the caller.

---

## Return shape

### {class}`~alchemiq.HealthReport`

The aggregate result returned by {func}`~alchemiq.check_health`.

| Field | Type | Description |
|---|---|---|
| ``healthy`` | ``bool`` | ``True`` only when every component probe succeeded |
| ``components`` | ``tuple[ComponentHealth, ...]`` | One entry per probed backend |

```python
report.to_dict()
# {
#     "status": "healthy",          # or "unhealthy"
#     "checks": [
#         {"name": "postgres",   "healthy": True,  "latency_ms": 1.4,  "error": None},
#         {"name": "clickhouse", "healthy": False, "latency_ms": None, "error": "..."},
#         {"name": "cache",      "healthy": True,  "latency_ms": 0.3,  "error": None},
#     ]
# }
```

### {class}`~alchemiq.ComponentHealth`

The probe result for a single backend component.

| Field | Type | Description |
|---|---|---|
| ``name`` | ``str`` | Component identifier: ``"postgres"``, ``"clickhouse"``, or ``"cache"`` |
| ``healthy`` | ``bool`` | Whether the probe succeeded |
| ``latency_ms`` | ``float \| None`` | Round-trip latency in milliseconds; ``None`` when the probe did not complete |
| ``error`` | ``str \| None`` | Short error description when unhealthy; ``None`` on success |

Both classes are frozen dataclasses (immutable, ``__slots__``).

---

## FastAPI integration

The ``[fastapi]`` extra provides ``health_router``, a pre-built ``APIRouter``
that mounts two endpoints:

| Endpoint | Kubernetes probe | Behaviour |
|---|---|---|
| ``GET /health/ready`` | ``readinessProbe`` | Calls ``check_health``; returns 200 when healthy, 503 when any component is degraded |
| ``GET /health/live`` | ``livenessProbe`` | Always returns 200 ``{"status": "alive"}``; no backend dependency |

Include the router once at application startup:

```python
from fastapi import FastAPI
from alchemiq.fastapi import health_router

app = FastAPI()
app.include_router(health_router())
```

The router accepts optional keyword arguments:

| Parameter | Default | Description |
|---|---|---|
| ``prefix`` | ``"/health"`` | URL prefix for both routes |
| ``timeout`` | ``5.0`` | Per-probe timeout passed to ``check_health`` |
| ``include_liveness`` | ``True`` | Set to ``False`` to omit the ``GET /live`` route |

```python
# Custom prefix:
app.include_router(health_router(prefix="/probe"))

# Readiness only (no liveness route):
app.include_router(health_router(include_liveness=False))
```

---

## Liveness vs readiness

The two probe types serve different purposes in Kubernetes:

**Readiness** (`/health/ready`) answers "can this pod serve traffic right now?"
A pod failing readiness is removed from the load-balancer pool but is not
restarted.  Use it to signal that a required database or cache is unreachable.

**Liveness** (`/health/live`) answers "is this pod still alive?"  A pod failing
liveness is restarted by the kubelet.  The liveness route in alchemiq is
intentionally dependency-free - it just confirms the event loop is running -
because a liveness failure that triggers a restart would not fix a broken
database connection.

A typical Kubernetes deployment manifest:

```yaml
readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10

livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30
```
