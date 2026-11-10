# prometheus.yml

Facts (research wf_35c2e079-c6c): top-level keys `global`, `rule_files`, `scrape_configs` (`static_configs`, `docker_sd_configs`), `alerting`. Anything else is (U) verify against the pinned version.

## Skeleton

```yaml
global:
  scrape_interval: 15s        # (U) value: POLICY or ask; shown as an example of the field only
  evaluation_interval: 15s

rule_files:
  - rules/*.yml             # relative paths resolve against the directory of prometheus.yml

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

## Docker SD

Fields (R, wf_340d5dfb-77e): `host` (required, address of the Docker daemon), `port` (default 80), `host_networking_host` (default `localhost`), `match_first_network` (default true), `filters` (Docker ContainerList filters: `name` + `values`), `refresh_interval` (default 60s), `http_config`. Labels for relabeling: `__meta_docker_container_id`, `_name`, `_image`, `_image_id`, `_network_mode`, `__meta_docker_container_label_<labelname>`, `__meta_docker_network_*` (`id`, `name`, `ingress`, `internal`, `scope`, `ip`, `label_<labelname>`), `__meta_docker_port_private`, `__meta_docker_port_public`, `__meta_docker_port_public_ip`.

Scrape only labelled containers: keep on the container label, and take the port from a label. `prometheus.scrape` and `prometheus.port` are example label names the project chooses and puts in the compose files (deploy-engineer); Prometheus rewrites `.` in label names to `_`.

```yaml
global:
  scrape_interval: 15s    # (U) value: POLICY or ask

scrape_configs:
  - job_name: docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock   # needs the socket mounted into Prometheus: security decision for deploy-engineer
        refresh_interval: 60s
    relabel_configs:
      - source_labels: [__meta_docker_container_label_prometheus_scrape]
        regex: "true"
        action: keep
      - source_labels: [__meta_docker_container_name]
        regex: "/(.*)"
        target_label: instance
      - source_labels: [__address__, __meta_docker_container_label_prometheus_port]
        regex: "(.+):\\d+;(\\d+)"
        replacement: "$1:$2"
        target_label: __address__
```

The `keep` relabel is the pattern from the Prometheus docs; the `instance` and `__address__` rules are the generic relabeling (`regex`, `replacement`, `target_label`) and are checked only by `promtool check config` (syntax), not against a running Docker. (U) The `__address__` rewrite depends on how the container publishes ports; verify with a running stack.

## Job per service

- One `job_name` per service; the name appears in alerts as `job`.
- Port and path come from the service's metrics endpoint (skill `metrics`), not from guesses.
- Targets that need auth: credentials never inline (R-OBS-NO-INLINE-SECRETS).

## Check

```text
nix shell nixpkgs#prometheus.cli -c promtool check config prometheus.yml
```
