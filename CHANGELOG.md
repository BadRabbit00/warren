# Changelog

## 0.2.0 — unreleased

- Codex CLI and Antigravity CLI (`agy`) exports in the payload: `$out/codex/{agents/*.toml,agents.toml,prompts,skills,AGENTS.md}`
  and `$out/agy/{agents/*.md,AGENTS.md}`, generated from the same agents, commands, skills and `core/CLAUDE.md`.
- `agent-models.json` carries `codex.model`, `codex.effort` and `agy.model` per agent; the validator requires them,
  checks the agy tier vocabulary, the codex effort, agent-name rules (charset, codex reserved keys), block-scalar
  descriptions and `'''` in agent bodies; the exporter re-parses every generated TOML file.
- No export of `tools`, `disallowedTools`, `maxTurns`, hooks or the orchestrator output style: the other CLIs have no
  equivalent. Codex roles get `sandbox_mode` read-only unless the agent keeps a write tool; agy agents get `inheritMcp: false`.

## 0.1.0 — 2026-11-06

First standalone release as **warren**. Until now this layer lived as the `badrabbit/` directory and the
`br` payload flavour inside a fork of [ECC](https://github.com/affaan-m/ecc).

- Repository root is the warren layer (internal prefix `br`): `agents/`, `rules/`, `skills/`, `commands/`, `core/`,
  `output-styles/`, `templates/`, `hooks/`, `tools/`.
- Nix: `packages.br-payload`, `packages.br-hook`, `lib.mk { pkgs }`; no Node in the build;
  the validator and the Python test suites run in `checkPhase`.
- Removed: the legacy ECC payload, `ecc-run` / `ecc-hook`, `/astra-review`, the allowlist,
  and every upstream agent, command, hook, rule and skill that the `br` payload flavour did not install.
- Kept from ECC: 22 reference skills (see README, "From ECC").
