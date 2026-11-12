---
paths:
  - "**/*.ts"
  - "**/*.tsx"
---

# TypeScript and React

## Scope

Front-end code: React + Vite + TypeScript, TanStack Query, the API layer. Visual rules are in `design.md`; this is the language and React part. `language-reviewer` checks it in depth.

Checks: `tsc --noEmit`; `eslint`; `vitest run`; Playwright only with browsers from nixpkgs, never downloaded.

## Rules

- R-TS-STRICT: `strict: true`; no `any`, no `as` casts to silence the compiler, no `!` without a guard above it. Data from the network is `unknown` until parsed (zod schema in the API module).
- R-TS-SERVER-STATE: server data lives in TanStack Query hooks (`useOrders`), not in `useState` + `useEffect`. Keys are stable arrays (`["orders", filters]`); mutations invalidate the keys they change.
- R-TS-EFFECTS: `useEffect` only to sync with something outside React (subscriptions, the DOM, timers), with complete dependencies and a cleanup. Values computable from props or state are computed, not stored.
- R-TS-STATE: state is never mutated in place; updates create new objects. List keys are stable ids, never the array index for lists that change.
- R-TS-HTML: no `dangerouslySetInnerHTML` with data that is not sanitized (DOMPurify) and needed as HTML; no `innerHTML`, `eval`, or `new Function`.
- R-TS-ASYNC: no floating promises: every promise is awaited, returned, or handled (`void` only with a `.catch`). Event handlers that call async code show errors to the user.
- R-TS-ENV: environment values are read only in `shared/config/env.ts`; components and hooks import from there.
- R-TS-NAMES: `orderApi.ts`, `useOrders.ts`, `OrderTable.tsx`; one component per file; no `utils.ts` dumps.

## Examples

### R-TS-SERVER-STATE — no fetch-in-effect

Bad:
```tsx
const [orders, setOrders] = useState<any[]>([]);
useEffect(() => {
  fetch(`/api/v1/orders?status=${status}`).then(r => r.json()).then(setOrders);
}, []);                                                     // stale when status changes
```
Why: missing dependency, no error or loading state, `any`, and a race when the status changes quickly.

Good:
```tsx
const { data: orders = [], isPending, error } = useOrders({ status });   // hook → orderApi → http.ts
```

### R-TS-STATE — keys and immutability

Bad:
```tsx
items.push(newItem);
setItems(items);                                  // same array: no re-render
return items.map((it, i) => <Row key={i} item={it} />);
```
Why: React sees no change; index keys mix up row state after inserts and deletes.

Good:
```tsx
setItems(prev => [...prev, newItem]);
return items.map(it => <Row key={it.id} item={it} />);
```
