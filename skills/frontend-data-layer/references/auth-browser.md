# Auth in the browser - examples

The server issues cookies and checks CSRF (skill `auth-service`); the client only cooperates.

### R-FDL-COOKIES - no tokens in JS-reachable storage

Bad:
```ts
const { access_token } = await login(body);
localStorage.setItem("token", access_token);
fetch(`/v1/orders?token=${access_token}`);
```
Why: any XSS reads the token; URLs end up in logs, history and referrers.

Good:
```ts
await http.post("/v1/auth/login", body);        // server sets httpOnly Secure SameSite cookies
const me = await http.get<Me>("/v1/me");       // the session is proven by the cookie
```

### R-FDL-CSRF and R-FDL-REFRESH - both live in http.ts

Bad:
```tsx
// every component adds its own header and handles 401 itself
await fetch("/v1/orders", { method: "POST", body, headers: { "X-CSRF-Token": getCookie("csrf") } });
if (res.status === 401) await fetch("/v1/auth/refresh", { method: "POST" });   // N parallel refreshes, no limit
```
Why: one forgotten header breaks a form; parallel refreshes revoke each other because refresh tokens rotate.

Good:
```ts
// shared/api/http.ts
let refreshing: Promise<void> | null = null;
const noRefresh = new Set(["/v1/auth/login", "/v1/auth/refresh"]);   // paths follow docs/API.md

async function request<T>(method: string, path: string, body?: unknown, retried = false): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (method !== "GET") headers["X-CSRF-Token"] = readCookie("csrf_token") ?? "";
  const res = await fetch(env.apiUrl + path, { method, headers, credentials: "include", body: body && JSON.stringify(body) });
  if (res.status === 401 && !retried && !noRefresh.has(path)) {
    refreshing ??= refresh().finally(() => { refreshing = null; });   // one shared refresh
    try { await refreshing; } catch { sessionExpired(); throw new ApiError(401); }
    return request<T>(method, path, body, true);                       // retry once
  }
  if (!res.ok) throw await toApiError(res);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}
```
A 401 from login is a normal error (wrong password) and reaches the form. `http.get(path, { params })` is a thin wrapper over `request` that appends `new URLSearchParams(params)` to the path. Header and cookie names follow the backend contract (`docs/API.md`); the CSRF cookie is the only cookie JS may read.

### R-FDL-SESSION - session is a query

Bad:
```ts
const token = localStorage.getItem("token");
const claims = JSON.parse(atob(token.split(".")[1]));     // decoding tokens on the client
const isAdmin = claims.role === "admin";
```
Why: the client trusts unverified data and holds a token it must not have.

Good:
```ts
export const useMe = () => useQuery({ queryKey: ["me"], queryFn: () => http.get<Me>("/v1/me"), retry: false });
// route guard: const { data: me, isPending } = useMe(); if (!isPending && !me) return <Navigate to="/login" />;
```
