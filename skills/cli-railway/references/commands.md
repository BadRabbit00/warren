# railway: command and flag reference

Source: `railway <command> --help` of railway 5.30.4 (checked locally); rows marked "docs" come from https://docs.railway.com and were not run.
R = allowed for log-collector / deploy-error-reader (intended). E = deploy-engineer / ci-engineer. M = mutating.

## Auth
| Command | Notes |
|---|---|
| `railway whoami` (R) | `--json`. Exit 1 + `Unauthorized…` when logged out. Prints the email: report yes/no only. Not answerable with a project token. |
| `railway login` (user) | `--browserless/-b` = device code (docs). Credentials in `~/.railway/config.json` (docs). |

## Logs and state
| Command | Flags that matter |
|---|---|
| `railway logs [DEPLOYMENT_ID]` (R) | `-s service`, `-e env`, `-p project`; type: `-d` (deployment), `-b` (build), `--http`, `--network`, `--dns`; bound: `-n/--lines N` (alias `--tail`), `-S/--since`, `-U/--until` (all three disable streaming); `-f/--filter "<query>"`; `--latest`; `--json` |
| `railway status` (R) | `-p`, `-e`, `--json`. Explicit `--project` requires `--environment`. |
| `railway deployment list` (R) | `-s`, `-e`, `-p`, `--limit N` (default 20, max 1000), `--json` |
| `railway list` (E) | `--json`. Lists projects: needs an account token. |
| `railway metrics` (E) | `-s`, `-a` (all services), `-e`, `-p`, `-S/--since` (default 1h), `-U/--until`, `--json`, `--cpu`, `--memory`, `--network`, `--volume`, `--http` (+ `--method`, `--path`), `--raw`; `-w/--watch` is a TUI: do not use |
| `railway variable list` (secret) | `-s`, `-e`, `-p`; `-k/--kv` and `--json` print raw values. Never for readers. |
| `railway api` (E for schema, M for queries) | subcommands `schema`, `search`, `describe`; options `-f file`, `--variables`, `--var`, `--raw-var`, `--operation-name`, `--compact`, `--allow-errors` |

### Log filter syntax (`railway logs --filter`, from help)
- Deploy/build logs: text `"error message"`, level `@level:error|warn|info`.
- HTTP logs: `@httpStatus:>=400`, `@path:/api`, `@method:GET`, `@totalDuration:>1000`, range `@httpStatus:200..299`; typed flags `--method`, `--status`, `--path`, `--request-id` (HTTP only).
- Network logs: `--protocol tcp|udp|icmp|icmpv6|unknown`, `--direction ingress|egress`, `--peer`, `--peer-kind`, `--dropped true|false`, `--port`, `--src`, `--dst`, `--host`, `--drop-cause`; `--status ok|dropped`.
- DNS logs: `--domain`, `--qname`, `--qtype`, `--rcode`, `--zone internal|external`; `--status ok|failed`.
- Operators: `AND`, `OR`, `-` (negation), parentheses.

## Mutating (M)
| Command | Flags |
|---|---|
| `railway up [PATH]` | `-d/--detach` (alias `--no-wait` in help text), `-y`, `-c/--ci` (build logs only, then exit), `-s`, `-e`, `-p`, `-w`, `--new`, `--name`, `--no-gitignore`, `--path-as-root`, `--verbose`, `--json` (implies CI mode), `-m/--message` |
| `railway redeploy` | `-s`, `-e`, `-p`, `-y`, `--json`, `--from-source` |
| `railway restart` | `-s`, `-e`, `-p`, `-y`, `--json` |
| `railway down` | `-s`, `-e`, `-p`, `-y` (removes the most recent deployment) |
| `railway link` | `-p`, `-e`, `-s`, `-w`, `--json` (docs) |
| `railway add` | `--database postgres\|mysql\|redis\|mongo`, `--service`, `--repo`, `--branch`, `--image`, `--json` (docs); non-interactive runs must pass one of them |
| `railway volume` | `list\|add\|delete\|update\|attach\|detach\|files\|browse` (docs), e.g. `volume add --service api --mount-path /data --json` |
| `railway config` | `init`, `pull`, `plan [--detailed-exit-code]` (0 no changes, 2 pending), `apply --yes --confirm-destructive`, `migrate --apply` (docs; the subcommand exists in 5.30.4) |
| `railway service`, `railway environment` | present in the command list; flags not verified: run `--help` |

## Environment and tokens (docs)
- `RAILWAY_TOKEN`: project token (one project + one environment; deploy, redeploy, logs). `RAILWAY_API_TOKEN`: account/workspace token (`whoami`, `link`, `list`, `init`).
- CI recipe: `RAILWAY_TOKEN=<project token> nix shell nixpkgs#railway -c railway up --ci --service <svc> --environment <env>`. Official image `ghcr.io/railwayapp/cli:latest`.
- Public GraphQL API: `https://backboard.railway.com/graphql/v2`; header `Authorization: Bearer <token>` (account tokens) or `Project-Access-Token: <token>` (project tokens).

## Sources
- https://docs.railway.com/reference/cli-api
- https://docs.railway.com/cli/logs , /cli/up , /cli/deploying , /cli/link , /cli/config
- https://railway.com/guides/roll-back-bad-deploy.md
- https://docs.railway.com/volumes , /databases/postgresql , /databases/redis
