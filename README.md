# warren — orchestrator and subagents for Claude Code

warren is a Claude Code configuration layer: one **orchestrator** output style for the main session and a
set of narrow, isolated **subagents** that do the actual work (research, tests, code, refactoring,
review, slides), plus path-scoped rules, skills, Python hooks and templates. It is installed
declaratively through Nix from the `nixos-conf` repository; nothing here is meant to be copied by hand.

Language: everything in this repository is **English** (cheaper in tokens, models follow it more
precisely). Everything the agents say **to the user** is **Russian**; that is stated in the output
style and in the subagent contract.

## Layout

```
.
├── core/
│   ├── CLAUDE.md                # always-on core for the MAIN session → ~/.claude/CLAUDE.md
│   └── subagent-contract.md     # injected into EVERY agent right after its frontmatter at build time
├── output-styles/orchestrator.md  # the orchestrator; main session only, subagents never see it
├── agents/                      # 23 subagents → ~/.claude/agents/
├── rules/                       # 16 path-scoped rules → ~/.claude/rules/br/
├── skills/                      # 37 skills → ~/.claude/skills/
├── commands/                    # 23 slash commands → ~/.claude/commands/
├── templates/                   # PLAN.md, POLICY.defaults.md, slides.html → ~/.claude/br/templates/
├── hooks/                       # Python hooks (guard_*.py, check_*.py), hooks.json, tests
├── tools/                       # validate.py (structure checks), measure_tokens.py, tests
├── agent-models.json            # pinned model + effort per agent for Claude, Codex and agy; the build writes them into the exports
├── settings.fragment.json       # merged into ~/.claude/settings.json (env, outputStyle)
├── _templates/                  # how to write an agent / rule / skill — NOT installed
└── nix/, flake.nix              # packaging
```

## How knowledge is layered

| Layer | Loaded | Where | Budget |
|---|---|---|---|
| Core | every main-session request | `core/CLAUDE.md` | ≤ 150 lines |
| Subagent contract | every subagent | `core/subagent-contract.md`, injected at build time | ≤ 40 lines |
| Path rules | when the agent touches matching files | `rules/*.md` with `paths:` | ≤ 120 lines each |
| Agent body | when that agent runs | `agents/*.md` | ≤ 300 lines each |
| Skills | on demand / preloaded by name | `skills/*/SKILL.md` | no hard limit, keep it scannable |
| Hooks | never in context | `hooks/` | 0 tokens |

Rule of thumb: if a machine can check it, it is a hook, not text. If only one agent needs it, it
lives in that agent, not in a rule.

## Agents

| Agent | Job | Writes |
|---|---|---|
| `researcher` | reads one area of code, returns facts as doc cards | nothing |
| `architect-critic` | attacks a proposed architecture | nothing |
| `presenter` | Russian HTML slides from a brief or from docs | `docs/slides/**`, `.plan/PLAN.html` |
| `test-writer` | tests from acceptance criteria | test files of its task |
| `coder` | makes the tests pass | the task's exclusive write set |
| `refactorer` | cleans up with tests green | the task's exclusive write set |
| `test-runner` | runs the affected tests or the full suite, reports numbers | nothing |
| `build-fixer` | minimal fix for a broken build or type check | code, never tests |
| `code-reviewer`, `python-reviewer`, `go-reviewer`, `rust-reviewer`, `ts-react-reviewer`, `flutter-dart-reviewer` | review of a task diff | nothing |
| `db-reviewer`, `security-reviewer`, `optimizer` | data access, security, performance review | nothing |
| `ui-verifier` | screenshots at 375/768/1024/1440, both themes | temp folder only |
| `nix-architect`, `nix-engineer`, `nix-reviewer`, `nix-build-resolver`, `nix-test-runner` | Nix work | per brief |

Every agent frontmatter has `omitClaudeMd: true`, an explicit `tools:` allowlist,
`disallowedTools: Agent, Skill, mcp__*` and `maxTurns:`. Nested subagents are also disabled globally
(`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` in `settings.fragment.json`). Models and efforts are pinned
in `agent-models.json`; the build fails if an agent is missing there.

## Commands

- `nix-plan`, `nix-write`, `nix-review`, `nix-test`, `nix-fix`, `nix-build`, `nix-check`,
  `nix-devshell`, `nix-docker`, `nix-package`, `nix-update`, `nix-search`, `nix-why`, `nix-gc` — the Nix toolkit.
- `ask-astra`, `ask-agy`, `ask-argon` — second opinions from GPT-6-Astra, Gemini 3.8 Flash, Gemini 4 Argon
  (read-only); `write-astra`, `write-agy`, `write-argon` — delegated implementation. The `ask-*` / `write-*`
  wrappers themselves live in `nixos-conf`.
- `optimize`, `policy-review`, `test-affected` — orchestrator helpers.

## Skills

Own: `architecture-guide`, `auth-service`, `deploy-variants`, `design-system`, `project-docs`,
`security-review`, `sops`, `stack-choice`; Nix: `nix-debugging`, `nix-flake-patterns`, `nix-packaging`,
`nix-testing`, `nix-toolkit`, `nixos-module-patterns`, `project-flake`. The 22 reference skills from ECC
are listed below.

## Rules about code have examples

An instruction without an example is air. Every rule in an agent or a path rule has a pair:

````markdown
### R-DB-PAGINATION — paginate in the query, never in memory
Bad:
```python
rows = (await session.scalars(select(Order))).all()
return rows[offset:offset + limit]
```
Why: loads the whole table into the process on every page request.

Good:
```python
stmt = select(Order).order_by(Order.id).where(Order.id > after_id).limit(limit)
return (await session.scalars(stmt)).all()
```
````

The heading starts with a rule id `R-<AREA>-<NAME>`, unique across the repo. `tools/validate.py` fails
the build if an agent or rule has no `Bad:`/`Good:` pair; exemptions live in `tools/validate.json`.

## Naming

- Agents: kebab-case role name, no prefix: `test-writer`, `db-reviewer`. File name equals `name:`.
- Rules: `<topic>.md`: `python.md`, `db.md`, `auth.md`.
- Skills: `skills/<name>/SKILL.md`, `name:` equals the directory.
- Hooks: `guard_*.py` deny before a tool call, `check_*.py` warn after it, `fix_*.py` repair after it.


## Codex and Antigravity exports

The same agents, commands and skills are exported for Codex CLI and for Antigravity CLI (`agy`), so a
consumer can lay them out into `~/.codex` and `~/.gemini/config` next to the Claude tree. The payload
writes them from the finished Claude tree, after the model pins and the subagent contract are in:

| Path in `$out` | Content |
|---|---|
| `codex/agents/<name>.toml` | one Codex role per agent: `name`, `description`, `model`, `model_reasoning_effort`, `sandbox_mode`, `developer_instructions` (the agent body as a TOML literal string) |
| `codex/agents.toml` | `[agents.<name>]` entries with `-` replaced by `_` in the key (`config_file`, `description`) to merge into `~/.codex/config.toml` |
| `codex/prompts/<command>.md` | every command except `ask-astra` and `write-astra`, frontmatter stripped, `# /<command>` header |
| `codex/skills/` | copy of `claude/skills/` |
| `codex/AGENTS.md`, `agy/AGENTS.md` | `core/CLAUDE.md` plus a generated list of the subagents; identical files, under 24 000 bytes |
| `agy/agents/<name>.md` | one agy custom agent per agent: `name`, `description`, `model` (tier), `subagent: true`, `mainAgent: true`, then the body |

What does not carry over, because the other CLIs have no equivalent: `tools`, `disallowedTools`,
`maxTurns`, the orchestrator output style and the hooks. Codex agents that have no Write, Edit, MultiEdit or NotebookEdit
tool in Claude get `sandbox_mode = "read-only"` (Bash does not count: the read-only sandbox still runs commands,
only without writes); the rest get `workspace-write`.

Models per CLI live next to the Claude pins in `agent-models.json` (`codex.model`, `codex.effort`,
`agy.model`). The agy field accepts only the tiers `inherit`, `flash_lite`, `flash`, `pro`; a full model id
makes agy drop the agent. The build fails when an agent lacks these fields or when its body contains `'''`.
## Adding something

1. Copy the matching file from `_templates/` and fill it in.
2. For an agent, add its Claude model and effort plus the `codex` and `agy` entries to `agent-models.json`.
3. `nix develop -c python3 tools/validate.py .` (it also runs inside the build).
4. `nix build .#br-payload` and inspect `result/claude/`.

## Nix

| Output | What |
|---|---|
| `packages.br-payload` | `$out/claude/{CLAUDE.md,agents,skills,commands,rules/br,output-styles,br/templates}`, `$out/codex/{agents,agents.toml,prompts,skills,AGENTS.md}`, `$out/agy/{agents,AGENTS.md}`, `$out/settings.fragment.json`, `$out/hooks.json`, `$out/LICENSE`. The validator and the Python test suites run in `checkPhase`; `installCheckPhase` runs `br-hook` once the way Claude Code does. |
| `packages.br-hook` | `br-hook <entry>` wrapper for `hooks/*.py` with the pinned Python |
| `lib.mk { pkgs, ... }` | `{ payload, hook, python }` for consumers; extra arguments such as `lib` are accepted and ignored |
| `checks.payload` | the payload build |
| `devShells.default` | Python, nixfmt, statix, deadnix |

Consumer (`nixos-conf`):

```nix
inputs.warren.url = "github:BadRabbit00/warren";
# ...
let warren = inputs.warren.lib.mk { inherit pkgs; };   # also accepts { inherit pkgs lib; }
in {
  # lay out warren.payload/claude/* into ~/.claude, install core/CLAUDE.md as ~/.claude/CLAUDE.md,
  # deep-merge warren.payload/settings.fragment.json and merge warren.payload/hooks.json by id into settings.json,
  # put warren.hook on PATH for the hooks;
  # lay out warren.payload/codex/* into ~/.codex (merge codex/agents.toml into config.toml)
  # and warren.payload/agy/agents into ~/.gemini/config/agents
}
```

## From ECC

warren (short internal code: `br`, for BadRabbit) started as a rewrite inside a fork of **ECC — Everything Claude Code** by Affaan Mustafa
([github.com/affaan-m/ecc](https://github.com/affaan-m/ecc), MIT). Since 0.1.0 this is a standalone
repository and shares no code with ECC, except these 22 reference skills, copied unchanged under the MIT
licence (see `LICENSE`):

`api-design`, `cost-aware-llm-pipeline`, `dart-flutter-patterns`, `database-migrations`, `docker-patterns`,
`documentation-lookup`, `e2e-testing`, `golang-patterns`, `homelab-network-readiness`, `homelab-network-setup`,
`homelab-pihole-dns`, `homelab-vlan-segmentation`, `homelab-wireguard-vpn`, `mcp-server-patterns`,
`network-config-validation`, `postgres-patterns`, `prompt-caching-strategy`, `react-patterns`,
`recsys-pipeline-architect`, `redis-patterns`, `rust-patterns`, `vite-patterns`.

## Acknowledgement

Thank you, Affaan Mustafa and the ECC contributors. ECC showed what a disciplined agent toolkit for
Claude Code can look like: agents with narrow jobs, skills as reusable knowledge, hooks as mechanical
guardrails. warren keeps that shape and the lessons; the implementation is our own.
