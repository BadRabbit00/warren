# TypeScript logging template: browser frontends only (pino 10.x)

Scope: browser frontends (React + Vite). There are no Node/TypeScript backends; backends are Python, Go, Rust. Copy per frontend (D12), no cross-service package: `src/core/logger.ts` of the frontend. Canonical fields as far as the browser can supply them: `timestamp level event module func` plus `exception` and context objects. Levels `DEBUG INFO WARNING ERROR PANIC`; secrets always `***`; personal data masked unless DEBUG; time is UTC ISO 8601 with `Z`.

Facts used (research wf_6b111f8e-0e4, pino 10.4.0 latest on 2026-11-10):
- Browser build: `asObject`, `write`, `serialize`, `transmit.send`, `transmit.level`; browser `formatters` support only `level`.
- `child(bindings)` gives a logger with fixed fields such as `func`.

Marked UNVERIFIED (not in the research; check the pino 10 docs before relying on it): `fatal` as the PANIC label via browser `formatters.level`, method/component names after Vite minification (need source maps).

## `src/core/logger.ts` (React + Vite)

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
        void fetch("/api/v1/client-logs", { // endpoint is yours; it must not be sent through this logger again
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
