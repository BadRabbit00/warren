# Structure

## Ownership
- `src/auth/` is self-contained: its code, `pyproject.toml`, `.env.example`, Alembic migrations, tests. Build recipe: a Dockerfile with context `src/auth/`. It could move to its own repo and still build and pass tests. Auth imports no other service's code, and nobody imports its code.
- Next to a modular monolith there is exactly one extra service — auth. No "users with passwords" module inside the monolith; the monolith verifies tokens like any consumer.
- Auth owns accounts (login/email, password hash, status), user roles, refresh sessions, service clients, signing keys. Business profile data (name, address, avatar, settings) lives in a domain service, keyed by `sub`.
- Own PostgreSQL database and DB user with rights only on it (one Postgres instance shared is fine, a shared superuser is not). Own Redis (container or ACL user limited to `auth:*`).
- Nobody else connects to auth's DB or Redis, maps the `users` table, or joins it. User data comes from `GET /internal/users/{id}` with a service token, or a local copy updated by events `user.registered`, `user.roles_changed`, `user.deactivated`. References are `user_id: UUID` without a foreign key.
- Events go through a transactional outbox, never published straight from a request handler.
- Auth knows no business entities; object rights belong to the owning service.

## Stack

| Need | Use | Not |
|---|---|---|
| HTTP | FastAPI + uvicorn, Pydantic v2, pydantic-settings | Django, Flask |
| issuing/verifying JWT in auth | AuthX (pinned) | python-jose, hand-written `jwt.encode` |
| JWKS/JWK in auth; verification in Python consumers | PyJWT (`pyjwt[crypto]`) | hand-built JWK, python-jose |
| verification in Go | `golang-jwt/jwt/v5` + `MicahParks/keyfunc/v3` | hand-parsed JWT |
| passwords | `pwdlib[argon2]` | passlib, hashlib, MD5/SHA, PBKDF2, home-made salts |
| data | PostgreSQL + SQLAlchemy 2.0 (asyncpg) + Alembic | SQLite, sessions only in Redis |
| revocation, limits, locks | Redis | in-process dicts |
| logs | structlog (JSON) | print |
| tests | pytest, pytest-asyncio, httpx `AsyncClient`, real PostgreSQL | SQLite |

Dependencies are pinned in `pyproject.toml` and `uv.lock` (`authx`, `pwdlib`). Async code; hashing and other blocking calls through `run_in_threadpool`.

## Layout

```text
src/auth/
├── app/
│   ├── main.py            # creates FastAPI, routers, error handlers; no logic
│   ├── core/              # config.py, database.py, redis.py, keys.py (PEM, kid, JWKS), security.py (AuthX), logging.py
│   ├── api/
│   │   ├── deps.py        # SessionDep, services, CurrentUserDep, require_roles, rate limits
│   │   ├── errors.py      # domain and AuthX errors → HTTP
│   │   └── routers/       # auth_router.py, user_router.py, jwks_router.py, internal_router.py, health_router.py
│   ├── schemas/           # auth_schema.py, user_schema.py, token_schema.py
│   ├── models/            # user_model.py, refresh_session_model.py, service_client_model.py, outbox_model.py
│   ├── repositories/      # user_repository.py, refresh_session_repository.py, service_client_repository.py
│   ├── services/          # auth_service.py, token_service.py, password_service.py, user_service.py
│   ├── domain/            # enums.py (Role), exceptions.py (InvalidCredentials, RefreshReused, …)
│   └── cli/               # keygen.py, create_admin.py
├── migrations/
├── tests/                 # unit/, integration/, api/
└── pyproject.toml, .env.example
```

Layers: router (HTTP, schemas, rights, limits, cookies) → service (rules, the one `commit`) → repository (ORM, row locks, no commit) → models. `domain/` holds enums, exceptions, pure functions. ORM only; races closed with `with_for_update()` or conditional `update(...).returning(...)`. Roles are an enum; TTLs, limits, URLs in `Settings`. Logs never contain passwords, tokens, cookies, or fragments of them.

```python
# api/routers/auth_router.py — HTTP only
@router.post("/login", response_model=MeRead)
async def login(body: LoginIn, request: Request, response: Response,
                service: AuthServiceDep, _: LoginRateLimitDep) -> MeRead:
    result = await service.login(body.email, body.password, client=ClientInfo.from_request(request))
    auth.set_access_cookies(result.access, response, max_age=settings.access_ttl_minutes * 60)
    auth.set_refresh_cookies(result.refresh, response, max_age=settings.refresh_ttl_days * 86400)
    return MeRead.model_validate(result.user)

# services/auth_service.py — rules and the transaction
class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.sessions = RefreshSessionRepository(session)

    async def login(self, email: str, password: str, *, client: ClientInfo) -> LoginResult:
        user = await self.users.get_by_email(normalize_email(email))
        valid = await verify_password(password, user.password_hash if user else None)
        if user is None or not valid or not user.is_active:
            raise InvalidCredentials()                 # one answer for all three cases
        refresh_session = self.sessions.start(user_id=user.id, client=client, settings=settings)
        await self.session.commit()
        return LoginResult(user, *issue_pair(user, refresh_session, is_login=True))
```

## Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/login` | check password, start a refresh session, set cookies |
| `POST /api/auth/refresh` | rotate refresh, issue a new pair |
| `POST /api/auth/logout`, `POST /api/auth/logout-all` | revoke this session / all sessions of the user |
| `GET /api/auth/me` | who is logged in: id, roles, display fields |
| `GET /.well-known/jwks.json` | public keys |
| `POST /internal/token` | service token by client credentials |
| `GET /health`, `GET /ready` | alive; ready = own DB and Redis reachable |

Registration, password reset, email confirmation, MFA: per project requirements, in this service.
