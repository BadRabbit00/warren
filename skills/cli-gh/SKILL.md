---
name: cli-gh
description: Use when you must read GitHub Actions state (runs, failed-step logs, PR checks, workflow files, releases, check-run annotations) with the gh CLI, or hand off a rerun/dispatch to ci-engineer.
---

# gh (GitHub CLI): CI state and logs

Verified locally with gh 2.103.3 (`--help` of every command below). Full flag tables: `references/commands.md`.
Who: `R` = allowed for `log-collector` and `deploy-error-reader` (hook allowlist: `gh auth status`, `gh run list`, `gh run view`). `E` = read-only, but only for `deploy-engineer` / `ci-engineer` (the readers' hook denies it).

## 1. Run

Always `nix shell nixpkgs#gh -c gh <args>`. Never a bare `gh`, never `brew`, `npm i -g`, or an install script piped into a shell.
Pick the repo with `-R owner/repo` (or run inside the clone: the git remote decides).

## 2. Login check FIRST

```
nix shell nixpkgs#gh -c gh auth status
```
- exit 0 and `Logged in to github.com account <name>` = ok. The token is masked; never add `--show-token`.
- exit 1 or "not logged in" = stop. Do not try other commands.
- exit 4 on any later command = the command needs authentication: same stop.

Not logged in: report `STATUS: blocked — login needed` and give the user this one command:
`! nix shell nixpkgs#gh -c gh auth login --web`
CI or token mode: gh reads the env var `GH_TOKEN` (or `GITHUB_TOKEN`); in Actions `GH_TOKEN: ${{ github.token }}`. Check that it is set with `test -n "$GH_TOKEN"`; never print it.

## 3. Read-only commands

### Why did the CI run fail (R)
```
# 1. find the run: never guess the id
nix shell nixpkgs#gh -c gh run list --branch <branch> --limit 5 --json databaseId,conclusion,status,name,headSha,createdAt -R owner/repo
# 2. which job and step failed
nix shell nixpkgs#gh -c gh run view <id> --json jobs --jq '.jobs[] | select(.conclusion=="failure") | {name, databaseId, steps: [.steps[] | select(.conclusion=="failure") | .name]}' -R owner/repo
# 3. only the failed steps' log, bounded, with line numbers
nix shell nixpkgs#gh -c gh run view <id> --log-failed -R owner/repo | tail -n 200 | cat -n
# one job only
nix shell nixpkgs#gh -c gh run view <id> --job <jobId> --log-failed -R owner/repo | tail -n 200
```
- `--attempt N` picks a rerun attempt; `--exit-status` makes the exit code non-zero when the run failed.
- Filters of `run list`: `-w <workflow>`, `-s failure` (or `success`, `in_progress`, ...), `-e push`, `-c <sha>`, `-u <user>`.

### What ran last / what is deployed now (R)
```
nix shell nixpkgs#gh -c gh run list --limit 10 --json databaseId,status,conclusion,name,headBranch,event -R owner/repo
nix shell nixpkgs#gh -c gh run list -w deploy.yml --branch main --limit 3 --json databaseId,conclusion,headSha,createdAt -R owner/repo
```

### Checks of a PR (E)
```
nix shell nixpkgs#gh -c gh pr checks <pr> --json name,bucket,state,workflow,link -R owner/repo
nix shell nixpkgs#gh -c gh pr view <pr> --json statusCheckRollup,headRefName,mergeable -R owner/repo
```
`bucket` is one of pass, fail, pending, skipping, cancel. `gh pr checks` exits 8 while checks are pending.
Do not use `--watch` (blocks): poll, or use `gh run watch` under `timeout`.

### Annotations: the exact failing line of a check (E)
```
nix shell nixpkgs#gh -c gh api "repos/{owner}/{repo}/commits/<sha>/check-runs" --jq '.check_runs[] | {id, name, conclusion}'
nix shell nixpkgs#gh -c gh api "repos/{owner}/{repo}/check-runs/<check_run_id>/annotations" --jq '.[] | {path, start_line, annotation_level, message}'
```
`{owner}` and `{repo}` are filled from the current clone. `gh api` defaults to GET: never pass `-X POST/PUT/PATCH/DELETE`, `-f`, `-F`, `--input` (they send data).

### Workflows, releases, artifacts (E)
```
nix shell nixpkgs#gh -c gh workflow list --json id,name,path,state -R owner/repo
nix shell nixpkgs#gh -c gh workflow view <file.yml> --yaml --ref <branch> -R owner/repo
nix shell nixpkgs#gh -c gh release list --limit 5 --json tagName,publishedAt,isPrerelease -R owner/repo
nix shell nixpkgs#gh -c gh release view <tag> --json tagName,assets,publishedAt -R owner/repo
nix shell nixpkgs#gh -c gh run download <id> -n <artifact> -D <tmpdir> -R owner/repo
```
`run download` writes files: only into a temp dir that you name.

## 4. Mutating commands: only deploy-engineer / ci-engineer, only after the user's «да» for this command (prod: «да» per command)

Readers never run these (the hook denies them). A reader that thinks one is needed reports it to the orchestrator.
```
nix shell nixpkgs#gh -c gh run rerun <id> --failed -R owner/repo     # failed jobs only; -d adds debug logging
nix shell nixpkgs#gh -c gh run rerun <id> -j <jobId> -R owner/repo
nix shell nixpkgs#gh -c gh run cancel <id> -R owner/repo
nix shell nixpkgs#gh -c gh workflow run <file.yml> --ref <branch> -f key=value -R owner/repo
timeout 600 nix shell nixpkgs#gh -c gh run watch <id> --exit-status --compact -R owner/repo   # blocks: always under timeout
```
Rerun only after the cause is understood and the user asked: a blind rerun of a flaky-looking failure hides the cause.

## 5. Patterns and anti-patterns

Bad: `gh run view <id> --log` (whole log: thousands of lines flood the context)
Good: `gh run view <id> --log-failed | tail -n 200`

Bad: guess or reuse a run id from memory
Good: `gh run list --branch <b> --limit 5 --json databaseId,conclusion,name`

Bad: `gh run view` without an id (opens an interactive picker and hangs)
Good: always pass the id and `--json`; `GH_PROMPT_DISABLED=1` is a safety net

Bad: `gh run watch <id>` with no timeout (blocks the agent)
Good: `timeout 600 nix shell nixpkgs#gh -c gh run watch <id> --exit-status --compact`

Bad: `gh auth status --show-token`, `gh auth token`, `env`, `echo $GH_TOKEN`
Good: `gh auth status`; `test -n "$GH_TOKEN"`

Bad: table output parsed with grep/awk
Good: `--json fields --jq '<filter>'` (field names are at the end of `gh run list --help`)

Bad: no repo when you are outside a clone
Good: `-R owner/repo` on every command

## 6. Report shape (collectors)

Put in the report:
- source: `gh run view`, repo, run id, job id, attempt, head sha, branch
- the exact command line and its exit code
- the failing step name and the log excerpt (at most ~40 lines) with line numbers (`cat -n`) and the time range of the excerpt
- the annotation list (path:line, message) when present

Do not put in the report:
- the whole log, or the output of `--log`
- tokens, the token line of `gh auth status`, secrets seen in a log (write `<redacted>`)
- guesses about the cause: write "observed" lines only; a cause is a hypothesis, labelled as one
