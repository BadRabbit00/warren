---
paths:
  - "**/*.py"
---

# Python

## Scope

The full rule set for coding agents is the skill `python-service`. Id map: `R-PY-X` = `R-PYS-X` (same rule), except `R-PY-ERRORS` = `R-PYS-EXCEPT`.

Python 3.12+ code: FastAPI services, workers, scripts. Layers, DB, and tests have their own rules; this is the language part. `language-reviewer` checks it in depth.

Checks: `pytest` (the task tests, then the touched package); `ruff check`; `ruff format --check`; `mypy --strict`.

## Rules

- R-PY-TYPES: every function is annotated; mypy runs in `strict` mode with the pydantic plugin. No `Any` for business data; external input is parsed into a model at the boundary. Several return values → `@dataclass(frozen=True)`, not a tuple.
- R-PY-ASYNC: inside `async def` nothing blocks: no `requests`, `time.sleep`, sync DB drivers, or large file reads (`httpx.AsyncClient`, `asyncio.sleep`, `asyncio.to_thread`). Concurrency through `asyncio.TaskGroup`; a created task is awaited or owned.
- R-PY-ERRORS: no bare `except:` and no `except Exception: pass`. Catch the narrowest error, re-raise as a domain error with `raise … from err`. Never return `None` to signal failure when the caller cannot tell why.
- R-PY-DEFAULTS: no mutable default arguments (`def f(x: list = [])`); pydantic fields use `Field(default_factory=list)`.
- R-PY-PYDANTIC: pydantic v2 API only: `model_validate`, `model_dump`, `ConfigDict(from_attributes=True)`, `field_validator`. Schemas are `OrderCreate` / `OrderUpdate` / `OrderRead`.
- R-PY-TIME: datetimes are timezone-aware (`datetime.now(UTC)`); stored as `timestamptz`. No naive `datetime.now()` / `utcnow()`.
- R-PY-LOGGING: `structlog.get_logger(__name__)`; values go as key-value pairs, not formatted into the message. No `print`. Secrets never; personal data only at DEBUG, masked at INFO and above (skill `logging`).
- R-PY-IMPORTS: absolute imports from the service root (`from app.services.order_service import …`); no imports inside functions to dodge a cycle; no star imports.
- R-PY-SUBPROCESS: `subprocess.run([...], check=True)` with a list, never `shell=True` with any interpolated value; `pathlib.Path` for paths.

## Examples

### R-PY-DEFAULTS — shared mutable default

Bad:
```python
def add_tag(order_id: str, tags: list[str] = []) -> list[str]:
    tags.append(order_id)
    return tags
```
Why: the same list is shared by every call; tags from one order leak into the next.

Good:
```python
def add_tag(order_id: str, tags: list[str] | None = None) -> list[str]:
    result = list(tags or [])
    result.append(order_id)
    return result
```

### R-PY-TIME — aware datetimes only

Bad:
```python
expires_at = datetime.utcnow() + timedelta(minutes=15)   # naive, deprecated
```
Why: comparing it with an aware value raises `TypeError`; stored without zone it shifts by the server's offset.

Good:
```python
expires_at = datetime.now(UTC) + timedelta(minutes=15)
```
