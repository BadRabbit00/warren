# Railway: pitfalls

Bad:
```
export RAILWAY_TOKEN=<project token>; railway whoami      # Unauthorized: whoami, link, list, add --repo are account-level
```
Good:
```
railway status --json                          # project-scoped read with a project token
RAILWAY_API_TOKEN=<account token> railway whoami   # only when an account token is really needed
```
[source](https://station.railway.com/questions/cli-throwing-unauthorized-with-railway-24883ba1)

Bad:
```
railway up --detach --json && echo deployed
```
Good:
```
railway up --ci --service api --environment production
railway deployment list --service api --environment production --json    # confirm the status
```
`--detach --json` returns before the deployment is healthy. [source](https://docs.railway.com/cli/up)

Bad:
```
railway redeploy        # "rollback": it rebuilds
```
Good:
```
railway deployment list --service api --json     # find the last good deployment id
# dashboard: Deployments > last good > Rollback   (or railway api with deploymentRollback, after the user's «да»)
```
[source](https://railway.com/guides/roll-back-bad-deploy.md)

Bad:
```
# railway.toml in a new service, expecting it to be applied
```
Good:
```
railway config pull                   # import the linked project into .railway/railway.ts
railway config plan --detailed-exit-code    # gate in CI; apply by a human
```
Old files have no effect on new services and are ignored by everyone after 2026-12-01. [source](https://station.railway.com/questions/railway-toml-has-no-effect-what-replac-b623aa81)

Bad:
```
export RAILWAY_TOKEN=<project token>; tofu plan      # provider reads RAILWAY_TOKEN but needs an account/workspace token
```
Good:
```
TF_VAR_railway_token=<account token> tofu plan       # provider "railway" { token = var.railway_token }
```
[source](https://raw.githubusercontent.com/terraform-community-providers/terraform-provider-railway/master/docs/index.md)

Bad:
```
# preDeployCommand: sqlite3 /data/app.db < migrate.sql      # volume is not mounted yet
```
Good:
```
# startCommand: sh -c "sqlite3 /data/app.db < migrate.sql && exec ./app"   # volume is mounted at start
```
[source](https://docs.railway.com/volumes)

A service with an attached volume cannot use replicas or scale to zero; deploys fail when the replica count is above 1. Keep one replica for volume-backed services, back up before removing a volume. (`railway down --service <svc> --environment <env>` removes the latest deployment, so the service goes down: only after the user's «да».) [source](https://station.railway.com/questions/service-stuck-at-2-replicas-with-an-atta-70a44553)

Bad:
```
railway variable list --service api --json      # raw values land in the log
railway variable set API_KEY=<value>            # value in argv and shell history
```
Good:
```
<protected source> | railway variable set API_KEY --stdin --skip-deploys --json   # value arrives on stdin
```
`railway variable` output contains secrets; the JSON list includes raw values (from `railway variable --help` of 5.30.4). [source](https://docs.railway.com/cli/deployment)
