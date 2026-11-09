# DigitalOcean: pitfalls

Bad:
```
doctl apps update <app id> --spec app.yaml      # spec has image tag :latest, the tag is unchanged
```
Good:
```
# tag images with the commit SHA, set that tag in the spec, then:
doctl apps update <app id> --spec app.yaml --wait
doctl apps create-deployment <app id> --wait      # always deploys the current image
```
`doctl apps update` does not redeploy an unchanged tag; deploy_on_push compares digests. [source](https://docs.digitalocean.com/products/container-registry/quickstart/)

Bad:
```
DIGITALOCEAN_CONTEXT=prod doctl account get       # with DIGITALOCEAN_ACCESS_TOKEN set: the env token is ignored for named contexts
doctl auth init                                   # in CI: overwrites the stored default token
```
Good:
```
DIGITALOCEAN_ACCESS_TOKEN=<from CI secret> doctl apps list      # default context, env var only
```
[source](https://github.com/digitalocean/doctl)

Bad:
```
curl -X POST .../v2/apps/<id>/rollback -d '{"deployment_id":"<id>"}'    # then forget it: the app stays pinned
```
Good:
```
# validate first: POST /v2/apps/<id>/rollback/validate
# after checking: POST .../rollback/commit (or /rollback/revert); or pass "skip_pin": true to commit at once
```
A pinned rollback blocks new deployments and deploy-on-push. [source](https://docs.digitalocean.com/reference/pydo/reference/apps/validate_rollback/)

Bad:
```
# rolling the app back after a destructive migration and assuming data is back
```
Good:
```
# expand/contract migrations; restore data into a new cluster:
doctl databases create <new> --engine pg --restore-from-cluster-name <src> --restore-from-timestamp '2026-11-09 10:00:00 +0000 UTC'
```
[source](https://docs.digitalocean.com/products/app-platform/how-to/manage-deployments/)

Bad:
```
doctl databases connection <cluster-id>      # 1.169.0: Password column, no masking flag: password in the log
```
Good:
```
# app spec: DATABASE_URL: ${db.DATABASE_URL}   (bindable variable, never printed)
```
[source](https://docs.digitalocean.com/reference/doctl/reference/databases/connection/)

Bad:
```
doctl apps create --spec app.yaml --wait      # no bound: the job hangs, or a killed job hides a deployment still running
```
Good:
```
timeout 1800 doctl apps create --spec app.yaml --wait      # outer timeout (--wait-timeout is 2.x only, not in 1.169.0)
doctl apps get-deployment <app id> <deployment id>      # after a timeout, read the real state
```
[source](https://docs.digitalocean.com/reference/doctl/reference/apps/create/)

Bad:
```
envs: [{ key: DATABASE_URL, value: "postgres://user:hunter2@host/db", type: SECRET }]     # plaintext secret committed in the spec
```
Good:
```
envs: [{ key: DATABASE_URL, value: "${db.DATABASE_URL}", type: SECRET }]    # bindable variable; other secrets injected at deploy time
```
`doctl apps spec get` returns encrypted values for SECRET envs, so a round trip changes them. [source](https://docs.digitalocean.com/products/app-platform/reference/app-spec/)

Bad:
```
nix shell nixpkgs#terraform -c terraform plan      # unfree
```
Good:
```
nix shell nixpkgs#opentofu -c tofu plan
```
[source](https://search.nixos.org/packages?channel=unstable&query=terraform)
