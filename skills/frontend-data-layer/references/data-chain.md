# Chain and structure - examples

### R-FDL-CHAIN - component -> hook -> API module -> http client

Bad:
```tsx
export function OrderList() {
  const [orders, setOrders] = useState<any[]>([]);
  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_URL}/v1/orders`).then((r) => r.json()).then(setOrders);
  }, []);
  return <ul>{orders.map((o) => <li key={o.id}>{o.number}</li>)}</ul>;
}
```
Why: URL, parsing, loading and errors live in the view; nothing is reusable or testable apart from the DOM.

Good:
```tsx
// shared/api/http.ts            -> request<T>(method, path, body?)
// features/orders/orders.api.ts
export const listOrders = (params: OrderFilters) =>
  http.get<components["schemas"]["OrderRead"][]>("/v1/orders", { params });

// features/orders/useOrders.ts
export const useOrders = (filters: OrderFilters) =>
  useQuery({ queryKey: orderKeys.list(filters), queryFn: () => listOrders(filters) });

// features/orders/OrderList.tsx
const { data, isPending, error } = useOrders(filters);
```

### R-FDL-NO-RULES - the server decides

Bad:
```tsx
const total = items.reduce((s, i) => s + i.price * i.qty, 0) * (user.isVip ? 0.9 : 1);
const canCancel = order.status === "new" || (order.status === "paid" && user.role === "admin");
```
Why: the discount and the cancel rule now exist twice and drift; the client is not a security boundary.

Good:
```tsx
const { total_minor, can_cancel } = order;        // computed by the API
<button disabled={!can_cancel} onClick={() => cancel.mutate(order.id)}>{t("orders.cancel")}</button>
```
