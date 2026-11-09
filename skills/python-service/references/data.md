# Data access - examples

### R-PYS-PAGINATE-IN-QUERY - page in SQL

Bad:
```python
async def list_orders(self, page: int, size: int) -> list[Order]:
    rows = (await self.session.scalars(select(Order))).all()   # whole table
    return rows[(page - 1) * size : page * size]
```
Why: every page request loads the whole table into the process; it gets heavier every day.

Good:
```python
async def list_orders(self, after: UUID | None, limit: int) -> list[Order]:
    stmt = select(Order).order_by(Order.id).limit(limit)
    if after is not None:
        stmt = stmt.where(Order.id > after)
    return list((await self.session.scalars(stmt)).all())
```

### R-PYS-NO-N-PLUS-1 - load relations in one go

Bad:
```python
orders = (await session.scalars(select(Order).where(Order.user_id == uid))).all()
for order in orders:
    order.items = (await session.scalars(select(Item).where(Item.order_id == order.id))).all()
```
Why: 100 orders mean 101 queries.

Good:
```python
stmt = select(Order).where(Order.user_id == uid).options(selectinload(Order.items)).limit(limit)
orders = (await session.scalars(stmt)).all()
```

### R-PYS-NO-STRING-SQL - no string-built SQL

Bad:
```python
await session.execute(text(f"SELECT * FROM orders WHERE status = '{status}' ORDER BY {sort}"))
```
Why: SQL injection through `status` and `sort`; column typos surface only at runtime.

Good:
```python
SORTABLE = {"created_at": Order.created_at, "total": Order.total_minor}
stmt = select(Order).where(Order.status == status).order_by(SORTABLE.get(sort, Order.created_at).desc())
```

### R-PYS-ORM-ONLY - raw SQL is an exception with a reason

Bad:
```python
async def totals(self) -> list[Row]:
    return (await self.session.execute(text("SELECT user_id, sum(total) FROM orders GROUP BY 1"))).all()
```
Why: no reason given, and `select(func.sum(...)).group_by(...)` does the job.

Good:
```python
async def tree(self, root: UUID) -> list[Row]:
    # why not ORM: recursive CTE over the category tree, measured 40x faster than loop-loading
    stmt = text("WITH RECURSIVE t AS (...) SELECT * FROM t WHERE root_id = :root")
    return (await self.session.execute(stmt, {"root": root})).all()
```

### R-PYS-TX-IN-SERVICE - the service owns the transaction

Bad:
```python
class OrderRepository:
    async def add(self, order: Order) -> None:
        self.session.add(order)
        await self.session.commit()          # the caller cannot group two writes
        await self.mailer.send(order.email)  # network call in the middle of a scenario
```
Why: two repositories cannot take part in one atomic scenario; a failure after the email leaves a mess.

Good:
```python
class OrderService:
    async def create(self, body: OrderCreate) -> Order:
        order = await self.orders.add(Order(**body.model_dump()))   # add + flush only
        await self.stock.reserve(order)
        await self.session.commit()
        await self.mailer.send(order.email)                         # after the commit
        return order
```

### R-PYS-RACES - atomic state change

Bad:
```python
order = await repo.get(order_id)
if order.status == OrderStatus.NEW:      # two requests both see NEW
    order.status = OrderStatus.PAID
    await session.commit()
```
Why: two concurrent payments both pass the check; the order is paid twice.

Good:
```python
paid = await session.scalar(
    update(Order)
    .where(Order.id == order_id, Order.status == OrderStatus.NEW)
    .values(status=OrderStatus.PAID)
    .returning(Order.id)
)
if paid is None:
    raise OrderNotPayable(order_id)
await session.commit()
```

### R-PYS-MIGRATIONS - schema only through Alembic

Bad:
```python
@app.on_event("startup")
async def init() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```
Why: no history, no rollback, replicas race each other, production drifts from the models.

Good:
```text
alembic revision --autogenerate -m "add order.number"
# read the generated file, remove noise, one logical change, then:
alembic upgrade head      # against the test DB only
```

### R-PYS-STORES - Redis is derived data

Bad:
```python
await redis.set(f"order:{order.id}", order.model_dump_json())   # the only copy, no TTL
```
Why: a restart or eviction loses the order.

Good:
```python
await redis.set(f"orders:view:{order.id}", view.model_dump_json(), ex=300)   # rebuildable from PostgreSQL
```
