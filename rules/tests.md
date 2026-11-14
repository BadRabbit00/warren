---
paths:
  - "**/test/**"
  - "**/tests/**"
  - "**/__tests__/**"
  - "**/integration_test/**"
  - "**/e2e/**"
  - "**/test_*.py"
  - "**/conftest.py"
  - "**/*_test.go"
  - "**/*_test.dart"
  - "**/*.test.*"
  - "**/*.spec.*"
---

# Tests

## Scope

Every test file. Our layout: a service's tests in `src/<service>/tests/`, shared tests in `/tests`, end-to-end tests in `/tests/e2e`. Rust tests live in `<crate>/tests/`, never in `#[cfg(test)]` modules inside `src/`. The one exception is Flutter/Dart, which keeps its native `test/` and `integration_test/`. Existing projects keep their layout (`_test.go`, `*.test.tsx`). Only `test-writer` writes tests (a hook enforces it). Everyone else reads.

## Rules

- R-TEST-LAYER: test each rule on its layer. A domain rule gets a unit test with no DB or network. A service scenario uses a fake repository plus key scenarios on the test DB. A repository gets an integration test on a real DB. An endpoint gets an API test with the role × endpoint matrix.
- R-TEST-REAL-DB: tests run against the same DBMS and version as production. The schema comes from migrations, never from `create_all`. No SQLite instead of PostgreSQL, no mongomock.
- R-TEST-FAKE-BOUNDARY: fake only what is outside the system: external APIs, LLMs, email, payment gateways, time, randomness. Never mock your own repository inside a repository test.
- R-TEST-BEHAVIOUR: assert results (return value, DB state, response, published event), not the order of internal calls.
- R-TEST-NAMES: a test name is a statement about behaviour: `test_paid_order_cannot_be_cancelled`, `TestCancel_PaidOrder_ReturnsConflict`, `cancel_rejects_paid_order`.
- R-TEST-ISOLATION: every test creates its own data (factories), cleans up (transaction rollback or a schema per worker), and passes in any order and in parallel.
- R-TEST-DETERMINISM: no `sleep` for waiting; wait for a condition with a timeout. Time comes from an injected clock, randomness from a fixed seed.
- R-TEST-MUST-FAIL-FIRST: a new test is run once against code where the rule is broken (or absent) and fails for the right reason.
- R-TEST-NO-SKIP: never delete, weaken, or skip a red test to get green. `skip` only with a reason and an issue link.

## Examples

### R-TEST-REAL-DB — same database as production

Bad:
```python
@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```
Why: different types, locking, and SQL dialect, and broken migrations go unnoticed. Green tests, red production.

Good:
```python
@pytest.fixture(scope="session")
def database_url(postgres_container) -> str:          # testcontainers or the compose test DB
    alembic_upgrade_head(postgres_container.url)        # schema from the real migrations
    return postgres_container.url

@pytest.fixture
async def session(engine):
    async with engine.connect() as conn, conn.begin() as tx:
        yield AsyncSession(bind=conn)
        await tx.rollback()                              # isolation per test
```

### R-TEST-BEHAVIOUR — assert the outcome

Bad:
```python
async def test_cancel(order_service, mocker):
    spy = mocker.spy(order_service.orders, "save")
    await order_service.cancel(order.id)
    spy.assert_called_once()
```
Why: it passes even if the status is wrong, and it breaks on any refactor.

Good:
```python
async def test_new_order_can_be_cancelled(order_service, make_order, session):
    order = await make_order(status=OrderStatus.NEW)
    await order_service.cancel(order.id)
    assert (await session.get(Order, order.id)).status == OrderStatus.CANCELLED

async def test_paid_order_cannot_be_cancelled(order_service, make_order):
    order = await make_order(status=OrderStatus.PAID)
    with pytest.raises(OrderAlreadyPaid):
        await order_service.cancel(order.id)
```

### R-TEST-DETERMINISM — no sleeping

Bad:
```go
go worker.Run(ctx)
time.Sleep(2 * time.Second)
require.Equal(t, "sent", repo.Status(id))
```
Why: slow on a fast machine, flaky on a slow one.

Good:
```go
go worker.Run(ctx)
require.Eventually(t, func() bool { return repo.Status(id) == "sent" }, 5*time.Second, 20*time.Millisecond)
```
