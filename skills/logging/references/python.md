# Logging templates: Python (structlog)

Copy-ready templates for one service. The module is per service (`app/core/logging.py`), copied with the service, never shared as a library (D12). Rules and levels: `../SKILL.md`. Requires Python 3.11+ (3.12+ in the project) and `structlog>=25.5.0` (`QUAL_NAME` exists since 25.5.0; latest release in the research is 26.1.0). A new dependency is reported to the orchestrator, not added.

Source marks used below:
- (R) stated in the research `docs/temp/logging/research-wf_6b111f8e-0e4.json`, structlog 26.1.0 docs.
- (U) NOT from the research: general knowledge, verify against the installed version before relying on it.

## Contents

1. [Config fields the module needs](#1-config-fields-the-module-needs)
2. [Shared module `app/core/logging.py`](#2-shared-module-appcoreloggingpy)
3. [Request id and startup](#3-request-id-and-startup)
4. [Boundary logging: decorator](#4-boundary-logging-decorator)
5. [External calls at DEBUG: HTTP and SQL](#5-external-calls-at-debug-http-and-sql)
6. [Levels in use: entity change, branch, INFO, WARNING, ERROR](#6-levels-in-use)
7. [PANIC: global hooks](#7-panic-global-hooks)
8. [Tests](#8-tests)

## 1. Config fields the module needs

The logging module reads settings only from the config module (`core/config.py`); nothing else calls `os.getenv`. Add these fields to the existing `Settings` and to `.env.example` in the same change (R-PYS-CONFIG).

```python
# app/core/config.py (excerpt: only the fields logging needs)
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORDERS_")  # service prefix

    log_level: str  # DEBUG | INFO | WARNING | ERROR | PANIC  (LOG_LEVEL with the prefix)
    log_max_value_len: int  # truncation limit; the number comes from docs/POLICY.md, no default here
```

`.env.example`: `ORDERS_LOG_LEVEL=INFO` and `ORDERS_LOG_MAX_VALUE_LEN=<value from POLICY>`. The limit has no default in code: a missing value fails at startup like any required setting.

## 2. Shared module `app/core/logging.py`

What it gives, all from processors, never from hand-written text:

| Field | Source |
|---|---|
| `timestamp` | `TimeStamper(fmt="iso", utc=True, key="timestamp")`, ends with `Z` (R) |
| `level` | `add_log_level`, renamed to `DEBUG/INFO/WARNING/ERROR/PANIC` (`critical` is PANIC) |
| `event` | structlog's own key |
| `module`, `func`, `file`, `line` | `CallsiteParameterAdder` with `MODULE, FUNC_NAME, LINENO, PATHNAME, QUAL_NAME` (R), renamed |
| `request_id` | `merge_contextvars` (R) |
| `trace_id`, `span_id` | OpenTelemetry processor (the structlog docs show this pattern for `trace_id`, R) |
| `exception` | `dict_tracebacks` in JSON, console formatting in dev (R) |

`func` is built as `<module>.<QUAL_NAME>`, for example `order_service.OrderService.cancel`. `MODULE` is the short module name. For the full import path (`app.services.order_service.OrderService.cancel`) require `structlog>=26.1.0` and add `CallsiteParameter.QUAL_MODULE` (added in 26.1.0, R); use `qual_module` in place of `module` below.

```python
"""Shared logging setup for this service: structlog, canonical fields, masking, PANIC hooks."""

import asyncio
import dataclasses
import logging
import os
import sys
import threading
from collections.abc import Callable, MutableMapping
from types import TracebackType
from typing import Any

import structlog
from opentelemetry import trace
from structlog.contextvars import merge_contextvars
from structlog.processors import (
    CallsiteParameter,
    CallsiteParameterAdder,
    JSONRenderer,
    TimeStamper,
    dict_tracebacks,
)
from structlog.typing import EventDict, Processor, WrappedLogger

from app.core.config import settings

MASK = "***"

# Secrets: masked at every level, DEBUG included. Substring match on the lower-cased key.
SECRET_KEYS = ("password", "passwd", "secret", "token", "api_key", "apikey", "authorization", "cookie", "private_key")
# Personal data: full at DEBUG only, masked at INFO and above. Adapt the list to the service.
PERSONAL_KEYS = ("email", "phone", "first_name", "last_name", "full_name", "address", "birth", "passport", "iin")

_LEVEL_NAMES = {
    "debug": "DEBUG",
    "info": "INFO",
    "warn": "WARNING",
    "warning": "WARNING",
    "error": "ERROR",
    "critical": "PANIC",
    "fatal": "PANIC",
}
_STDLIB_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "PANIC": 50}  # PANIC is CRITICAL


def _level_name(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    event_dict["level"] = _LEVEL_NAMES[str(event_dict["level"]).lower()]
    return event_dict


def _canonical_callsite(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Rename the callsite keys to module/func/file/line.

    A caller that logs on behalf of another function (the `traced` decorator) passes
    `_callsite={...}`; it wins over the frame lookup, which would point at the wrapper.
    """
    override = event_dict.pop("_callsite", None)
    module = event_dict.pop("module", "")
    qual_name = event_dict.pop("qual_name", "")
    event_dict.pop("func_name", None)
    event_dict["module"] = module
    event_dict["func"] = f"{module}.{qual_name}" if module else qual_name
    event_dict["file"] = event_dict.pop("pathname", "")
    event_dict["line"] = event_dict.pop("lineno", 0)
    if override:
        event_dict.update(override)
    return event_dict


def _trace_context(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Add trace_id and span_id of the current OpenTelemetry span (pattern from the structlog docs, R)."""
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:  # (U) SpanContext.is_valid
        event_dict["trace_id"] = format(ctx.trace_id, "032x")  # (R)
        event_dict["span_id"] = format(ctx.span_id, "016x")  # (U) width 16 hex digits for 64-bit span id
    return event_dict


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[:limit]}...<truncated {len(text) - limit}>"


def _sanitize(value: Any, key: str, *, show_personal: bool, limit: int) -> Any:
    lowered = key.lower()
    if any(part in lowered for part in SECRET_KEYS):
        return MASK
    if not show_personal and any(part in lowered for part in PERSONAL_KEYS):
        return MASK
    if hasattr(value, "model_dump"):  # pydantic v2 model: walk the fields, never repr() the object
        value = value.model_dump()
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = dataclasses.asdict(value)
    if isinstance(value, dict):
        return {str(k): _sanitize(v, str(k), show_personal=show_personal, limit=limit) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_sanitize(v, key, show_personal=show_personal, limit=limit) for v in value]
    if isinstance(value, bool | int | float) or value is None:
        return value
    if isinstance(value, str):
        return _truncate(value, limit)
    return _truncate(repr(value), limit)


def _sanitizer(*, show_personal: bool, limit: int) -> Processor:
    """One central processor: secrets always `***`, personal data `***` unless DEBUG, long values cut."""

    def sanitize(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
        for key, value in list(event_dict.items()):
            if key in ("exc_info", "exception", "timestamp", "level", "event"):
                continue
            event_dict[key] = _sanitize(value, key, show_personal=show_personal, limit=limit)
        return event_dict

    return sanitize


def configure_logging() -> None:
    """Call once at process start (app factory, worker entry point)."""
    level_name = settings.log_level.upper()
    show_personal = level_name == "DEBUG"
    json_output = not sys.stderr.isatty()  # terminal: console; otherwise JSON (R, structlog best practices)

    processors: list[Processor] = [
        merge_contextvars,  # first in the chain (R)
        structlog.processors.add_log_level,
        _level_name,
        CallsiteParameterAdder(
            {
                CallsiteParameter.MODULE,
                CallsiteParameter.FUNC_NAME,
                CallsiteParameter.LINENO,
                CallsiteParameter.PATHNAME,
                CallsiteParameter.QUAL_NAME,
            },
            # (U) additional_ignores takes module names whose frames are skipped; check the 26.1.0 API page
            additional_ignores=[__name__],
        ),
        _canonical_callsite,
        TimeStamper(fmt="iso", utc=True, key="timestamp"),
        _trace_context,
        _sanitizer(show_personal=show_personal, limit=settings.log_max_value_len),
    ]
    if json_output:
        processors += [dict_tracebacks, JSONRenderer(default=repr)]  # dumps kwargs pass through (R)
    else:
        processors += [structlog.dev.ConsoleRenderer()]  # handles exc_info itself (R)

    structlog.configure(
        processors=processors,
        # (U) make_filtering_bound_logger drops events below the level before any processor runs
        wrapper_class=structlog.make_filtering_bound_logger(_STDLIB_LEVELS[level_name]),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
```

Notes:
- The sanitizer runs before the renderers, so a secret never reaches the output. `exc_info` is left alone; do not put secrets into exception messages.
- `PANIC` is structlog's `critical` (D3): call `log.critical(...)`.
- Substring match over-masks (`token_count`); rename the field or narrow the tuple per service. Keep the tuples in this one module.
- Per-module level overrides (D6) are not in the research and not in this template; add them only when a task asks.

## 3. Request id and startup

`request_id` comes from contextvars, bound once per request; every later line carries it without passing it around. `clear_contextvars` first, as the docs say (R).

```python
# app/api/middleware.py
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from structlog.contextvars import bind_contextvars, clear_contextvars


def install_request_id(app: FastAPI) -> None:
    # (U) FastAPI/Starlette @app.middleware("http") signature
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        clear_contextvars()
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response
```

Startup (INFO, once, no secrets): log the effective config summary.

```python
# app/main.py
import structlog

from app.core.config import settings
from app.core.logging import configure_logging, install_panic_hooks

configure_logging()
install_panic_hooks()
log = structlog.get_logger(__name__)
log.info("service.started", log_level=settings.log_level)  # only non-secret settings
```

For Celery tasks and bot handlers call `clear_contextvars()` and `bind_contextvars(request_id=...)` at the task start with the id from the task headers or a new one.

## 4. Boundary logging: decorator

One decorator for sync and async functions: entry with arguments, exit with result and `duration_ms` at DEBUG; exceptions at DEBUG with the stack and re-raised (the ERROR line is written once, where the error is handled, not here). Put it on service methods and repository calls; do not put it inside loops. Secrets in `args`/`result` are masked by the central sanitizer, because they travel as keyed dicts.

```python
# app/core/logging.py (continued)
import functools
import inspect
import time
from collections.abc import Awaitable
from types import FunctionType
from typing import cast


def traced[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """Log entry (args) and exit (result, duration_ms) at DEBUG, and any exception."""
    log = structlog.get_logger(fn.__module__)
    signature = inspect.signature(fn)
    callsite = {
        "module": fn.__module__,
        "func": f"{fn.__module__}.{fn.__qualname__}",
        "file": inspect.getsourcefile(fn) or "",
        "line": cast(FunctionType, fn).__code__.co_firstlineno,
    }

    def entry(args: tuple[Any, ...], kwargs: dict[str, Any]) -> float:
        bound = signature.bind_partial(*args, **kwargs).arguments
        shown = {k: v for k, v in bound.items() if k not in ("self", "cls")}
        log.debug("enter", args=shown, _callsite=callsite)
        return time.perf_counter()

    def leave(started: float, result: Any) -> None:
        log.debug("exit", result=result, duration_ms=round((time.perf_counter() - started) * 1000, 3), _callsite=callsite)

    def failed(started: float) -> None:
        log.debug(
            "raised", exc_info=True, duration_ms=round((time.perf_counter() - started) * 1000, 3), _callsite=callsite
        )

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            started = entry(args, kwargs)
            try:
                result = await cast(Callable[P, Awaitable[Any]], fn)(*args, **kwargs)
            except Exception:
                failed(started)
                raise
            leave(started, result)
            return result

        return cast(Callable[P, R], async_wrapper)

    @functools.wraps(fn)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        started = entry(args, kwargs)
        try:
            result = fn(*args, **kwargs)
        except Exception:
            failed(started)
            raise
        leave(started, result)
        return result

    return sync_wrapper
```

Use:

```python
class OrderService:
    @traced
    async def cancel(self, order_id: UUID, reason: str) -> Order:
        ...
```

The lines carry `func=app.services.order_service.OrderService.cancel` from the decorator's `_callsite`, not the wrapper's frame. The `@traced` call costs a signature bind per call: use it at boundaries (service, repository, client methods), not on hot inner helpers. If OpenTelemetry spans are used (see `opentelemetry.md`), the span replaces the entry/exit pair for that function; do not stack both.

## 5. External calls at DEBUG: HTTP and SQL

### HTTP client (httpx)

The research lists `opentelemetry-instrumentation-httpx` (`HTTPXClientInstrumentor().instrument()`) for spans (R). It does not cover httpx event hooks: the hook API below is (U), verify against the installed httpx.

```python
# app/clients/logging_hooks.py
import time

import httpx
import structlog

log = structlog.get_logger(__name__)


async def log_request(request: httpx.Request) -> None:
    request.extensions["started"] = time.perf_counter()  # (U) Request.extensions is a mutable dict
    log.debug("http.request", method=request.method, url=str(request.url.copy_with(query=None)),
              headers=dict(request.headers))  # query dropped: it may carry tokens; header values masked by key


async def log_response(response: httpx.Response) -> None:
    started = response.request.extensions.get("started", time.perf_counter())
    log.debug("http.response", method=response.request.method, url=str(response.request.url.copy_with(query=None)),
              status=response.status_code, duration_ms=round((time.perf_counter() - started) * 1000, 3))


def logged_client(**kwargs: object) -> httpx.AsyncClient:
    """Every client has a timeout (POLICY); pass it in kwargs."""
    return httpx.AsyncClient(event_hooks={"request": [log_request], "response": [log_response]}, **kwargs)  # type: ignore[arg-type]  # kwargs are forwarded as given
```

Response bodies are not logged by default (large, may hold personal data). If a task needs them, read the body in the hook (`await response.aread()`) and log it as `body=` so the sanitizer truncates it. A slow call over the POLICY threshold is a WARNING, written by the caller that knows the threshold.

### SQL with parameters (SQLAlchemy)

(U) The SQLAlchemy event names and signatures are not from the research; verify against the installed SQLAlchemy 2.x. Attach to `engine.sync_engine` for an async engine. Parameters come from the compiled statement as a named dict, so the sanitizer can mask `password` and similar columns by name; positional DBAPI tuples cannot be masked and are never logged.

```python
# app/core/database.py (excerpt)
import time
from typing import Any

import structlog
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine

log = structlog.get_logger("app.core.database")


def log_sql(engine: Engine) -> None:
    """Pass `async_engine.sync_engine`. Call only when LOG_LEVEL is DEBUG."""

    @event.listens_for(engine, "before_cursor_execute")
    def before(conn: Connection, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        conn.info.setdefault("query_started", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def after(conn: Connection, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        started = conn.info["query_started"].pop()
        compiled = getattr(context, "compiled", None)
        log.debug(
            "sql.execute",
            statement=statement,
            params=getattr(compiled, "params", None),  # named dict or None
            executemany=executemany,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )
```

The `statement` line has the callsite of the listener, not of your repository method; the repository's own `@traced` line gives the business callsite. Set `statement` in the SQLAlchemy logger off (`echo=False`) so the same query is not printed twice by the standard `logging` module.

## 6. Levels in use

Entity change (before → after) at DEBUG: snapshot the fields before the change and log both after it. The sanitizer masks by key, so pass dicts, not model objects with secrets inside.

```python
@traced
async def change_status(self, order_id: UUID, new_status: OrderStatus) -> Order:
    order = await self._orders.get(order_id)
    before = {"status": order.status, "total": order.total}
    order.status = new_status
    await self._orders.save(order)
    self._log.debug("order.updated", order_id=str(order_id), before=before, after={"status": order.status, "total": order.total})
    self._log.info("order.status_changed", order_id=str(order_id), status=new_status)  # business event: one line, not in a loop
    return order
```

Branch decision at DEBUG: log the inputs that decided the branch and the branch taken, once per decision.

```python
if order.paid_at is None:
    self._log.debug("cancel.branch", branch="unpaid_no_refund", paid_at=None, status=order.status)
else:
    self._log.debug("cancel.branch", branch="paid_refund", paid_at=order.paid_at, amount=order.total)
```

WARNING (works, needs attention): a retry, a fallback, a slow call, a deprecated path.

```python
log.warning("payments.retry", attempt=attempt, max_attempts=max_attempts, delay_s=delay, reason=type(err).__name__)
```

ERROR (failed, the code goes on): once, where the error is handled, with the stack and context. Do not also log it at the places it passed through.

```python
try:
    await self._mail.send(order.customer_email, template)
except MailError:
    log.exception("order.mail_failed", order_id=str(order.id))  # exception() = ERROR + exc_info
```

`log.exception` renders the stack through `dict_tracebacks` (JSON) or the console renderer. Never `log.error(str(err))`: the stack is lost.

## 7. PANIC: global hooks

Unrecoverable: log at PANIC with the message, full stack and context, flush, then exit non-zero. Hooks are installed once at startup (section 3). The exception types and calls are standard library (U); the `critical` to PANIC mapping is in section 2.

```python
# app/core/logging.py (continued)
_panic_log = structlog.get_logger("panic")


def _panic(message: str, exc_info: tuple[type[BaseException], BaseException, TracebackType | None], **context: Any) -> None:
    _panic_log.critical(message, exc_info=exc_info, **context)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(1)  # skip the failing runtime's cleanup: the process state is unknown


def install_panic_hooks() -> None:
    """Uncaught exceptions in the main thread and in threads."""

    def excepthook(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
        _panic("uncaught.exception", (exc_type, exc, tb))

    def thread_hook(args: threading.ExceptHookArgs) -> None:  # (U) threading.excepthook
        if args.exc_value is not None:
            _panic("uncaught.thread_exception", (args.exc_type, args.exc_value, args.exc_traceback),
                   thread=getattr(args.thread, "name", None))

    sys.excepthook = excepthook
    threading.excepthook = thread_hook


def install_loop_panic_handler(loop: asyncio.AbstractEventLoop) -> None:
    """Call inside the running loop (for example in the FastAPI lifespan): `install_loop_panic_handler(asyncio.get_running_loop())`."""

    def handler(_: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:  # (U) loop.set_exception_handler
        exc = context.get("exception")
        if isinstance(exc, BaseException):
            _panic("uncaught.async_exception", (type(exc), exc, exc.__traceback__), asyncio_message=context.get("message"))
        _panic_log.critical("uncaught.async_error", asyncio_message=context.get("message"))
        sys.stdout.flush()
        os._exit(1)

    loop.set_exception_handler(handler)
```

Decide per service whether an unretrieved task exception should kill the process: D3 says it does. A handled exception (caught and logged at ERROR) never reaches these hooks.

## 8. Tests

Tests run with `LOG_LEVEL=DEBUG` (prefixed name in the service, for example `ORDERS_LOG_LEVEL=DEBUG`), set in the test environment file read by the config module, not by `os.environ` edits in test bodies. At DEBUG the boundary lines, SQL and HTTP lines are produced, so a failing test shows the full path, and personal data appears unmasked there; test data must be synthetic. Secrets stay `***` in tests too.

To assert on log output use `structlog.testing.capture_logs()` (U, verify; it captures before the renderers, so it sees events but not the sanitizer's masking). Test the masking by calling the processor function directly.
