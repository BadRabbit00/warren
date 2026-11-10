# Config, logging, runtime - examples

### R-PYS-CONFIG - one module reads env

Bad:
```python
class PaymentClient:
    def __init__(self) -> None:
        self.url = os.getenv("PAYMENT_URL", "")   # empty string at runtime if unset
```
Why: a missing variable surfaces as a failed request in production, not as a startup error.

Good:
```python
# core/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORDERS_")
    payment_url: AnyHttpUrl            # required: fails at startup
    payment_timeout_s: float = 5.0

@lru_cache
def get_settings() -> Settings:
    return Settings()
```
Add `ORDERS_PAYMENT_URL=` (no real value) to `.env.example` in the same change.

### R-PYS-LOGGING - structured, no secrets

Bad:
```python
print(f"user {user.email} logged in with {password}")
logger.info(f"order {order.id} paid")
```
Why: secrets and personal data in logs; the message cannot be searched by field.

Good:
```python
log = structlog.get_logger(__name__)
log.info("order_paid", order_id=str(order.id), amount_minor=order.total_minor)
```

### R-PYS-NIX - the dev shell, not a private environment

Bad:
```text
create a private Python environment in the repo and pip-install httpx into it
```
Why: the environment is not reproducible and drifts from the dev shell and CI.

Good:
```text
nix develop -c pytest -q
# a new dependency: report name, version, why; the Nix owner adds it to pyproject.toml and the devShell
```
