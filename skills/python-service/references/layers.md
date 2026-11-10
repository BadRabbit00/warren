# Layers and naming - examples

### R-PYS-ROUTER - HTTP only in the router

Bad:
```python
@router.post("/orders")
async def create_order(body: OrderCreate, session: SessionDep) -> OrderRead:
    if await session.scalar(select(exists().where(Order.number == body.number))):
        raise HTTPException(409, "exists")
    order = Order(**body.model_dump())
    session.add(order)
    await session.commit()
    return OrderRead.model_validate(order)
```
Why: the rule cannot be reused from a worker or CLI and is testable only through HTTP.

Good:
```python
@router.post("", response_model=OrderRead, status_code=201)
async def create_order(body: OrderCreate, user: ManagerDep, service: OrderServiceDep) -> OrderRead:
    return OrderRead.model_validate(await service.create(body, actor_id=user.id))
```

### R-PYS-SERVICE - domain errors, not HTTP

Bad:
```python
class OrderService:
    async def cancel(self, order_id: UUID) -> None:
        order = await self.orders.get(order_id)
        if order.status == OrderStatus.PAID:
            raise HTTPException(status_code=409, detail="paid")
```
Why: the service depends on FastAPI; a Celery task calling it gets an HTTP exception.

Good:
```python
class OrderService:
    async def cancel(self, order_id: UUID) -> None:
        order = await self.orders.get(order_id)
        if order.status == OrderStatus.PAID:
            raise OrderAlreadyPaid(order_id)   # ConflictError subclass, mapped to 409 in api/errors.py
        order.status = OrderStatus.CANCELLED
        await self.session.commit()
```

### R-PYS-ERRORS-MAPPED - one place turns domain errors into HTTP

Bad:
```python
@router.post("/{order_id}/cancel")
async def cancel(order_id: UUID, service: OrderServiceDep) -> None:
    try:
        await service.cancel(order_id)
    except OrderAlreadyPaid:
        raise HTTPException(409, "paid")
```
Why: every route repeats the mapping and the formats drift.

Good:
```python
# api/errors.py
@app.exception_handler(ConflictError)
async def conflict_handler(_: Request, err: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(err), "code": err.code})
```

### R-PYS-NO-FANATISM - no layers without work

Bad:
```python
class OrderManager:
    def __init__(self, service: OrderService) -> None:
        self.service = service
    async def get(self, order_id: UUID) -> Order:
        return await self.service.get(order_id)   # adds nothing
```
Why: one more hop to read and change, with no logic in it.

Good:
```python
# the router calls OrderService directly; a new layer appears only when it carries a rule
```

### R-PYS-NAMING - names by entity and layer

Bad:
```python
# app/utils.py, app/helpers/order_helper.py
class OrderSchema(BaseModel): ...
class OrderRepo: ...
```
Why: `utils` collects unrelated code; short or mixed suffixes make search and imports unpredictable.

Good:
```python
# app/services/order_service.py, app/repositories/order_repository.py
class OrderRead(BaseModel): ...
class OrderRepository: ...
```
