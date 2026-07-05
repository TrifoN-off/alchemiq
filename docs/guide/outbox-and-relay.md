# Outbox and relay

The transactional outbox pattern solves the dual-write problem: a domain event
is written to the database in the **same transaction** as the business row, so
the event cannot be lost even if the broker is temporarily unavailable.  A
background worker (`Relay`) then drains the outbox table and delivers events to
the broker with at-least-once semantics.

```bash
pip install "alchemiq[outbox,postgres]"
```

---

## The outbox table

Import of ``alchemiq.outbox`` creates the `outbox` table automatically.
{class}`~alchemiq.OutboxEvent` is the ORM model for each row:

| Column | Type | Description |
|---|---|---|
| ``id`` | int PK | Auto-assigned surrogate key |
| ``topic`` | str | Broker routing key, e.g. ``"user.signed_up"`` |
| ``aggregate_type`` | str (nullable) | Optional model name |
| ``aggregate_id`` | str (nullable) | Optional partition key |
| ``event_type`` | str (nullable) | Optional sub-type discriminator |
| ``payload`` | JSON | Event data |
| ``headers`` | JSON (nullable) | Optional broker-level headers |
| ``status`` | str | ``pending`` -> ``published`` / ``failed`` -> ``dead`` |
| ``attempts`` | int | Delivery attempt counter |
| ``created_at`` | timestamptz | Row creation time |
| ``published_at`` | timestamptz (nullable) | Successful delivery timestamp |
| ``last_error`` | str (nullable) | Last delivery exception message |

---

## Publishing events manually

{func}`~alchemiq.publish` writes an outbox row in its own autocommit
transaction.  Use it for manual event emission from background tasks or CLI
scripts.  To tie the event to a business transaction, wrap the call in a
{class}`~alchemiq.UnitOfWork`.

```python
from alchemiq import publish

# simple dict payload
await publish("user.signed_up", {"id": 1, "email": "ada@example.com"})

# Pydantic payload - dumped automatically
await publish("billing.upgraded", BillingUpgraded(plan="pro"), key="user-42")
```

Parameters:

| Parameter | Description |
|---|---|
| ``topic`` | Broker routing key |
| ``payload`` | ``dict`` or Pydantic ``BaseModel`` |
| ``key`` | Optional partition key (stored as ``aggregate_id``) |
| ``headers`` | Optional broker-level headers dict |

---

## Automatic capture via model signals

If a model has ``Meta.outbox = True``, alchemiq writes an outbox row
automatically on every create, update, or delete - in the same transaction as
the business operation.  No manual ``publish`` call is required.

```python
from alchemiq import Model
from alchemiq.types import PK

class Order(Model):
    id: PK[int]
    status: str

    class Meta:
        outbox = True
```

---

## The Publisher protocol

{class}`~alchemiq.Publisher` is a structural (duck-typed) protocol.  Any object
that exposes an async ``publish(message)`` method satisfies it:

```python
from alchemiq import OutboxMessage
from alchemiq.outbox import Publisher, TransientPublishError

class MyBrokerPublisher:
    async def publish(self, message: OutboxMessage) -> None:
        try:
            await broker.send(message.topic, message.payload)
        except BrokerConnectionError as e:
            raise TransientPublishError(str(e)) from e
```

Raise {class}`~alchemiq.TransientPublishError` for connection failures - the
relay backs off without incrementing ``attempts``.  Any other exception poisons
the row (increments ``attempts``, marks it ``failed`` or ``dead``).

An optional ``publish_batch(messages)`` method is detected by duck-typing when
present.  It is **not** part of the protocol contract, so any object with only
``publish`` satisfies ``isinstance(obj, Publisher)``.

---

## The Relay worker

{class}`~alchemiq.Relay` drains the outbox table and delivers rows to a broker.
Run it as an asyncio background task:

```python
import asyncio
from alchemiq.outbox import Relay

relay = Relay(my_publisher, batch_size=50, poll_interval=2.0, max_attempts=5)

task = asyncio.create_task(relay.run())

# on shutdown:
relay.stop()
await task
```

### What Relay claims each cycle

Each cycle claims a batch of **both ``pending`` and ``failed`` rows** with
``FOR UPDATE SKIP LOCKED``.  This makes it safe to run multiple concurrent
workers without double-delivery.

### Error taxonomy

| Error type | Behaviour |
|---|---|
| {class}`~alchemiq.TransientPublishError` (per-message or batch) | Whole-batch rollback; ``attempts`` is **not** incremented; relay sleeps ``error_backoff`` seconds |
| Any other exception - per-message path | Row poisoned: ``attempts`` incremented; status -> ``failed`` or ``dead`` |
| Any other exception - ``publish_batch`` path | **All rows in the batch are poisoned together** (not row-by-row) |

The ``publish_batch`` poison behaviour means a single bad batch poisons the
entire set of claimed rows.  Use per-message ``publish`` if you need finer
fault isolation.

### Parameters

| Parameter | Default | Description |
|---|---|---|
| ``publisher`` | *(required)* | Delivery adapter satisfying the ``Publisher`` protocol |
| ``batch_size`` | 100 | Maximum rows claimed per cycle |
| ``poll_interval`` | 1.0 s | Wait between cycles when the batch was not full |
| ``max_attempts`` | 5 | Attempts before a row is marked ``dead`` |
| ``error_backoff`` | 5.0 s | Sleep after a transient broker error |

---

## FastStream publishing

The ``[faststream]`` extra provides ``FastStreamPublisher``, a ``Publisher``
adapter that works with any FastStream broker (RabbitMQ, Kafka, NATS, Redis):

```bash
pip install "alchemiq[faststream,postgres]"
```

```python
from faststream.rabbit import RabbitBroker
from alchemiq import Relay
from alchemiq.faststream import FastStreamPublisher

broker = RabbitBroker("amqp://guest:guest@localhost/")
await broker.connect()

relay = Relay(FastStreamPublisher(broker), batch_size=200)
await relay.run()
```

The ``correlation_id`` of each published message is set to ``str(message.id)``
(the outbox row PK) so consumers can deduplicate under the at-least-once
contract.  Event metadata (``aggregate_type``, ``aggregate_id``, ``event_type``)
is forwarded as broker headers under the ``alchemiq.*`` prefix.

``FastStreamPublisher`` exposes only ``publish`` (no ``publish_batch``), so the
relay always uses the per-message delivery path with it - each row is published
and acknowledged individually rather than as a batch.

### Consumer dependency injection

``alchemiq.faststream`` exposes the same providers as ``alchemiq.fastapi``.
Use them as ``Depends`` targets in FastStream subscribers to inject a session,
unit of work, or repository:

```python
from faststream import Depends, FastStream
from alchemiq.faststream import lifespan, unit_of_work
from alchemiq import Repository

app = FastStream(broker, lifespan=lifespan("postgresql+asyncpg://user:pass@localhost/mydb"))

@broker.subscriber("orders.created")
async def on_order(evt: dict, uow=Depends(unit_of_work)):
    async with uow:
        order = await Repository(Order).create(**evt)
```

Outbox capture fires automatically when the subscriber writes through the unit
of work.
