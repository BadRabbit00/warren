#!/usr/bin/env python3
"""Second half of the br payload build (nix/payload.nix): frontmatter edits and self-checks.

The shell part of the build has already copied files into $out. This script:
  1. pins model/effort from agent-models.json into every agent;
  2. isolates every agent (omitClaudeMd, disallowedTools, maxTurns, preloaded skills for the Nix
     agents, no "Use PROACTIVELY"); a no-op for fields an agent already has;
  3. injects core/subagent-contract.md after the frontmatter of every agent;
  4. writes hooks.json with the pinned br-hook path;
  5. runs the output self-checks;
  6. exports the finished Claude tree to out/codex and out/agy.
Any miss exits non-zero and fails the build.

Usage: payload.py <out> <repo-root> <br-hook-exe>
Stdlib only.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tomllib
from pathlib import Path

# Skills each Nix agent is told to read in its body. The Skill tool is disabled for
# subagents, so preloading through `skills:` is the only way they get them.
NIX_AGENT_SKILLS = {
    "nix-architect": ["nix-toolkit", "nix-flake-patterns", "nixos-module-patterns"],
    "nix-engineer": ["nix-flake-patterns", "nixos-module-patterns", "nix-packaging"],
    "nix-build-resolver": ["nix-debugging"],
    "nix-test-runner": ["nix-testing"],
}
CONTRACT_HEADING = "## Contract (all br subagents)"
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
SKIPPED_PROMPTS = {"ask-astra", "write-astra"}
AGENTS_MD_LIMIT = 24_000  # agy reads at most 24 000 bytes per rules file; codex allows more

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def split(text: str) -> tuple[list[str], str]:
    if not text.startswith("---\n"):
        raise ValueError("no frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("unterminated frontmatter")
    return text[4:end].split("\n"), text[end + 5:]


def block_list_keys(fm: list[str]) -> list[str]:
    """Keys written as `key:` + indented or `- ` lines. get/put/as_list only understand one-line
    values, so editing such a list would leave orphaned items behind: refuse instead."""
    keys = []
    for i, line in enumerate(fm[:-1]):
        m = re.fullmatch(r"([A-Za-z_][\w-]*):\s*", line)
        if m and fm[i + 1].startswith((" ", "\t", "- ")):
            keys.append(m.group(1))
    return keys


def join(fm: list[str], body: str) -> str:
    return "---\n" + "\n".join(fm) + "\n---\n" + body


def get(fm: list[str], key: str) -> str | None:
    for line in fm:
        if line.startswith(key + ":"):
            return line.split(":", 1)[1].strip()
    return None


def put(fm: list[str], key: str, value: str) -> list[str]:
    out = [ln for ln in fm if not ln.startswith(key + ":")]
    out.append(f"{key}: {value}")
    return out


def as_list(value: str | None) -> list[str]:
    if not value:
        return []
    v = value.strip()
    if v.startswith("[") and v.endswith("]"):
        v = v[1:-1]
    return [x.strip().strip("'\"") for x in v.split(",") if x.strip()]


def hooks_shape_ok(hooks: object) -> bool:
    """hooks.json must be {"hooks": {event: [{"hooks": [{"command": str}]}]}}; anything else is
    reported here instead of crashing the substitution below."""
    by_event = hooks.get("hooks") if isinstance(hooks, dict) else None
    if not isinstance(by_event, dict):
        fail("hooks/hooks.json: top level must be an object with a 'hooks' object")
        return False
    ok = True
    for event, entries in by_event.items():
        if not isinstance(entries, list):
            fail(f"hooks/hooks.json: {event} must be a list")
            ok = False
            continue
        for entry in entries:
            cmds = entry.get("hooks") if isinstance(entry, dict) else None
            if not isinstance(cmds, list) or not all(isinstance(h, dict) and isinstance(h.get("command"), str) for h in cmds):
                fail(f"hooks/hooks.json: {event}: every entry needs a 'hooks' list of objects with a string 'command'")
                ok = False
    return ok


ROLE_KEYS = {"name", "description", "model", "model_reasoning_effort", "sandbox_mode", "developer_instructions"}


def codex_toml_check(codex: Path, expected: int) -> None:
    """Parse every generated codex TOML file and check its exact key set."""
    before = len(errors)
    files = sorted((codex / "agents").glob("*.toml"))
    if len(files) != expected:
        fail(f"codex toml: {len(files)} role files, expected {expected}")
    for f in files:
        try:
            keys = set(tomllib.loads(f.read_text(encoding="utf-8")))
        except tomllib.TOMLDecodeError as exc:
            fail(f"codex/agents/{f.name}: invalid TOML: {exc}")
            continue
        if keys != ROLE_KEYS:
            fail(f"codex/agents/{f.name}: keys {sorted(keys)} != {sorted(ROLE_KEYS)}")
    try:
        tables = tomllib.loads((codex / "agents.toml").read_text(encoding="utf-8")).get("agents", {})
    except tomllib.TOMLDecodeError as exc:
        fail(f"codex/agents.toml: invalid TOML: {exc}")
        return
    if len(tables) != expected:
        fail(f"codex/agents.toml: {len(tables)} tables, expected {expected}")
    for key, entry in tables.items():
        if not isinstance(entry, dict) or set(entry) != {"config_file", "description"}:
            fail(f"codex/agents.toml: [agents.{key}] must have exactly config_file and description")
    if len(errors) == before:
        print(f"codex toml ok: {expected} roles, agents.toml")


def export_codex_agy(out: Path, br: Path, models: dict[str, dict[str, dict[str, str]]]) -> tuple[int, int]:
    """Step 6: codex and agy trees from the finished Claude tree. Returns (agents, prompts)."""
    claude = out / "claude"
    codex_agents = out / "codex" / "agents"
    agy_agents = out / "agy" / "agents"
    prompts_dir = out / "codex" / "prompts"
    for d in (codex_agents, agy_agents, prompts_dir):
        d.mkdir(parents=True, exist_ok=True)
    entries: list[str] = []
    subagents: list[str] = []
    for p in sorted((claude / "agents").glob("*.md")):
        name = p.stem
        try:
            fm, body = split(p.read_text(encoding="utf-8"))
        except ValueError as exc:
            fail(f"agents/{name}.md: {exc}")
            continue
        desc = get(fm, "description") or ""
        if not desc or desc[0] in ">|":
            fail(f"agents/{name}.md: description must be one plain non-empty line (no block scalar)")
            continue
        if len(desc) >= 2 and desc[0] == desc[-1] and desc[0] in "\"'":
            quote = desc[0]
            desc = desc[1:-1]
            if ("''" if quote == "'" else "\\") in desc:
                fail(f"agents/{name}.md: description uses YAML escapes; write it plainly or without quotes")
                continue
        if CONTROL_CHARS.search(desc + body):
            fail(f"agents/{name}.md: description or body contains a control character")
            continue
        if "'''" in body:
            fail(f"agents/{name}.md: body contains ''' which would end the TOML literal string in codex/agents/{name}.toml")
            continue
        try:
            codex, agy = models[name]["codex"], models[name]["agy"]
            cmodel, ceffort, tier = codex["model"], codex["effort"], agy["model"]
        except (KeyError, TypeError) as exc:
            fail(f"agents/{name}.md: agent-models.json has no usable {exc} entry for codex/agy")
            continue
        if not all(isinstance(v, str) and v.strip() for v in (cmodel, ceffort, tier)):
            fail(f"agents/{name}.md: agent-models.json codex.model, codex.effort and agy.model must be non-empty strings")
            continue
        granted = set(as_list(get(fm, "tools"))) - set(as_list(get(fm, "disallowedTools")))
        sandbox = "workspace-write" if WRITE_TOOLS & granted else "read-only"
        quoted = json.dumps(desc, ensure_ascii=False)
        (codex_agents / f"{name}.toml").write_text(
            f"name = {json.dumps(name)}\n"
            f"description = {quoted}\n"
            f"model = {json.dumps(cmodel)}\n"
            f"model_reasoning_effort = {json.dumps(ceffort)}\n"
            f"sandbox_mode = {json.dumps(sandbox)}\n"
            f"developer_instructions = '''\n{body.strip("\n")}\n'''\n",
            encoding="utf-8",
        )
        entries.append(f'[agents.{name.replace("-", "_")}]\nconfig_file = "agents/{name}.toml"\ndescription = {quoted}\n')
        (agy_agents / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: {quoted}\nmodel: {tier}\nsubagent: true\nmainAgent: true\ninheritMcp: false\n---\n\n{body.lstrip("\n")}",
            encoding="utf-8",
        )
        subagents.append(f"- `{name}` — {desc} (codex: {cmodel}/{ceffort}; agy: {tier})")
    (out / "codex" / "agents.toml").write_text("\n".join(entries), encoding="utf-8")

    codex_toml_check(out / "codex", len(subagents))

    prompts = 0
    for p in sorted((claude / "commands").glob("*.md")):
        if p.stem in SKIPPED_PROMPTS:
            continue
        try:
            _, body = split(p.read_text(encoding="utf-8"))
        except ValueError as exc:
            fail(f"commands/{p.name}: {exc}")
            continue
        body = body.lstrip("\n")
        first = next((ln for ln in body.splitlines() if ln.strip()), "")
        if first.strip() != f"# /{p.stem}":
            body = f"# /{p.stem}\n\n{body}"
        (prompts_dir / p.name).write_text(body, encoding="utf-8")
        prompts += 1

    shutil.copytree(claude / "skills", out / "codex" / "skills", copy_function=shutil.copyfile)
    core = (br / "core" / "CLAUDE.md").read_text(encoding="utf-8")
    agents_md = core.rstrip("\n") + "\n\n## Subagents\n\n" + "\n".join(subagents) + "\n"
    if len(agents_md.encode("utf-8")) > AGENTS_MD_LIMIT:
        fail(f"AGENTS.md: {len(agents_md.encode('utf-8'))} bytes, limit {AGENTS_MD_LIMIT}")
    for tool in ("codex", "agy"):
        (out / tool / "AGENTS.md").write_text(agents_md, encoding="utf-8")
    return len(subagents), prompts


def main() -> int:
    out, br, hook_exe = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    claude = out / "claude"
    agents_dir = claude / "agents"
    models = json.loads((br / "agent-models.json").read_text(encoding="utf-8"))["agents"]
    contract = (br / "core" / "subagent-contract.md").read_text(encoding="utf-8").rstrip("\n") + "\n\n"
    # Effort values and the PROACTIVELY sentence are defined once, in the validator's config.
    cfg = json.loads((br / "tools" / "validate.json").read_text(encoding="utf-8"))
    allowed_effort = cfg["allowedEffort"]
    required_disallowed = cfg["requiredDisallowed"]
    style_marker = cfg["styleMarker"]
    proactive = re.compile(cfg["proactivelyPattern"])

    # --- 1–3: agents -----------------------------------------------------------------------------
    for p in sorted(agents_dir.glob("*.md")):
        name = p.stem
        try:
            fm, body = split(p.read_text(encoding="utf-8"))
        except ValueError as exc:
            fail(f"{name}: {exc}")
            continue
        blocks = block_list_keys(fm)
        for key in blocks:
            fail(f"{name}: block-style list for '{key}' is not supported; use inline [a, b]")
        if blocks:
            continue
        if name not in models:
            fail(f"{name}: no entry in agent-models.json")
            continue
        model, effort = str(models[name]["model"]), str(models[name]["effort"])
        if not re.fullmatch(r"claude-[a-z0-9.-]+", model):
            fail(f"{name}: bad model id {model!r}")
            continue
        if effort not in allowed_effort:
            fail(f"{name}: bad effort {effort!r}")
            continue
        fm = put(fm, "model", model)
        fm = put(fm, "effort", effort)
        fm = put(fm, "omitClaudeMd", "true")
        dis = as_list(get(fm, "disallowedTools"))
        fm = put(fm, "disallowedTools", ", ".join(dis + [t for t in required_disallowed if t not in dis]))
        if get(fm, "maxTurns") is None:
            fm = put(fm, "maxTurns", "40")
        if get(fm, "tools") is None:
            fail(f"{name}: agent without an explicit tools: line")
        skills = NIX_AGENT_SKILLS.get(name, [])
        if skills:
            fm = put(fm, "skills", "[" + ", ".join(skills) + "]")
        fm = [proactive.sub("", ln) if ln.startswith("description:") else ln for ln in fm]
        p.write_text(join(fm, "\n" + contract + body.lstrip("\n")), encoding="utf-8")
    for skill_agent in NIX_AGENT_SKILLS:
        if not (agents_dir / f"{skill_agent}.md").is_file():
            fail(f"{skill_agent}: listed in NIX_AGENT_SKILLS but agents/{skill_agent}.md is missing")

    # --- 4: hooks.json ---------------------------------------------------------------------------
    # Parse first, substitute inside the command values only: a raw-text replace would also hit
    # descriptions and break JSON if the path ever needed escaping.
    hooks = json.loads((br / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    hooks_ok = hooks_shape_ok(hooks)
    if hooks_ok:
        for entries in hooks["hooks"].values():
            for entry in entries:
                for h in entry["hooks"]:
                    h["command"] = h["command"].replace("@BR_HOOK@", hook_exe)
        (out / "hooks.json").write_text(json.dumps(hooks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # --- 5: self-checks --------------------------------------------------------------------------
    for p in sorted(agents_dir.glob("*.md")):
        try:
            fm, body = split(p.read_text(encoding="utf-8"))
        except ValueError as exc:
            fail(f"{p.name}: {exc}")
            continue
        if get(fm, "omitClaudeMd") != "true":
            fail(f"{p.name}: omitClaudeMd is not true")
        if not (get(fm, "model") or "").startswith("claude-"):
            fail(f"{p.name}: model not pinned")
        if "Agent" not in as_list(get(fm, "disallowedTools")):
            fail(f"{p.name}: Agent not in disallowedTools")
        if CONTRACT_HEADING not in body:
            fail(f"{p.name}: contract not injected")
        if re.search(r"^# Core rules\b", body, re.M):
            fail(f"{p.name}: core rules leaked into an agent")
        if re.search(r"proactively", get(fm, "description") or "", re.I):
            fail(f"{p.name}: description still asks for proactive use")
        for s in as_list(get(fm, "skills")):
            if not (claude / "skills" / s / "SKILL.md").is_file():
                fail(f"{p.name}: preloaded skill '{s}' is not in the output")
    hits = [str(f.relative_to(out)) for f in out.rglob("*") if f.is_file() and style_marker in f.read_text(encoding="utf-8", errors="ignore")]
    if hits != ["claude/output-styles/orchestrator.md"]:
        fail(f"style marker found in {hits}; expected only claude/output-styles/orchestrator.md")

    settings = json.loads((out / "settings.fragment.json").read_text(encoding="utf-8"))
    if not isinstance(settings, dict):
        fail("settings.fragment.json: top level must be an object")
    else:
        if set(settings) != {"env", "outputStyle"}:
            fail(f"settings.fragment.json: keys {sorted(settings)}, expected ['env', 'outputStyle']")
        env = settings.get("env")
        if not isinstance(env, dict) or env.get("CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH") != "1":
            fail("settings.fragment.json: CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH must be \"1\"")
        if settings.get("outputStyle") != "orchestrator":
            fail("settings.fragment.json: outputStyle must be orchestrator")

    for p in sorted((claude / "rules" / "br").glob("*.md")):
        try:
            fm, _ = split(p.read_text(encoding="utf-8"))
        except ValueError:
            fm = []
        if not any(ln.startswith("paths:") for ln in fm):
            fail(f"rules/br/{p.name}: no paths: frontmatter (would load into every session)")

    if hooks_ok:
        raw = (out / "hooks.json").read_text(encoding="utf-8")
        if "@BR_HOOK@" in raw:
            fail("hooks.json: @BR_HOOK@ left")
        for entries in hooks["hooks"].values():
            for entry in entries:
                if not str(entry.get("id", "")).startswith("br:"):
                    fail(f"hooks.json: id {entry.get('id')} does not start with br:")
                for h in entry["hooks"]:
                    parts = h["command"].split()
                    if len(parts) != 2 or parts[0] != hook_exe or not (br / "hooks" / f"{parts[1]}.py").is_file():
                        fail(f"hooks.json: bad command {h['command']!r}")

    for d, want in [("skills/architecture-guide/references/layers", 11), ("skills/security-review/references", 5)]:
        count = len(list((claude / d).glob("*.md")))
        if count != want:
            fail(f"{d}: {count} files, expected {want}")
    if not (claude / "skills/project-docs/templates/example_db.dbml").is_file():
        fail("skills/project-docs/templates/example_db.dbml missing")

    scripts = sorted((claude / "workflows").glob("*.js"))
    if not scripts:
        fail("claude/workflows: no *.js files")
    for script in scripts:
        first = next((ln for ln in script.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.lstrip().startswith("//")), "")
        if not first.startswith("export const meta = {"):
            fail(f"claude/workflows/{script.name}: first statement must be export const meta = {{…}}")

    n_codex, n_prompts = export_codex_agy(out, br, models)

    if errors:
        print("br payload self-check failed:", file=sys.stderr)
        for msg in errors:
            print("  - " + msg, file=sys.stderr)
        return 1
    print(f"br payload: {len(list(agents_dir.glob('*.md')))} agents, "
          f"{len(list((claude / 'skills').iterdir()))} skills, "
          f"{len(list((claude / 'commands').glob('*.md')))} commands, "
          f"{len(list((claude / 'rules' / 'br').glob('*.md')))} rules, "
          f"{len(scripts)} workflows, "
          f"codex/agy: {n_codex} agents, {n_prompts} prompts — self-checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
