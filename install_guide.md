# Install guide

How to put warren into Claude Code without Nix. Two ways: the script (recommended) or by hand.
Both give the same result. First install what [requirements.md](requirements.md) lists — at least
Claude Code, Python 3.11+ and Git.

## With the script

From the repository root:

```bash
python3 tools/install.py --dry-run   # shows every file it would write, changes nothing
python3 tools/install.py             # installs into your home directory
python3 tools/install.py --check     # optional: runs the validator and both test suites
```

The same commands work on Windows: the hooks are called as `python3`, so that command must start
Python 3.11+ there too. Re-run the same command after `git pull` to update. `--dest <dir>` installs
into another home directory (useful for a trial run: `python3 tools/install.py --dest /tmp/warren-home`).

What it does:

1. Builds the payload into a temporary directory with `tools/build.py` (subagent contract and
   model pins injected into every agent, Codex and agy exports generated).
2. Copies into your home directory:

   | From the build | To |
   |---|---|
   | `claude/CLAUDE.md` | `~/.claude/CLAUDE.md` (a different existing file is kept as `CLAUDE.md.bak-<timestamp>`) |
   | `claude/agents`, `skills`, `commands`, `workflows`, `output-styles` | same names under `~/.claude/` (files with the same name are replaced, your other files stay) |
   | `claude/rules/br`, `claude/br/templates`, `claude/br/hooks` | same paths under `~/.claude/` (these directories are replaced as a whole) |
   | `codex/agents`, `prompts`, `skills`, `AGENTS.md`, `agents.toml` | `~/.codex/` (a different existing `AGENTS.md` is backed up the same way) |
   | `agy/agents`, `AGENTS.md` | `~/.gemini/config/` (same backup rule) |

   Before deleting or writing anything it checks every target. A target it cannot replace stops
   the run with a message and nothing changed. Symlinks left by an earlier install (for example
   home-manager links into a read-only store) are replaced by regular files. It records what it
   installed in `~/.claude/br/manifest.json`; the next run removes files it installed before that
   the new version no longer ships (your own files are never touched).

3. Merges `~/.claude/settings.json`: your keys stay; `env` and `outputStyle` from
   `settings.fragment.json` are added; hooks whose `id` starts with `br:` are replaced, your other
   hooks stay. Each warren hook runs as
   `"python3" -I -B "~/.claude/br/hooks/<entry>.py"`, the same command on Windows, macOS and
   Linux. Before writing anything the script checks that `python3` is on `PATH` and is 3.11+;
   otherwise it stops and changes nothing. A malformed `settings.json` stops the run with
   `settings.json: <reason>` and nothing written.

Restart Claude Code afterwards; the orchestrator output style is active from the next session.

## By hand (what Claude does when asked to install without the script)

1. Build: `python3 tools/build.py <out> <repo root> python3` — for example
   `python3 tools/build.py /tmp/warren-build . python3`.
2. Copy the directories from `<out>` exactly as in the table above.
3. Edit `~/.claude/settings.json`:
   - add the `env` keys and `outputStyle` from `<out>/settings.fragment.json`;
   - add the hook entries from `<out>/hooks.json` (each has an `id` starting with `br:`), replacing
     earlier `br:` entries and keeping every other hook;
   - in each added command, replace the build path `<out>/claude/br/hooks/` with the absolute
     path of `~/.claude/br/hooks/` (the build writes its own output path there).
4. Check: start Claude Code, run `/agents` — the warren agents (`researcher`, `coder`,
   `test-writer`, …) are listed; ask for a write outside a task in an orchestrated project — the
   hook refuses it.

## Uninstall

Remove the files listed in `~/.claude/br/manifest.json`, then `~/.claude/rules/br` and
`~/.claude/br`, the `br:` hooks and the warren `env`/`outputStyle` keys in
`~/.claude/settings.json`, and restore your own `CLAUDE.md` / `AGENTS.md` from the newest
`.bak-<timestamp>` file.
