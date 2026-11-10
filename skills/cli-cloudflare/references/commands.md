# wrangler and cf: command and flag reference

Source: `wrangler <command> --help` of wrangler 4.151.1 (checked locally); `cf` 1.0.0-beta.21 top-level help and `cf auth whoami` (checked locally); behaviour notes marked "docs" come from https://developers.cloudflare.com/workers/wrangler/commands/ and https://developers.cloudflare.com/workers/configuration/versions-and-deployments/rollbacks/ (not run).
R = allowed for log-collector / deploy-error-reader. E = deploy-engineer / ci-engineer. M = mutating.
Global flags of every wrangler command: `-c config`, `--cwd dir`, `-e env`, `--env-file`, `--profile` (not on `whoami`/`login`), `-h`, `-v`.

## Auth
| Command | Notes |
|---|---|
| `wrangler whoami` (R) | `--json` (exit non-zero when not logged in), `--account <id\|name>` |
| `wrangler login` (user only) | `--device`, `--browser=false`, `--scopes`, `--scopes-list`, `--use-keyring`, `--callback-host`, `--callback-port` (default 8976) |
| `cf auth whoami` (E) | exit 0 even when logged out: read `"authenticated"` |
| `cf auth login` (user only) | `--no-browser`, `--force` (docs) |

## Workers
| Command | Flags that matter |
|---|---|
| `wrangler tail [worker]` (R) | `--format json\|pretty`, `--status ok\|error\|canceled`, `--method`, `--header`, `--ip` (`self`), `--search`, `--version-id`, `--sampling-rate`. Streams: use `timeout` |
| `wrangler deployments list` (E) | `--name`, `--json`. 10 most recent |
| `wrangler deployments status` (E) | `--name`, `--json`. Current production state |
| `wrangler versions list` (E) | `--name`, `--json`. 10 most recent |
| `wrangler versions view <id>` (E) | `--name`, `--json` |
| `wrangler secret list` (E) | `--name`, `--format json\|pretty` (default json). Names only |
| `wrangler deploy [path]` (M) | `--name`, `--tag`, `--message`, `--dry-run`, `--keep-vars`, `--secrets-file`, `--strict`, `--latest`, `--var`, `--routes`, `--domains`, `--containers-rollout immediate\|gradual\|none`. Without `--keep-vars` vars are replaced by the config |
| `wrangler versions upload [path]` (M) | `--tag`, `--message`; the version is not live |
| `wrangler versions deploy [id@pct%..]` (M) | `-y`, `--message` (docs for the `id@pct%` form) |
| `wrangler rollback [version-id]` (M) | `--name`, `-m/--message`, `-y`, `--durable-objects-code-update-mode`. No id = previous version (docs) |
| `wrangler secret put <key>` (M) | `--name`; value from stdin; live at once (docs) |

## Pages
| Command | Flags |
|---|---|
| `wrangler pages project list` (E) | `--json` |
| `wrangler pages deployment list` (E) | `--project-name`, `--environment`, `--json` (docs) |
| `wrangler pages deployment tail [deployment]` (E) | `--project-name`, `--environment production\|preview`, `--status`, `--method`, `--search`, `--sampling-rate` (docs). Streams: use `timeout` |
| `wrangler pages deploy [dir]` (M) | `--project-name`, `--branch` (docs) |

## D1, KV, R2, Hyperdrive
| Command | Flags / notes |
|---|---|
| `wrangler d1 list` (E) | `--json`. Acts on remote databases |
| `wrangler d1 info <name>` (E) | `--json`. Acts on remote databases |
| `wrangler d1 migrations list <db>` (E) | `--local`, `--remote`, `--preview`, `--persist-to` |
| `wrangler d1 time-travel info <db>` (E) | `--timestamp <unix\|RFC3339>`, `--json`. Remote |
| `wrangler d1 execute <db>` (E for SELECT, else M) | `--command` or `--file`, `--local`, `--remote`, `--preview`, `-y`, `--json`, `--persist-to` |
| `wrangler d1 migrations apply <db>` (M) | `--local`, `--remote`, `--preview`; asks to confirm |
| `wrangler d1 time-travel restore <db>` (M) | `--bookmark` or `--timestamp` (within 30 days), `--json` |
| `wrangler kv namespace list` (E) | no flags |
| `wrangler kv key list` (E) | `--binding` or `--namespace-id`, `--prefix`, `--preview`, `--local`, `--remote`, `--persist-to` |
| `wrangler kv key get <key>` (E, value may be secret) | `--text`, `--binding`, `--namespace-id`, `--preview`, `--local`, `--remote` |
| `wrangler r2 bucket list` (E) | `-J/--jurisdiction` |
| `wrangler r2 bucket info <bucket>` (E) | `-J`, `--json` |
| `wrangler hyperdrive list` (E) | listed in the wrangler help; flags not verified. `hyperdrive create` takes a connection string with a password: M, never echoed |

## cf (beta)
Huge API wrapper. Verified: `cf auth whoami|login|list`, `cf docs search`, `cf schema [command..]` (`--list`), `cf workers list|get|deployments|versions`. Discovery: `cf cli search "<task>"` returns five JSON matches; `cf schema <path>` shows API details; `--dry-run` shows a command without running it; global `-z zone`, `--profile`, `-q`. Run `--help` first; other commands: not verified.

## Environment
`CLOUDFLARE_API_TOKEN` (overrides a stored login), `CLOUDFLARE_ACCOUNT_ID` (docs). Legacy `CLOUDFLARE_API_KEY` + `CLOUDFLARE_EMAIL` (docs).

## Official sources
- https://developers.cloudflare.com/workers/wrangler/commands/general/
- https://developers.cloudflare.com/workers/wrangler/commands/workers/
- https://developers.cloudflare.com/workers/wrangler/commands/pages/
- https://developers.cloudflare.com/d1/wrangler-commands/
- https://developers.cloudflare.com/kv/reference/kv-commands/
- https://developers.cloudflare.com/r2/reference/wrangler-commands/
- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/rollbacks/
- https://developers.cloudflare.com/pages/configuration/rollbacks/
- Official agent skills (Apache-2.0): https://github.com/cloudflare/skills
