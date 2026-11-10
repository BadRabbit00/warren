# Grafana provisioning

Facts (research wf_35c2e079-c6c): Grafana reads YAML from `provisioning/datasources` and `provisioning/dashboards`. Datasources file: `apiVersion: 1` plus a `datasources` list. Dashboards file: `providers` list with `type: file` and `options.path`. Dashboard JSON fields: `uid`, `title`, `tags`, `panels`, `templating`, `time`, `schemaVersion`, `version`, `refresh`. Full provisioning paths inside the container (`/etc/grafana/provisioning`) and per-field details are (U) verify.

## Datasource

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy                  # (U) verify
    url: http://prometheus:9090    # (U) port; host depends on same server vs separate
    isDefault: true
```

Credentials, if any: files or environment provided at runtime, never inline (R-OBS-NO-INLINE-SECRETS). How Grafana reads them (env substitution in provisioning) is (U) verify.

## Dashboard provider

```yaml
apiVersion: 1
providers:
  - name: default
    type: file
    options:
      path: /var/lib/grafana/dashboards   # mount grafana/dashboards here; tell deploy-engineer
```

## Dashboard JSON

- Set a stable `uid` and `title`; keep `version` consistent when exporting.
- Panels query the recorded series (`job:...`) where recording rules exist.
- `templating` for `job` / `instance` variables; `time` and `refresh` as defaults.
- Start from the four golden-signal panels: request rate, error ratio, latency quantile, saturation.
- Write JSON by hand or export from a throwaway local Grafana and commit the file; never leave a dashboard only in the UI.
- JSON syntax check: any JSON parser (`jq . file.json` via `nix shell nixpkgs#jq`). Grafana has no offline schema check in the research: schema validity is (U) verify; first load happens at deployment.
