# Vulnerable → fixed

Each pair: the weakness as it is usually written, why it fails, and the fix in the project's stack.

### R-SEC-IDOR — object access without an ownership check (S-ACCESS-2)

Bad:
```python
@router.get("/v1/orders/{order_id}")
async def get_order(order_id: UUID, user: CurrentUserDep, svc: OrderServiceDep) -> OrderRead:
    return await svc.get(order_id)            # any logged-in user reads any order
```
Why: the route checks that a user is logged in, not that the order is theirs; IDs are guessable or leak in URLs.

Good:
```python
async def get(self, actor: CurrentUser, order_id: UUID) -> Order:
    order = await self._orders.get(order_id)
    if order is None or not (order.customer_id == actor.id or Role.ADMIN in actor.roles):
        raise OrderNotFound(order_id)         # same answer as "does not exist": no existence leak
    return order
```

### R-SEC-JWT-VERIFY — trusting the token to describe its own verification (S-AUTHN-1)

Bad:
```python
header = jwt.get_unverified_header(token)
claims = jwt.decode(token, key, algorithms=[header["alg"]], options={"verify_aud": False})
```
Why: the attacker picks the algorithm; any audience is accepted, so a token for another service works here.

Good:
```python
claims = jwt.decode(token, jwks[kid].key, algorithms=["ES256"], issuer=settings.auth_issuer,
                    audience=settings.api_audience, leeway=30,
                    options={"require": ["exp", "iat", "sub", "jti", "iss", "aud"]})
if claims.get("type") != "access":
    raise jwt.InvalidTokenError("access token required")
```

### R-SEC-MASS-ASSIGN — role from the request body (S-ACCESS-4)

Bad:
```python
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    role: Role = Role.CUSTOMER

user = User(**body.model_dump())               # {"role": "admin"} is accepted
```
Why: anyone can register as an administrator.

Good:
```python
class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)

user = User(email=body.email, password_hash=hasher.hash(body.password.get_secret_value()), role=Role.CUSTOMER)
```

### R-SEC-SSRF — fetching a user-supplied URL (S-SSRF-1)

Bad:
```python
@router.post("/v1/integrations/test-webhook")
async def test_webhook(body: WebhookIn, http: HttpDep) -> dict:
    r = await http.get(body.url)               # http://169.254.169.254/… or http://redis:6379
    return {"status": r.status_code, "body": r.text[:500]}
```
Why: the server becomes a proxy into the internal network and cloud metadata, and echoes the answer back.

Good:
```python
async def fetch_external(http: httpx.AsyncClient, raw_url: str) -> httpx.Response:
    url = httpx.URL(raw_url)
    if url.scheme != "https" or url.host is None:
        raise UnsafeUrl(raw_url)
    infos = await asyncio.get_running_loop().getaddrinfo(url.host, url.port or 443, type=socket.SOCK_STREAM)
    ips = {ipaddress.ip_address(i[4][0]) for i in infos}
    if any(not ip.is_global for ip in ips):
        raise UnsafeUrl(raw_url)
    ip = sorted(ips, key=str)[0]
    return await http.get(url.copy_with(host=str(ip)), headers={"Host": url.host},
                          extensions={"sni_hostname": url.host}, follow_redirects=False, timeout=5.0)
# and the response is not echoed back: only "delivered / failed"
```

### R-SEC-UPLOAD-PATH — the user's filename in a path (S-FILE-3)

Bad:
```python
dest = os.path.join(settings.upload_dir, file.filename)    # "../../app/main.py"
with open(dest, "wb") as f:
    f.write(await file.read())                               # no size limit, whole file in memory
```
Why: path traversal overwrites application files; a huge upload exhausts memory.

Good:
```python
key = f"uploads/{actor.id}/{uuid4()}"
size = 0
async with s3.multipart(key, content_type=detected_type) as mp:
    while chunk := await file.read(1 << 20):
        size += len(chunk)
        if size > settings.max_upload_bytes:
            raise UploadTooLarge()
        await mp.write(chunk)
await files.add(owner_id=actor.id, key=key, original_name=file.filename[:255], size=size)
```

### R-SEC-SQLI-GO — query text from fmt.Sprintf (S-INPUT-2)

Bad:
```go
q := fmt.Sprintf("SELECT id, email FROM users WHERE email = '%s'", email)
rows, err := db.QueryContext(ctx, q)
```
Why: `' OR '1'='1` returns every user.

Good:
```go
var u User
err := db.WithContext(ctx).Select("id", "email").Where("email = ?", email).Take(&u).Error
```

### R-SEC-CORS — any origin with credentials (S-API-2)

Bad:
```python
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"])
```
Why: with credentials, a permissive policy lets other sites make authenticated requests and read the answers (Starlette even reflects the origin).

Good:
```python
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-CSRF-TOKEN"])
# settings validator: production refuses "*" in cors_origins
```

### R-SEC-GHA-PRT — running PR code with secrets (S-CONF-1)

Bad:
```yaml
on: pull_request_target
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { ref: "${{ github.event.pull_request.head.sha }}" }
      - run: make test
        env: { DEPLOY_TOKEN: "${{ secrets.DEPLOY_TOKEN }}" }
```
Why: a fork PR's code runs with the repository's secrets and a write token.

Good:
```yaml
on: pull_request
permissions: { contents: read }
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<full-commit-sha>   # pinned
      - run: make test               # no secrets in PR checks
```

### R-SEC-TOKEN-STORAGE — tokens readable by any script (S-SESS-1)

Bad:
```ts
const { access_token } = await api.post("/auth/login", creds);
localStorage.setItem("access_token", access_token);
```
Why: any XSS, or any third-party script on the page, reads the token and uses it elsewhere.

Good:
```ts
await http.post("/api/auth/login", creds);   // auth sets HttpOnly cookies; http.ts adds X-CSRF-TOKEN on mutations
const me = await http.get<Me>("/api/auth/me");
```

### R-SEC-WEBHOOK-SIG — unverified or replayable webhooks (S-AUTHN-6)

Bad:
```python
if request.headers.get("X-Signature") == hashlib.sha256(secret + body).hexdigest():
    await handle(json.loads(body))
```
Why: plain hash instead of HMAC, `==` leaks timing, and an old captured request can be replayed forever.

Good:
```python
ts = int(request.headers["X-Timestamp"])
if abs(time.time() - ts) > 300:
    raise InvalidSignature()
expected = hmac.new(secret, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
if not hmac.compare_digest(request.headers.get("X-Signature", ""), expected):
    raise InvalidSignature()
if not await events.insert_if_new(event_id=payload_id(body)):   # replay / duplicate protection
    return
```
