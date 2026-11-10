# Config and i18n - examples

### R-FDL-ENV-ONE - one env module

Bad:
```ts
// in three different files
const base = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const key = import.meta.env.VITE_PAYMENT_SECRET;       // secret in the bundle
```
Why: scattered defaults hide a missing variable; anything with `VITE_` is shipped to every visitor.

Good:
```ts
// shared/config/env.ts
const raw = import.meta.env;
if (!raw.VITE_API_URL) throw new Error("VITE_API_URL is required");
export const env = { apiUrl: raw.VITE_API_URL as string } as const;
// elsewhere: import { env } from "@/shared/config/env";
```

### R-FDL-I18N - keys, not literals

Bad:
```tsx
<button>Cancel order</button>
<span>{new Date(o.created_at).toLocaleDateString()}</span>
```
Why: untranslatable text; the date format depends on the browser default, not on the chosen locale.

Good:
```tsx
const { t, i18n } = useTranslation();
<button>{t("orders.cancel")}</button>
<span>{new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" }).format(new Date(o.created_at))}</span>
```
