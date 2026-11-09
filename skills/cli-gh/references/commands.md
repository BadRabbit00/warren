# gh: command and flag reference

Source: `gh <command> --help` of gh 2.103.3 (checked locally). Every command takes `-R, --repo [HOST/]OWNER/REPO`.
R = allowed for log-collector / deploy-error-reader. E = deploy-engineer / ci-engineer.

## Auth (R)
| Command | Notes |
|---|---|
| `gh auth status` | exit 1 on auth problems. `-h <host>`, `--active`, `--json hosts` (exit 0 even if broken), `--no-refresh`. Never `-t/--show-token`. |

## Runs
| Command | Flags that matter |
|---|---|
| `gh run list` (R) | `-b branch`, `-c sha`, `-e event`, `-s status`, `-u user`, `-w workflow`, `-a` (include disabled), `-L limit` (default 20), `--created date`, `--json`, `-q jq` |
| `gh run view [id]` (R) | `--log-failed`, `--log`, `-j jobId`, `-a attempt`, `-v` (steps), `--exit-status`, `--json`, `-q`; `-w` opens a browser: do not use |
| `gh run watch [id]` (E) | `--compact`, `--exit-status`, `-i seconds` (default 3) |
| `gh run download [id]` (E) | `-n name`, `-p glob`, `-D dir` |
| `gh run rerun [id]` (mutating) | `--failed`, `-j jobId`, `-d` |
| `gh run cancel [id]` (mutating) | `--force` |

JSON fields of `run list`: attempt, conclusion, createdAt, databaseId, displayTitle, event, headBranch, headSha, name, number, startedAt, status, updatedAt, url, workflowDatabaseId, workflowName.
`run view` adds `jobs` (each job has steps with name, conclusion, number).

## Workflows
| Command | Flags |
|---|---|
| `gh workflow list` (E) | `-a`, `-L` (default 50), `--json id,name,path,state` |
| `gh workflow view <id\|name\|file>` (E) | `-y/--yaml`, `-r/--ref` |
| `gh workflow run <id\|name\|file>` (mutating) | `-r ref`, `-f key=value`, `-F key=value`, `--json` (inputs from stdin) |

## Pull requests
| Command | Flags |
|---|---|
| `gh pr checks [n\|url\|branch]` (E) | `--json bucket,completedAt,description,event,link,name,startedAt,state,workflow`, `--required`, `--watch` (blocks), `--fail-fast`, `-i` |
| `gh pr view [n]` (E) | `--json`, `-c` comments |
| `gh pr list` (E) | `-H head`, `-B base`, `-s open\|closed\|merged\|all`, `-A author`, `-L` (default 30), `--json` |

## API (E)
`gh api <endpoint>`: GET by default. `--jq`, `--paginate` (+ `--slurp`), `-i` (headers), `--cache 60s`, `-H`. Placeholders `{owner}`, `{repo}`, `{branch}` come from the clone.
Endpoints checked with gh 2.103.3 against a public repo (cli/cli):
- `repos/{owner}/{repo}/commits/<sha>/check-runs`
- `repos/{owner}/{repo}/check-runs/<id>/annotations`
Sending flags (mutating): `-X`, `-f/--raw-field`, `-F/--field`, `--input`.

## Releases, caches, repo (E)
| Command | Flags |
|---|---|
| `gh release list` | `-L` (default 30), `--exclude-drafts`, `--exclude-pre-releases`, `--json` |
| `gh release view [tag]` | `--json apiUrl,assets,body,createdAt,isDraft,isPrerelease,name,publishedAt,tagName,url,...` |
| `gh cache list` | `-k key-prefix`, `-r ref`, `-S sort`, `-L`, `--json` |
| `gh repo view` | `--json`, `-b branch` |

## Exit codes (`gh help exit-codes`)
0 ok, 1 failed, 2 cancelled, 4 needs authentication, 8 (`pr checks`) pending.

## Environment (`gh help environment`)
`GH_TOKEN`, `GITHUB_TOKEN` (in that order), `GH_HOST`, `GH_REPO`, `GH_PROMPT_DISABLED`, `GH_PAGER`, `NO_COLOR`, `GH_NO_UPDATE_NOTIFIER`.
