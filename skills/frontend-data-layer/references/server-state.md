# Server state and types - examples

### R-FDL-TYPES-GENERATED - types come from OpenAPI

Bad:
```ts
// shared/api/types.ts, copied by hand
export interface Order { id: string; number: string; total: number }   // backend now returns total_minor
```
Why: the copy drifts silently; the compiler stays green while the UI shows `undefined`.

Good:
```ts
// generated: nix develop -c npx openapi-typescript <backend openapi.json> -o src/shared/api/schema.ts
import type { components } from "@/shared/api/schema";
export type Order = components["schemas"]["OrderRead"];
```

### R-FDL-QUERY - TanStack Query owns server data

Bad:
```tsx
const [orders, setOrders] = useState<Order[]>([]);
const create = async (body: OrderCreate) => {
  await createOrder(body);
  setOrders(await listOrders());          // manual refetch, no cache, no dedupe
};
```
Why: duplicated state, races between requests, no retry or cache control.

Good:
```ts
export const orderKeys = {
  all: ["orders"] as const,
  list: (f: OrderFilters) => [...orderKeys.all, "list", f] as const,
};

export const useCreateOrder = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createOrder,
    onSuccess: () => qc.invalidateQueries({ queryKey: orderKeys.all }),
  });
};
```

### R-FDL-STATES - all four states

Bad:
```tsx
const { data } = useOrders(filters);
return <ul>{data!.map((o) => <OrderRow key={o.id} order={o} />)}</ul>;
```
Why: crashes while loading and on error; the empty list shows a blank page.

Good:
```tsx
if (isPending) return <Spinner />;
if (error) return <ErrorState error={error} onRetry={refetch} />;
if (data.length === 0) return <EmptyState text={t("orders.empty")} />;
return <ul>{data.map((o) => <OrderRow key={o.id} order={o} />)}</ul>;
```
