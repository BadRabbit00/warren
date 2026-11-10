---
name: frontend-data-layer
description: Use when writing or changing the data and auth layer of a React + Vite + TypeScript frontend - API modules and the http client, types generated from OpenAPI, TanStack Query hooks, env config, i18n keys, cookie login with CSRF and refresh, and the frontend checks. Visual design and markup are out of scope.
---

# Frontend data layer

Behaviour and data of the interface; looks belong to the designer. Component patterns are in `react-patterns`, Vite config and env pitfalls in `vite-patterns`; this skill does not repeat them. Rule ids `R-FDL-*`; examples are in `references/`.

**Priority.** The task and its failing tests > the project's `AGENTS.md`/`CLAUDE.md` > this skill. Follow the existing folder structure. Tests are read-only for you.

## Contents

1. [Chain and structure](#chain-and-structure)
2. [Server state and types](#server-state-and-types)
3. [Config and i18n](#config-and-i18n)
4. [Auth in the browser](#auth-in-the-browser)
5. [Checks before you hand back](#checks-before-you-hand-back)

## Chain and structure

Details: `references/data-chain.md`.

- R-FDL-CHAIN: component -> hook -> API module -> `http.ts` client. A component never calls `fetch`/`axios`; a hook never builds URLs; an API module returns typed data and knows nothing about React.
- R-FDL-HTTP-ONE: one `shared/api/http.ts` owns base URL, `credentials: "include"`, CSRF header, JSON parsing, error mapping and the 401 refresh. No second client.
- R-FDL-NO-RULES: no business rules on the client. Prices, permissions and status transitions come from the API; the UI only shows them (hiding a button is not access control).
- R-FDL-NAMING: files by role and entity (`orders.api.ts`, `useOrders.ts`, `OrderList.tsx`); no `utils`, `helpers`, `common`. `strict` TypeScript, no `any` for API data.

## Server state and types

Details: `references/server-state.md`.

- R-FDL-TYPES-GENERATED: API types are generated from the backend OpenAPI (`openapi-typescript` or the project's generator) into `shared/api/schema.ts`; never hand-copied, never edited by hand. A mismatch is fixed on the backend or by regenerating.
- R-FDL-QUERY: server state lives in TanStack Query, not in `useState`/Redux/context. Query keys come from one factory per entity; a mutation invalidates the keys it affects.
- R-FDL-PARSE-EDGE: the API module is the only place that touches raw responses; it returns typed values (validate with zod only where the backend schema is not trusted).
- R-FDL-STATES: every query-backed screen handles loading, error, empty and data states.

## Config and i18n

Details: `references/config-i18n.md`.

- R-FDL-ENV-ONE: env is read only in `shared/config/env.ts` (`import.meta.env`), validated once, typed. Only public values carry the `VITE_` prefix; no secrets in the bundle.
- R-FDL-I18N: with a multilingual interface every user-visible string is an i18n key, never a literal in JSX; dates, numbers and money are formatted with `Intl` by locale.

## Auth in the browser

Details: `references/auth-browser.md`. The server side is the skill `auth-service`.

- R-FDL-COOKIES: tokens live in httpOnly + Secure + SameSite cookies set by the server. Never `localStorage`, `sessionStorage`, URLs, logs, or JS-readable cookies.
- R-FDL-CSRF: every state-changing request (POST/PUT/PATCH/DELETE) sends the CSRF header from the CSRF cookie; this is done in `http.ts` only.
- R-FDL-REFRESH: on 401 `http.ts` calls refresh once (a single shared in-flight promise), retries the request once, and on failure clears the session and goes to login. No refresh loops.
- R-FDL-SESSION: "who am I" is a query (`/me`) behind a hook; route guards read it. The client never decodes or stores tokens.

## Checks before you hand back

1. `nix develop -c npx --no-install tsc --noEmit`, `nix develop -c npx --no-install eslint .`, `nix develop -c npx --no-install vitest run` (or the project's `npm run typecheck|lint|test`) - numbers in the report; no skipped. If a binary is missing from `node_modules`, report `STATUS: blocked`; never let `npx` fetch a package.
2. Playwright (when the task has e2e tests) uses browsers from nixpkgs (`PLAYWRIGHT_BROWSERS_PATH` from the dev shell), never a downloaded browser.
3. Dependencies: `nix develop -c npm ci`; a new package is reported (name, version, why), not added.
4. `git diff`: files of the write set only; grep your diff for `fetch(` in components, `localStorage`, `sessionStorage`, `import.meta.env` outside `env.ts`, `any`.
