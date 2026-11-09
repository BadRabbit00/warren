# Cloudflare: pitfalls

Each item: sources in brackets.

Bad:
```
wrangler d1 execute prod-db --command "SELECT count(*) FROM sessions"
```
Good:
```
wrangler d1 execute prod-db --remote --command "SELECT count(*) FROM sessions"
# without --remote the command may hit local Miniflare storage, so reads look empty and writes never reach production
```
[d1 commands](https://developers.cloudflare.com/d1/wrangler-commands/)

Bad:
```
wrangler secret put API_KEY      # deploys a new version immediately, bypassing the gradual rollout
```
Good:
```
wrangler versions secret put API_KEY   # staged: part of a version you deploy gradually
```
[wrangler skill](https://raw.githubusercontent.com/cloudflare/skills/main/skills/wrangler/SKILL.md)

Bad:
```
wrangler rollback            # after a Durable Object migration, expecting data to come back
```
Good:
```
wrangler rollback <VERSION_ID> --name <worker> --message "bad deploy"   # code only
wrangler d1 time-travel restore <DB> --bookmark <B>                     # data, separately, with «да»
```
Rollback is blocked after DO migrations or deleted bindings and never restores D1/KV/R2 data. Plan DO migrations as forward-only. [rollbacks](https://developers.cloudflare.com/workers/configuration/versions-and-deployments/rollbacks/)

Bad:
```
wrangler pages deployment delete <id>    # destructive, not a rollback
```
Good:
```
# dashboard: Pages project > Deployments > Rollback to this deployment
# or: wrangler pages deploy ./dist --project-name <name> --branch main   (previous commit checked out)
```
[pages rollbacks](https://developers.cloudflare.com/pages/configuration/rollbacks/)

Bad:
```
export CLOUDFLARE_API_TOKEN=...; wrangler whoami   # then trusting the shown identity as the stored login
```
Good:
```
# note whether CLOUDFLARE_API_TOKEN / CLOUDFLARE_API_KEY are set; they override the stored OAuth login.
# wrangler logout does not revoke a token: delete it in the dashboard.
```
[general commands](https://developers.cloudflare.com/workers/wrangler/commands/general/)

Bad:
```
wrangler login          # on SSH or in a container: waits for localhost:8976 forever
```
Good:
```
! wrangler login --device     # user runs it; CI uses an API token
```
[general commands](https://developers.cloudflare.com/workers/wrangler/commands/general/)

Bad:
```
# wrangler login done; running `cf deploy` and assuming it is logged in
```
Good:
```
cf auth whoami      # cf has its own credentials; or set CLOUDFLARE_API_TOKEN for both
```
[cf-cli skill](https://raw.githubusercontent.com/cloudflare/skills/main/skills/cf-cli/SKILL.md)

Bad:
```
cf workers delete <name> --force --delete-with-references      # --force skips the confirmation; --delete-with-references deletes the Worker even when others reference it (breaks service bindings, deletes Durable Object namespaces it implements)
```
Good:
```
cf workers delete <name> --dry-run    # preview; ask the user for «да»; non-interactive delete without --force prints "Aborted." and still exits 0
```
Flags checked in `cf workers delete --help` (`-f, --force  Skip confirmation`; `--delete-with-references`; `--dry-run`). [cf-cli skill](https://raw.githubusercontent.com/cloudflare/skills/main/skills/cf-cli/SKILL.md)
