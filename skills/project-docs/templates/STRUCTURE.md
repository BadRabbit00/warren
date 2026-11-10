# STRUCTURE — <project name>

<!-- Repository map. For each file: why it exists, which classes and functions are inside — one line each.
Entity details → ENTITY.md, fat method details → METHOD.md.
Tests (`tests/` folders), generated code and vendor: one line per folder, not per file. -->

## Tree

```
<repo>/
├── src/
│   ├── <orders>/         # <orders service>
│   │   ├── app/          # <router → service → repository → model>
│   │   └── tests/        # <this service's tests>
│   └── <billing>/        # <...>
├── deploy/               # <Dockerfiles, Quadlet/systemd units, install scripts>
├── docs/                 # this documentation
├── .plan/                # current change plan (temporary)
├── tests/                # <shared / cross-service tests>
├── pyproject.toml, uv.lock   # <or package.json, go.mod, Cargo.toml>
└── compose.yaml          # <local stack>
```

## Entry points

| What | File | How it runs |
|---|---|---|
| <orders HTTP server> | `<src/orders/app/main.py>` | `<uvicorn ...>` |
| <queue worker> | `<...>` | `<...>` |
| <CLI / cron> | `<...>` | `<...>` |

---

## `<src/orders/app/>`

### `<routers/order_router.py>`

**Purpose:** <orders HTTP routes>

- `<create_order()>` — <endpoint `POST /v1/orders` → API.md#<post-v1orders>>
- `<get_order()>` — <...>

### `<models/order_model.py>`

**Purpose:** <order domain model>

- `<Order>` — <order entity> → `ENTITY.md#<order>`
- `<OrderStatus>` — <status enum>

### `<services/order_service.py>`

**Purpose:** <order business logic>

- `<OrderService>` — <...> → `ENTITY.md#<orderservice>`
  <!-- If the file/class does several different things, list them: -->
  1. <create order>
  2. <cancel>
  3. <recalculate total>

---

## Configs and service files

| File | Purpose |
|---|---|
| `<pyproject.toml>` | <dependencies and build> |
| `<.env.example>` | <environment variables, no values> |
| `<pyproject.toml>` | <Python deps, linter settings> |
