# Testing - examples

Only `test-writer` writes tests; you read them and make them pass.

### R-PYS-TEST-REAL-DB - same database as production

Bad:
```python
@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```
Why: different types, locking and dialect; broken migrations go unnoticed. Green tests, red production.

Good:
```python
@pytest.fixture(scope="session")
def database_url(postgres_container) -> str:        # testcontainers or the compose test DB
    alembic_upgrade_head(postgres_container.url)      # schema from the real migrations
    return postgres_container.url

@pytest.fixture
async def session(engine):
    async with engine.connect() as conn, conn.begin() as tx:
        yield AsyncSession(bind=conn)
        await tx.rollback()                            # isolation per test
```

### R-PYS-TEST-OUTCOME - assert the result

Bad:
```python
async def test_cancel(order_service, mocker):
    spy = mocker.spy(order_service.orders, "save")
    await order_service.cancel(order.id)
    spy.assert_called_once()
```
Why: it passes with a wrong status and breaks on any refactor.

Good:
```python
async def test_paid_order_cannot_be_cancelled(order_service, make_order):
    order = await make_order(status=OrderStatus.PAID)
    with pytest.raises(OrderAlreadyPaid):
        await order_service.cancel(order.id)
```

### R-PYS-TEST-FIRST - behaviour, not fixture values

Bad:
```python
def total_with_discount(cart: Cart) -> int:
    if cart.id == "cart-123":          # the fixture's id
        return 900
    return sum(i.price for i in cart.items)
```
Why: green tests, broken rule; the next real cart gets no discount.

Good:
```python
def total_with_discount(cart: Cart, rules: DiscountRules) -> int:
    subtotal = sum(i.price * i.qty for i in cart.items)
    return subtotal - rules.discount_for(subtotal)
```

### R-PYS-TEST-NO-SKIP - wait for conditions

Bad:
```python
await worker.start()
await asyncio.sleep(2)
assert await repo.status(id) == "sent"
```
Why: slow on a fast machine, flaky on a slow one.

Good:
```python
await worker.start()
await wait_until(lambda: repo.status(id) == "sent", timeout=5)   # polls a condition, fails on timeout
```
