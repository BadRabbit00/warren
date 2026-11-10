# TypeScript logging templates (pino 10.x)

Copy per service (D12), no cross-service package. Node backend: `src/core/logger.ts`. Browser (React + Vite): `src/core/logger.ts` of the frontend. Canonical fields: `timestamp level event module func file line request_id trace_id span_id` plus `duration_ms args result before after exception`. Levels `DEBUG INFO WARNING ERROR PANIC`; secrets always `***`; personal data masked unless DEBUG; time is UTC ISO 8601 with `Z`.

Facts used (research wf_6b111f8e-0e4, pino 10.4.0 latest on 2026-11-10):
- `pino.stdTimeFunctions.isoTime` is ISO 8601 UTC; `mixin()` runs on every active log call and returns an object synchronously; `redact` takes paths, `*` wildcards, a custom `censor`; `child(bindings)`.
- pino has no caller option; V8 stack API (`Error.captureStackTrace`, `Error.prepareStackTrace`, `CallSite.getFileName/getLineNumber/getFunctionName/getTypeName/getMethodName`) is the way. `pino-caller` 4.0.0 is dev-only: do not use in prod.
- Browser build: `asObject`, `write`, `serialize`, `transmit.send`, `transmit.level`; browser `formatters` support only `level`.

Marked UNVERIFIED (not in the research; check the pino 10 docs before relying on it): `formatters.level` signature and `fatal` as the PANIC label in the Node build, `pino-pretty` (not named in the research, so dev output here is plain JSON), cost of stack capture (not measured), method/class names after Vite minification (need source maps), Node `uncaughtException`/`unhandledRejection` handler behaviour with pino (research: "not verified from docs").

## Node: shared module `src/core/logger.ts`

```ts
import { AsyncLocalStorage } from "node:async_hooks";
import path from "node:path";
import pino from "pino";
import { config } from "./config"; // LOG_LEVEL comes only from the config module

export interface RequestContext {
  request_id: string;
  trace_id?: string;
  span_id?: string;
}
export const requestContext = new AsyncLocalStorage<RequestContext>();

// pino: trace < debug < info < warn < error < fatal. We rename labels, not levels.
const LEVEL_NAMES: Record<string, string> = {
  trace: "DEBUG",
  debug: "DEBUG",
  info: "INFO",
  warn: "WARNING",
  error: "ERROR",
  fatal: "PANIC", // PANIC == pino `fatal`; call logger.fatal(...) only from the global hooks
};

const SECRET_PATHS = [
  "password", "token", "access_token", "refresh_token", "api_key", "secret",
  "authorization", "cookie",
  "*.password", "*.token", "*.access_token", "*.refresh_token", "*.api_key", "*.secret",
  "*.authorization", "*.cookie",
  "headers.authorization", "headers.cookie", "args.*.password", "args.*.token",
  "args.headers.authorization", "args.headers.cookie",
];
// Personal data: full only at DEBUG, masked at INFO and above (D5).
const PERSONAL_PATHS = [
  "email", "phone", "full_name", "address", "*.email", "*.phone", "*.full_name", "*.address",
];

const isDebug = config.logLevel.toLowerCase() === "debug" || config.logLevel.toLowerCase() === "trace";

// Caller helper: file, line, func with class, via the V8 stack trace API.
// Cost: one Error + structured stack per log call. It runs inside mixin(), which pino calls
// only for log calls at enabled levels, so disabled DEBUG calls pay nothing. Not measured.
const SKIP = [`${path.sep}core${path.sep}logger.`, `${path.sep}node_modules${path.sep}pino${path.sep}`, "node:"];

interface Caller { file: string; line: number; func: string; module: string }

function caller(): Caller | undefined {
  const holder: { stack?: NodeJS.CallSite[] } = {};
  const prevPrepare = Error.prepareStackTrace;
  const prevLimit = Error.stackTraceLimit;
  Error.stackTraceLimit = 12;
  Error.prepareStackTrace = (_err, sites) => sites;
  try {
    Error.captureStackTrace(holder, caller);
    const sites = holder.stack as NodeJS.CallSite[] | undefined;
    const site = sites?.find((s) => {
      const f = s.getFileName() ?? "";
      return f !== "" && !SKIP.some((p) => f.includes(p));
    });
    if (!site) return undefined;
    const file = path.relative(process.cwd(), (site.getFileName() ?? "").replace(/^file:\/\//, ""));
    const type = site.getTypeName();
    const fn = site.getFunctionName() ?? site.getMethodName() ?? "<anonymous>";
    return {
      file,
      line: site.getLineNumber() ?? 0,
      func: type && type !== "Object" && type !== "undefined" ? `${type}.${fn}` : fn,
      module: file.replace(/\.[cm]?[jt]sx?$/, "").split(path.sep).join("."),
    };
  } finally {
    Error.prepareStackTrace = prevPrepare;
    Error.stackTraceLimit = prevLimit;
  }
}

export const logger = pino({
  level: config.logLevel, // per-module overrides: child loggers, see below
  // isoTime returns the partial JSON `,"time":"<UTC ISO 8601>"`; rename the key to the canonical `timestamp`.
  timestamp: () => pino.stdTimeFunctions.isoTime().replace('"time"', '"timestamp"'),
  messageKey: "event",
  formatters: {
    level: (label) => ({ level: LEVEL_NAMES[label] ?? label.toUpperCase() }), // UNVERIFIED signature
  },
  redact: {
    paths: isDebug ? SECRET_PATHS : [...SECRET_PATHS, ...PERSONAL_PATHS],
    censor: "***",
  },
  mixin() {
    const ctx = requestContext.getStore();
    return { ...(ctx ?? {}), ...caller() };
  },
});

// Per-module level override (D6): one child per module.
export function moduleLogger(name: string, level?: string): pino.Logger {
  return logger.child({ module: name }, level ? { level } : undefined);
}
```

Notes:
- `isoTime` writes the key `"time"`; the template renames it. Equivalent without string surgery: `timestamp: () => \`,"timestamp":"${new Date().toISOString()}"\`` (partial JSON string; `toISOString()` is UTC with `Z`).
- Trace ids: with OpenTelemetry (see `opentelemetry.md`) `@opentelemetry/instrumentation-pino` adds `trace_id`/`span_id`; without it set them in `requestContext`.
- Dev vs prod: output is JSON in both. Dev reading: pipe through `jq` (`node dist/main.js | jq -c .`); `pino-pretty` is not in the research.
- Tests run at `LOG_LEVEL=debug`.
- `logger.error({ exception: err, event: "payment_failed" })`: pass the error under `exception` and register `serializers: { exception: pino.stdSerializers.err }` if the stack must be in the line (stdSerializers not in the research: UNVERIFIED).

### Request context (Express-style middleware)

```ts
import { randomUUID } from "node:crypto";
import type { NextFunction, Request, Response } from "express";
import { requestContext } from "./logger";

export function requestIdMiddleware(req: Request, _res: Response, next: NextFunction): void {
  const request_id = req.header("x-request-id") ?? randomUUID();
  requestContext.run({ request_id }, next);
}
```

### Boundary wrapper (DEBUG entry/exit/duration)

```ts
import { logger } from "./logger";

export function logged<A extends unknown[], R>(
  name: string,
  fn: (...args: A) => R | Promise<R>,
): (...args: A) => Promise<R> {
  return async (...args: A): Promise<R> => {
    const start = performance.now();
    logger.debug({ args }, `${name}.enter`);
    try {
      const result = await fn(...args);
      logger.debug({ result, duration_ms: performance.now() - start }, `${name}.exit`);
      return result;
    } catch (exception) {
      logger.error({ exception, duration_ms: performance.now() - start }, `${name}.failed`);
      throw exception; // log once where handled; rethrow here only because the caller handles it
    }
  };
}

// Method decorator (TC39 standard decorators, TypeScript 5+):
export function Logged<This, A extends unknown[], R>(
  target: (this: This, ...args: A) => R | Promise<R>,
  context: ClassMethodDecoratorContext<This>,
) {
  const name = String(context.name);
  return function (this: This, ...args: A): Promise<R> {
    const cls = (this as { constructor: { name: string } }).constructor.name;
    return logged(`${cls}.${name}`, target.bind(this))(...args);
  };
}
```

Because `func` comes from the caller helper, set it explicitly in wrapper lines: the stack frame is the wrapper, so pass `{ func: name }` in the object (the `mixin` result is merged first, the call object wins in pino).

Decision: an exception rethrown by `logged` is logged at ERROR here; if a higher layer also logs it, drop the `logger.error` in the wrapper (log once where handled).

### Outgoing HTTP (fetch wrapper)

```ts
import { logger } from "./logger";

export async function loggedFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const start = performance.now();
  const ctxHeaders = { "x-request-id": requestContext.getStore()?.request_id ?? "" };
  logger.debug({ args: { method: init.method ?? "GET", url, headers: { ...init.headers, ...ctxHeaders } } }, "http.request");
  try {
    const res = await fetch(url, { ...init, headers: { ...init.headers, ...ctxHeaders }, signal: init.signal ?? AbortSignal.timeout(10_000) });
    logger.debug({ result: { status: res.status }, duration_ms: performance.now() - start }, "http.response");
    return res;
  } catch (exception) {
    logger.warn({ exception, args: { url }, duration_ms: performance.now() - start }, "http.failed");
    throw exception;
  }
}
```

Timeout and retries come from `docs/POLICY.md`; 10 s above is a placeholder. The headers are logged under `args.headers`; `SECRET_PATHS` above already lists `args.headers.authorization` and `args.headers.cookie`.

### Global hooks: PANIC

```ts
import { logger } from "./logger";

function panic(event: string, exception: unknown): never {
  logger.fatal({ exception, stack: exception instanceof Error ? exception.stack : undefined }, event);
  // flush, then exit; pino writes to stdout synchronously by default, flushSync covers async destinations
  logger.flush?.();
  process.exit(1);
}

process.on("uncaughtException", (err) => panic("uncaught_exception", err));
process.on("unhandledRejection", (reason) => panic("unhandled_rejection", reason));
```

## Browser: `src/core/logger.ts` (React + Vite)

```ts
import pino from "pino";

const SECRET_KEYS = /pass(word)?|token|secret|api[_-]?key|authorization|cookie/i;
const PERSONAL_KEYS = /email|phone|full_?name|address/i;
const debug = import.meta.env.VITE_LOG_LEVEL === "debug"; // config module reads import.meta.env

function mask(value: unknown, depth = 0): unknown {
  if (depth > 5 || value === null || typeof value !== "object") return value;
  const out: Record<string, unknown> = Array.isArray(value) ? ([] as unknown as Record<string, unknown>) : {};
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    out[k] = SECRET_KEYS.test(k) || (!debug && PERSONAL_KEYS.test(k)) ? "***" : mask(v, depth + 1);
  }
  return out;
}

const LEVELS: Record<string, string> = { trace: "DEBUG", debug: "DEBUG", info: "INFO", warn: "WARNING", error: "ERROR", fatal: "PANIC" };

export const logger = pino({
  level: import.meta.env.VITE_LOG_LEVEL ?? "info",
  browser: {
    asObject: true,
    formatters: { level: (label) => ({ level: LEVELS[label] ?? label.toUpperCase() }) }, // browser formatters: only `level`
    serialize: true,
    transmit: {
      level: "warn", // WARNING and above go to the backend
      send: (level, logEvent) => {
        const m = logEvent.messages;
        const body = {
          timestamp: new Date(logEvent.ts).toISOString(),
          level: LEVELS[level] ?? level.toUpperCase(),
          event: typeof m[m.length - 1] === "string" ? m[m.length - 1] : "client_log",
          ...(mask(Object.assign({}, ...logEvent.bindings, ...m.filter((x: unknown) => typeof x === "object"))) as object),
          module: location.pathname,
        };
        void fetch("/api/v1/client-logs", { // endpoint is yours; it must not be logged again by loggedFetch
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
          keepalive: true,
        });
      },
    },
  },
});

// func: component or function name, passed by the call site through a child logger.
export const componentLogger = (func: string) => logger.child({ func });
// Usage in a component:  const log = componentLogger("CheckoutForm"); log.info({ order_id }, "order_submitted");

window.addEventListener("error", (e: ErrorEvent) => {
  logger.fatal({
    func: "window.onerror", file: e.filename, line: e.lineno,
    exception: { message: e.message, stack: (e.error as Error | undefined)?.stack },
  }, "uncaught_error");
});

window.addEventListener("unhandledrejection", (e: PromiseRejectionEvent) => {
  const r = e.reason as Error | unknown;
  logger.fatal({
    func: "window.onunhandledrejection",
    exception: r instanceof Error ? { message: r.message, stack: r.stack } : { message: String(r) },
  }, "unhandled_rejection");
});
```

Notes:
- Browser `console` output: with `asObject` pino writes objects to the console; this is the dev view. In prod only WARNING+ is shipped; DEBUG/INFO stay in the console or are dropped by `level`.
- Masking happens before `fetch` in `send` (above); `mask` is a hand-written function, pino `redact` is not used in the browser here.
- The `file`/`line` for ordinary calls are not available in the browser build (no stack helper); the `error` handler gives them via `ErrorEvent`. After Vite minification function names are mangled: upload source maps (UNVERIFIED how the backend resolves them), and pass `func` explicitly.
- A shipped `PANIC` from `logger.fatal` goes through `transmit` because its level is above `warn`.
- The backend endpoint must validate and rate-limit client logs and never trust client-provided `level` blindly.
