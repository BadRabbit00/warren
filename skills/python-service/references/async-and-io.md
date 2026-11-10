# Language, async, outgoing calls, workers - examples

### R-PYS-ASYNC - nothing blocks the loop

Bad:
```python
async def fetch_rate(code: str) -> Decimal:
    resp = requests.get(f"{BASE}/rates/{code}")   # blocks every request of this process
    time.sleep(1)
    return Decimal(resp.json()["rate"])
```
Why: one slow call stalls all concurrent requests of the replica.

Good:
```python
async def fetch_rate(client: httpx.AsyncClient, code: str) -> Decimal:
    resp = await client.get(f"/rates/{code}")
    resp.raise_for_status()
    return RateResponse.model_validate(resp.json()).rate
```

### R-PYS-ASYNC - owned tasks

Bad:
```python
asyncio.create_task(send_all(users))   # nobody awaits it; errors vanish
```
Why: lost exceptions and half-sent work on shutdown.

Good:
```python
async with asyncio.TaskGroup() as tg:
    for user in users:
        tg.create_task(send(user))
```

### R-PYS-EXCEPT - narrow catch, domain error

Bad:
```python
try:
    return await client.charge(order)
except Exception:
    pass
```
Why: failures vanish; the caller cannot tell "not charged" from "charged".

Good:
```python
try:
    return await client.charge(order)
except httpx.TimeoutException as err:
    raise PaymentUnavailable(order.id) from err
```

### R-PYS-TYPES - model at the boundary, no Any

Bad:
```python
def parse(data: dict[str, Any]) -> tuple[Any, Any, Any]:
    return data["id"], data["total"], data["status"]
```
Why: a missing key or a wrong type surfaces deep in the logic; callers unpack by position.

Good:
```python
class PaymentEvent(BaseModel):
    id: UUID
    total_minor: int
    status: PaymentStatus

def parse(data: bytes) -> PaymentEvent:
    return PaymentEvent.model_validate_json(data)
```

### R-PYS-DEFAULTS - shared mutable default

Bad:
```python
def add_tag(order_id: str, tags: list[str] = []) -> list[str]:
    tags.append(order_id)
    return tags
```
Why: the same list is shared by every call.

Good:
```python
def add_tag(order_id: str, tags: list[str] | None = None) -> list[str]:
    result = list(tags or [])
    result.append(order_id)
    return result
```

### R-PYS-TIME - aware datetimes only

Bad:
```python
expires_at = datetime.utcnow() + timedelta(minutes=15)   # naive, deprecated
```
Why: comparing with an aware value raises `TypeError`; stored without zone it shifts by the server offset.

Good:
```python
expires_at = datetime.now(UTC) + timedelta(minutes=15)
```

### R-PYS-SUBPROCESS - no shell interpolation

Bad:
```python
subprocess.run(f"convert {path} out.png", shell=True)
```
Why: a file name with `;` runs arbitrary commands.

Good:
```python
subprocess.run(["convert", str(path), "out.png"], check=True, timeout=30)
```

### R-PYS-OUTGOING - timeout and bounded retries

Bad:
```python
resp = await httpx.AsyncClient().post(url, json=payload)   # default timeout, new client per call, ad-hoc retry
```
Why: a hung provider holds the request; retries happen by accident or never.

Good:
```python
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

client = httpx.AsyncClient(base_url=cfg.payment_url, timeout=httpx.Timeout(cfg.payment_timeout_s))

@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(),
       retry=retry_if_exception_type(httpx.TransportError))
async def get_status(payment_id: str) -> PaymentStatus: ...   # idempotent GET only
```
Use the project's retry helper; if `tenacity` is not in `pyproject.toml`, report it as a new dependency. A POST without an idempotency key is not retried. Timeout and attempts come from `docs/POLICY.md` through config.

### R-PYS-WORKERS - parallel-safe, repeatable tasks

Bad:
```python
@app.task
def send_invoice(order: dict) -> None:
    if not order["invoice_sent"]:        # stale copy; two workers both send
        mailer.send(order)
        orders.mark_sent(order["id"])
```
Why: a serialized object is stale, and a retry or a second worker sends twice.

Good:
```python
@app.task(bind=True, acks_late=True, max_retries=3)
def send_invoice(self, order_id: str) -> None:
    # inside: UPDATE ... WHERE invoice_sent_at IS NULL RETURNING id, then send
    asyncio.run(invoice_service.send_once(UUID(order_id)))
```

### R-PYS-STATELESS - nothing kept in the process

Bad:
```python
_attempts: dict[str, int] = {}

async def check_login_rate(ip: str) -> None:
    _attempts[ip] = _attempts.get(ip, 0) + 1
    if _attempts[ip] > 5:
        raise TooManyAttempts()
```
Why: with three replicas the limit is three times higher, and it resets on deploy.

Good:
```python
async def check_login_rate(redis: Redis, ip: str, limit: int, window_s: int) -> None:
    key = f"auth:login:{ip}"
    async with redis.pipeline(transaction=True) as pipe:   # counter and TTL set atomically
        pipe.incr(key)
        pipe.expire(key, window_s, nx=True)
        count, _ = await pipe.execute()
    if count > limit:
        raise TooManyAttempts()
```
