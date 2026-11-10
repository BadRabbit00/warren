# prometheus.yml

Facts (research wf_35c2e079-c6c): top-level keys `global`, `rule_files`, `scrape_configs` (`static_configs`, `docker_sd_configs`), `alerting`. Anything else is (U) verify against the pinned version.

## Skeleton

```yaml
global:
  scrape_interval: 15s        # (U) value: POLICY or ask; shown as an example of the field only
  evaluation_interval: 15s

rule_files:
  - /etc/prometheus/rules/*.yml

alerting:
  alertmanagers:            # (U) verify field layout in the pinned version
    - static_configs:
        - targets: ["alertmanager:9093"]   # (U) port

scrape_configs:
  - job_name: api
    metrics_path: /metrics
    static_configs:
      - targets: ["api:9464"]
```

Intervals are POLICY values; when POLICY is silent, ask. Example numbers above are not defaults to copy.

## Choosing static vs Docker SD

| Case | Use |
|---|---|
| Few fixed services, names known | `static_configs` with service names (compose) or addresses (separate server) |
| Containers come and go on one Docker host | `docker_sd_configs` (the Prometheus container needs access to the Docker socket or API: a security decision, raise it with deploy-engineer) |

`docker_sd_configs` fields (`host`, relabeling by container labels) are (U) verify; the research confirms only that the block exists.

## Job per service

- One `job_name` per service; the name appears in alerts as `job`.
- Port and path come from the service's metrics endpoint (skill `metrics`), not from guesses.
- Targets that need auth: credentials never inline (R-OBS-NO-INLINE-SECRETS).

## Check

```text
nix shell nixpkgs#prometheus -c promtool check config prometheus.yml
```
