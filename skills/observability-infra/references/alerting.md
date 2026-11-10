# Rules and Alertmanager

Facts (research wf_35c2e079-c6c): rule files are `groups` -> `rules`. Alert rule keys: `alert`, `expr`, `for`, `keep_firing_for`, `labels`, `annotations`. Recording rule keys: `record`, `expr`, `labels`. Secret fields (follow-up wf_340d5dfb-77e): see the facts table in `../SKILL.md`. Alertmanager: `route` (`receiver`, `group_by`, `group_wait`, `group_interval`, `repeat_interval`, `routes` with `matchers`), `receivers` (e.g. `webhook_configs`), optional `inhibit_rules`. Checks: `promtool check rules`, `promtool test rules`, `amtool check-config`.

## Rule file

```yaml
groups:
  - name: api_alerts
    rules:
      - alert: HighErrorRatio
        expr: job:http_requests_5xx:ratio_rate5m > 0.01   # from POLICY
        for: 5m                                            # from POLICY
        labels:
          severity: critical
        annotations:
          summary: "Error ratio above SLO for {{ $labels.job }}"
          description: "5xx ratio is {{ $value | humanizePercentage }}."
          runbook: "docs/runbooks/high-error-ratio.md"
```

Template functions such as `humanizePercentage` and `$value` are (U) verify in the pinned version.

## Alert catalogue

| Alert | Sketch | Needs from POLICY |
|---|---|---|
| Error ratio | 5xx rate / total rate | threshold, `for` |
| Latency over SLO | `histogram_quantile` over `_bucket` series | quantile, limit, `for` |
| Target down | `up == 0` | `for` |
| Saturation | disk / queue / pool usage ratio | threshold, `for` |

Metric names depend on what the services export (OpenTelemetry semantic names versus custom): read them from the code or the `metrics` skill. Do not assume.

## Recording rules

Use for expressions that several alerts or panels share, or that are heavy. Name `level:metric:operations`. Rule group evaluation order is not guaranteed across groups: put a recording rule and the alert that uses it in the same group, or accept one interval of delay (U) verify.

## Alertmanager

```yaml
route:
  receiver: ops
  group_by: ["alertname", "job"]
  group_wait: 30s          # values from POLICY or ask
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - severity="critical"
      receiver: ops
receivers:
  - name: ops
    webhook_configs:
      - url_file: /run/secrets/alertmanager_webhook_url   # (R) file with the URL
inhibit_rules: []
```

- Route on the `severity` label values defined in POLICY.
- Secrets are files provided at runtime, never inline. File fields (R): `webhook_configs.url_file`; `slack_configs.api_url_file` / `app_token_file`; `telegram_configs.bot_token_file` / `chat_id_file`; `pagerduty_configs.routing_key_file` / `service_key_file`; `opsgenie_configs` and `victorops_configs` `api_key_file`; `pushover_configs.user_key_file` / `token_file`; `email_configs.auth_password_file` / `auth_secret_file`; `webhook_url_file` for discord, mattermost, msteams; in any `http_config`: `authorization.credentials_file`, `basic_auth.password_file`, `oauth2.client_secret_file`. Global counterparts exist (`slack_api_url_file`, `smtp_auth_password_file`, `telegram_bot_token_file`, ...).
- The file content is the bare secret; Alertmanager 0.35 trims whitespace for `token_file` and `user_key_file` (pushover) only, so write the file without a trailing newline for the others (U: not checked per field).
- Other receiver kinds are (U) verify in the pinned version's docs.

## Tests

`promtool test rules tests/*.yml` feeds synthetic series and asserts which alerts fire. Test file schema is (U) verify against the pinned version; write one case for each alert with non-trivial logic.

## Checks

```text
promtool check rules rules/*.yml
amtool check-config alertmanager.yml
```
