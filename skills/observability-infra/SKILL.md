---
name: observability-infra
description: Use when writing or reviewing monitoring configuration as files - Prometheus scrape config, recording and alert rules, Alertmanager routing and receivers, Grafana datasource and dashboard provisioning - and checking it locally with promtool and amtool. Not for deploying it.
---

# Observability infra

Monitoring configuration written as files in the repository and checked locally. The agent that loads this skill writes files and runs checks; it never deploys. Services expose metrics per the `metrics` skill; this skill consumes those endpoints.

## When to use

- A project needs Prometheus scraping, alerts, Alertmanager routing, or Grafana dashboards as code.
- Reviewing such files.
- Not for: instrumenting services (skill `metrics`), starting containers or servers (skills `deploy-variants`, `docker-patterns`; agent deploy-engineer via /br-deploy).

## Contents

1. [Facts and versions](#facts-and-versions) · 2. [File layout](#file-layout) · 3. [Workflow](#workflow) · 4. [Rules](#rules) · 5. [Hand-off to deploy-engineer](#hand-off-to-deploy-engineer) · 6. [Reviewer checklist](#reviewer-checklist) · 7. [References](#references)

## Facts and versions

Source: /br-research wf_35c2e079-c6c (2026-11-10), official "latest" docs; the Prometheus configuration page references 3.16. No Prometheus, Alertmanager or Grafana version is pinned in the project: read the pinned version from the deploy files (compose image tag, Nix package) before using a field, and mark anything not listed here "(U) verify".

| Area | Stated by the research |
|---|---|
| `prometheus.yml` | top-level `global`, `rule_files`, `scrape_configs` (with `static_configs`, `docker_sd_configs`), `alerting` |
| Rule files | `groups` -> `rules`; alert rule: `alert`, `expr`, `for`, `keep_firing_for`, `labels`, `annotations`; recording rule: `record`, `expr`, `labels` |
| Alertmanager | `route` (`receiver`, `group_by`, `group_wait`, `group_interval`, `repeat_interval`, `routes` with `matchers`), `receivers` (e.g. `webhook_configs`), optional `inhibit_rules` |
| Checks | `promtool check config`, `promtool check rules`, `promtool test rules`, `amtool check-config` |
| Grafana | reads `provisioning/datasources` and `provisioning/dashboards` YAML; datasources: `apiVersion: 1` + `datasources` list; dashboards: `providers` list with `type: file` and `options.path` |
| Dashboard JSON | `uid`, `title`, `tags`, `panels`, `templating`, `time`, `schemaVersion`, `version`, `refresh` |

Everything else (field defaults, Docker SD relabeling, secret-from-file fields, Nix package names, Grafana env substitution) is **(U) verify** against the pinned version before relying on it.

## File layout

A default; the plan may change it. Follow the repository's existing layout when one exists.

```text
deploy/observability/
  prometheus/prometheus.yml
  prometheus/rules/*.yml            # alert + recording rules, one file per area
  prometheus/tests/*.yml            # promtool test rules (optional)
  alertmanager/alertmanager.yml
  grafana/provisioning/datasources/*.yml
  grafana/provisioning/dashboards/*.yml
  grafana/dashboards/*.json
```

## Workflow

1. Read the task, `docs/POLICY.md` (SLOs, thresholds, `for:` durations, severities), and the services' metrics endpoints (host, port, path) from the code or the `metrics` skill output.
2. Write `prometheus.yml`: `global` intervals (values from POLICY or ask), one `scrape_configs` job per service from the endpoint list, `rule_files`, `alerting`. Details: [references/prometheus.md](references/prometheus.md).
3. Write rules and Alertmanager config: [references/alerting.md](references/alerting.md).
4. Write Grafana provisioning and dashboards: [references/grafana.md](references/grafana.md).
5. Check (see below). Fix until clean.
6. Hand off to deploy-engineer (section below).

Checks, run from the repository root through the dev shell or one-off:

```text
nix shell nixpkgs#prometheus nixpkgs#prometheus-alertmanager -c promtool check config deploy/observability/prometheus/prometheus.yml
nix shell nixpkgs#prometheus -c promtool check rules deploy/observability/prometheus/rules/*.yml
nix shell nixpkgs#prometheus -c promtool test rules deploy/observability/prometheus/tests/*.yml
nix shell nixpkgs#prometheus-alertmanager -c amtool check-config deploy/observability/alertmanager/alertmanager.yml
```

Package names `prometheus` (promtool) and `prometheus-alertmanager` (amtool) are (U) verify with `nix search nixpkgs`. `promtool check config` also checks that files in `rule_files` exist and parse, so run it from a path where the relative `rule_files` resolve.

## Rules

### R-OBS-THRESHOLDS-FROM-POLICY — thresholds and durations come from POLICY

Bad:
```yaml
- alert: HighErrorRate
  expr: sum(rate(http_requests_total{code=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.05
  for: 10m   # numbers invented by the writer
```
Why: an invented SLO is wrong in both directions: pages for nothing or stays silent.

Good:
```yaml
# threshold 0.01 and for 5m: docs/POLICY.md#p-slo-errors
- alert: HighErrorRatio
  expr: job:http_requests_5xx:ratio_rate5m > 0.01
  for: 5m
```
If POLICY has no number: write `❓` in the report, ask, and do not commit a guess.

### R-OBS-SYMPTOM-ALERTS — alert on what users feel

Bad:
```yaml
- alert: HighCPU
  expr: node_cpu_usage > 0.7
```
Why: CPU at 70% hurts nobody; the alert trains people to ignore pages.

Good:
```yaml
- alert: HighErrorRatio      # error ratio
- alert: LatencyOverSLO      # histogram_quantile over the SLO from POLICY
- alert: TargetDown          # up == 0
- alert: DiskAlmostFull      # saturation, only with a POLICY threshold
```
Cause-style metrics (CPU, memory) go on dashboards; they alert only as saturation with a POLICY threshold.

### R-OBS-ALERT-FIELDS — every alert has for, severity, annotations

Bad:
```yaml
- alert: TargetDown
  expr: up == 0
```
Why: without `for:` one failed scrape pages; without labels and annotations routing and triage are blind.

Good:
```yaml
- alert: TargetDown
  expr: up == 0
  for: 5m                      # value from POLICY
  labels:
    severity: critical         # values from POLICY, used by Alertmanager matchers
  annotations:
    summary: "{{ $labels.job }} on {{ $labels.instance }} is down"
    description: "Target has not been scraped successfully for 5m."
    runbook: "docs/runbooks/target-down.md"
```

### R-OBS-RECORDING-FOR-EXPENSIVE — record what is queried often

Bad:
```yaml
# the same quantile expression pasted into 3 alerts and 6 panels
expr: histogram_quantile(0.99, sum by (le, job) (rate(http_request_duration_seconds_bucket[5m])))
```
Why: repeated heavy queries load Prometheus and drift apart.

Good:
```yaml
groups:
  - name: http_recording
    rules:
      - record: job:http_request_duration_seconds:p99_rate5m
        expr: histogram_quantile(0.99, sum by (le, job) (rate(http_request_duration_seconds_bucket[5m])))
```
Name: `level:metric:operations`. The metric names above must match what the service really exports.

### R-OBS-NO-INLINE-SECRETS — no tokens or webhook URLs in files

Bad:
```yaml
receivers:
  - name: ops
    webhook_configs:
      - url: "https://hooks.example.com/services/T000/B000/XXXX"
```
Why: the file is committed; the URL is a credential.

Good:
```yaml
receivers:
  - name: ops
    webhook_configs:
      - url_file: /run/secrets/alertmanager_webhook_url   # (U) verify url_file in the pinned version
```
The secret file is provided at runtime (skills `sops`, rule `secrets.md`; deploy-engineer wires it). If the pinned version has no file-based field, tell the orchestrator; do not inline. Same for Grafana admin passwords and datasource credentials.

### R-OBS-CHECKED-CONFIG — nothing is reported done unchecked

Bad:
```text
Wrote alertmanager.yml and rules. Looks right.
```
Why: a typo in a rule file only shows when the stack fails to reload.

Good:
```text
promtool check config prometheus.yml -> SUCCESS: 1 rule files found
promtool check rules rules/*.yml     -> SUCCESS: 7 rules found
amtool check-config alertmanager.yml -> Checking ... SUCCESS
```
Paste real outputs. A check tool that cannot run is `blocked`, never "skipped = passed". Non-trivial alert logic gets a `promtool test rules` case.

### R-OBS-NO-DEPLOY — write files, do not run the stack

Bad:
```text
docker compose up -d prometheus grafana   # run by the observability agent
```
Why: deployment is deploy-engineer's job through /br-deploy; two writers on one stack collide.

Good:
```text
Files written in deploy/observability/. Hand-off to deploy-engineer: ports, volumes, networks, same server or separate (see section).
```
The agent does not edit compose files, Nix modules, or CI.

### R-OBS-TARGETS-FROM-CODE — scrape what exists

Bad:
```yaml
scrape_configs:
  - job_name: app
    static_configs:
      - targets: ["app:8080"]   # guessed port, path left default
```
Why: a wrong port gives `up == 0` forever, or a silent gap.

Good:
```yaml
scrape_configs:
  - job_name: api               # port and path read from the service code / metrics skill
    metrics_path: /metrics
    static_configs:
      - targets: ["api:9464"]
```

### R-OBS-PROVISION-AS-CODE — Grafana is provisioned, not clicked

Bad:
```text
Dashboard built in the Grafana UI, never exported.
```
Why: it disappears with the volume and cannot be reviewed.

Good:
```yaml
apiVersion: 1
providers:
  - name: default
    type: file
    options:
      path: /var/lib/grafana/dashboards
```
Dashboards are JSON files with a stable `uid`; datasources are YAML with `apiVersion: 1`.

## Hand-off to deploy-engineer

Report these so deploy-engineer can wire the stack (`deploy-variants`, `docker-patterns`). Do not choose for it.

| Item | Tell it |
|---|---|
| Config files | paths of every file and where each mounts (`prometheus.yml` and `rules/`, `alertmanager.yml`, `grafana/provisioning`, `grafana/dashboards`) |
| Ports | default ports of Prometheus, Alertmanager, Grafana (U: confirm in the pinned image docs); which must be reachable from outside |
| Volumes | data directories to persist (Prometheus TSDB, Grafana data) (U: confirm paths) |
| Networks | the scrape targets' hostnames from `scrape_configs` and the network they must share with Prometheus |
| Placement | same compose and server as the app, or a separate monitoring server; for a separate server, scrape targets must be reachable across hosts (addresses, firewall, auth) and `static_configs` targets change from service names to addresses |
| Secrets | names of secret files expected at runtime (webhook URL, Grafana admin password) |
| Reload | after a config change Prometheus and Alertmanager must reload or restart (U: reload endpoint/signal needs an enabled flag; verify) |

## Reviewer checklist

- [ ] Every threshold and `for:` traces to `docs/POLICY.md`; none invented (R-OBS-THRESHOLDS-FROM-POLICY)
- [ ] Alerts are symptom-based; each has `for`, `severity`, `summary`, `description`, `runbook` (R-OBS-SYMPTOM-ALERTS, R-OBS-ALERT-FIELDS)
- [ ] Repeated heavy expressions are recording rules (R-OBS-RECORDING-FOR-EXPENSIVE)
- [ ] Scrape targets, ports, paths match the services' real endpoints (R-OBS-TARGETS-FROM-CODE)
- [ ] No inline secrets in any file (R-OBS-NO-INLINE-SECRETS)
- [ ] Real output of `promtool check config`, `promtool check rules`, `amtool check-config` is in the report (R-OBS-CHECKED-CONFIG)
- [ ] Grafana datasources and dashboards are files with stable uids (R-OBS-PROVISION-AS-CODE)
- [ ] No compose, Nix, or CI file touched; hand-off table filled (R-OBS-NO-DEPLOY)
- [ ] Fields outside the facts table are marked (U) or verified against the pinned version

## References

- [references/prometheus.md](references/prometheus.md) - prometheus.yml, scrape jobs, Docker SD
- [references/alerting.md](references/alerting.md) - rule files, recording rules, Alertmanager, tests
- [references/grafana.md](references/grafana.md) - provisioning and dashboard JSON
- Skills: `metrics`, `deploy-variants`, `docker-patterns`, `sops`
- Research: /br-research wf_35c2e079-c6c (`docs/temp/observability/research-wf_35c2e079-c6c.json`)
