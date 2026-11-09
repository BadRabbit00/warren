#!/usr/bin/env python3
"""Structural checks for the br repository.

Usage:
    python3 tools/validate.py [root]

root  repository root; defaults to the parent of tools/.

Exit code 0 = clean, 1 = violations (printed one per line), 2 = internal error
(unreadable root or config). Standard library only; runs inside the payload build.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CONTENT_DIRS = ("agents", "rules", "skills", "commands", "core", "templates", "hooks")
RULE_HEADING = re.compile(r"^###\s+(R-[A-Z0-9]+(?:-[A-Z0-9]+)+)\b", re.M)
# Applied to one section at a time (see check_examples), so a Bad: of one rule can never
# pair with a Good: of the next.
PAIR = re.compile(r"^Bad:\s*\n```[^\n]*\n.*?\n```.*?^Good:\s*\n```[^\n]*\n.*?\n```", re.M | re.S)
HEADING = re.compile(r"#{1,3}\s")
BLOCK_KEY = re.compile(r"([A-Za-z_][\w-]*):\s*$")


# ---------------------------------------------------------------- frontmatter

def raw_frontmatter(text: str) -> tuple[str, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    return text[4:end], text[end + 4:].lstrip("\n")


def split_frontmatter(text: str) -> tuple[dict[str, object], str] | None:
    parts = raw_frontmatter(text)
    if parts is None:
        return None
    return parse_yaml_subset(parts[0]), parts[1]


def block_list_keys(raw: str) -> list[str]:
    """Keys written as `key:` followed by an indented or `- ` line. nix/payload.py cannot edit
    such lists, so agents must use the inline form."""
    lines = raw.splitlines()
    keys = []
    for i, line in enumerate(lines[:-1]):
        m = BLOCK_KEY.fullmatch(line)
        if m and lines[i + 1].startswith((" ", "\t", "- ")):
            keys.append(m.group(1))
    return keys


def parse_yaml_subset(raw: str) -> dict[str, object]:
    """Parses the flat YAML we use: `key: value`, `key: [a, b]`, and `key:` + `  - item` lists.
    An empty `key:` is "" until a list item follows. Lines starting with '#' are comments."""
    data: dict[str, object] = {}
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith(("  - ", "- ")) and current_key is not None:
            items = data[current_key]
            if not isinstance(items, list):
                items = []
                data[current_key] = items
            items.append(unquote(line.split("- ", 1)[1].strip()))
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if value == "":
            data[key] = ""
            current_key = key
            continue
        current_key = None
        if value.startswith("[") and value.endswith("]"):
            data[key] = [unquote(v.strip()) for v in value[1:-1].split(",") if v.strip()]
        elif value in ("true", "false"):
            data[key] = value == "true"
        elif re.fullmatch(r"-?\d+", value):
            data[key] = int(value)
        else:
            data[key] = unquote(value)
    return data


def unquote(v: str) -> str:
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def scalar(v: object) -> str:
    """Text of a scalar value; lists and missing values are "" so 'missing' checks fire."""
    if isinstance(v, str):
        return v
    if isinstance(v, (bool, int)):
        return str(v)
    return ""


def as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def sections(body: str) -> list[str]:
    """Body split at headings (levels 1-3) that sit outside code fences: a markdown example
    inside a fence may contain `### ` lines of its own."""
    out: list[list[str]] = [[]]
    is_open = False
    for line in body.splitlines(keepends=True):
        if line.startswith("```"):
            is_open = not is_open
        elif not is_open and HEADING.match(line):
            out.append([])
        out[-1].append(line)
    return ["".join(chunk) for chunk in out]


def fence_tags(body: str) -> tuple[list[str], bool]:
    """Language tags of opening fences, and whether the last fence is left open."""
    tags: list[str] = []
    is_open = False
    for line in body.splitlines():
        if line.startswith("```"):
            if not is_open:
                tags.append(line[3:].strip())
            is_open = not is_open
    return tags, is_open


# ---------------------------------------------------------------- checks

LIST_KEYS = (
    "allowedModels", "allowedEffort", "agyModels", "requiredDisallowed", "forbiddenDescriptionWords",
    "examplesExempt", "hookEvents", "docTemplates", "buildIsolated", "useWhenExempt",
)


class Validator:
    def __init__(self, root: Path) -> None:
        self.root = root
        cfg = json.loads((root / "tools" / "validate.json").read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            raise TypeError("tools/validate.json: top level must be an object")
        for key in LIST_KEYS:
            val = cfg.get(key, [])
            if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
                raise TypeError(f"tools/validate.json: {key} must be a list of strings")
        self.cfg = cfg
        self.errors: list[str] = []
        self.rule_ids: dict[str, Path] = {}
        self._cache: dict[Path, str | None] = {}

    def err(self, path: Path, msg: str) -> None:
        self.errors.append(f"{path.relative_to(self.root)}: {msg}")

    # -- helpers
    def lines(self, text: str) -> int:
        return len(text.splitlines())

    def check_examples(self, path: Path, body: str, key: str) -> None:
        if key in self.cfg.get("examplesExempt", []):
            return
        hint = "(Bad: + code block, then Good: + code block)"
        rules = []
        for section in sections(body):
            m = RULE_HEADING.match(section)
            if m:
                rules.append((m.group(1), section))
        if rules:
            for rid, section in rules:
                if not PAIR.search(section):
                    self.err(path, f"rule {rid}: no example pair {hint}")
        elif not PAIR.search(body):
            self.err(path, f"no example pair {hint}")
        tags, still_open = fence_tags(body)
        if still_open:
            self.err(path, "unclosed code fence")
        if any(not tag for tag in tags):
            self.err(path, "code block without a language tag")

    def collect_rule_ids(self, path: Path, body: str) -> None:
        for rid in RULE_HEADING.findall(body):
            if rid in self.rule_ids:
                self.err(path, f"duplicate rule id {rid} (first in {self.rule_ids[rid].name})")
            else:
                self.rule_ids[rid] = path

    def check_encoding(self, path: Path, raw: bytes) -> None:
        if raw.startswith(b"\xef\xbb\xbf"):
            self.err(path, "UTF-8 BOM")
        if b"\r\n" in raw:
            self.err(path, "CRLF line endings")

    def read(self, path: Path) -> str | None:
        """Text with BOM and CRLF already reported and normalised away, so one defect yields one
        error. None means the file is not UTF-8; callers skip it. Cached: every file is reported once."""
        if path in self._cache:
            return self._cache[path]
        raw = path.read_bytes()
        self.check_encoding(path, raw)
        text: str | None
        try:
            text = raw.decode("utf-8").removeprefix("﻿").replace("\r\n", "\n")
        except UnicodeDecodeError:
            self.err(path, "not UTF-8")
            text = None
        self._cache[path] = text
        return text

    # -- sections
    def check_core(self) -> None:
        limits = self.cfg["limits"]
        for name, key in (("CLAUDE.md", "core"), ("subagent-contract.md", "contract")):
            p = self.root / "core" / name
            if not p.exists():
                self.err(p, "missing")
                continue
            text = self.read(p)
            if text is None:
                continue
            count = self.lines(text)
            if count > limits[key]:
                self.err(p, f"{count} lines > limit {limits[key]}")

    def check_agents(self, models: dict[str, object]) -> list[str]:
        names = []
        for p in sorted((self.root / "agents").glob("*.md")):
            text = self.read(p)
            if text is None:
                continue
            parsed = split_frontmatter(text)
            if parsed is None:
                self.err(p, "no YAML frontmatter")
                continue
            fm, body = parsed
            raw = raw_frontmatter(text)
            for key in block_list_keys(raw[0] if raw else ""):
                self.err(p, f"block-style list for '{key}' is not supported; use inline [a, b]")
            name = scalar(fm.get("name"))
            names.append(name)
            if name != p.stem:
                self.err(p, f"name '{name}' != file name '{p.stem}'")
            desc = scalar(fm.get("description")).strip()
            if not desc:
                self.err(p, "description missing")
            elif desc[0] in ">|":
                self.err(p, "description must be one plain line (no block scalar)")
            # buildIsolated agents get isolation fields from nix/payload.py at build time.
            built = name in self.cfg.get("buildIsolated", [])
            checked = desc
            if built:
                # Same substitution as nix/payload.py (one pattern in validate.json): the build strips this sentence.
                checked = re.sub(self.cfg["proactivelyPattern"], "", desc)
            for word in self.cfg["forbiddenDescriptionWords"]:
                if word.lower() in checked.lower():
                    self.err(p, f"description contains '{word}' (would make Claude auto-invoke)")
            if not built and fm.get("omitClaudeMd") is not True:
                self.err(p, "omitClaudeMd: true is required")
            if not as_list(fm.get("tools")):
                self.err(p, "explicit tools allowlist is required")
            if "Agent" in as_list(fm.get("tools")):
                self.err(p, "tools must not include Agent")
            if not built:
                disallowed = as_list(fm.get("disallowedTools"))
                for t in self.cfg["requiredDisallowed"]:
                    if t not in disallowed:
                        self.err(p, f"disallowedTools must include {t}")
                if not isinstance(fm.get("maxTurns"), int):
                    self.err(p, "maxTurns (integer) is required")
            if scalar(fm.get("model")) not in self.cfg["allowedModels"]:
                self.err(p, f"model must be one of {self.cfg['allowedModels']}")
            if "effort" in fm and scalar(fm["effort"]) not in self.cfg["allowedEffort"]:
                self.err(p, f"effort must be one of {self.cfg['allowedEffort']}")
            if "'''" in body:
                self.err(p, "body contains ''' (terminates the TOML literal string of the codex export)")
            count = self.lines(body)
            if count > self.cfg["limits"]["agent"]:
                self.err(p, f"body {count} lines > limit {self.cfg['limits']['agent']}")
            if not built and "## Output" not in body:
                self.err(p, "missing '## Output' section")
            self.check_examples(p, body, f"agent:{name}")
            self.collect_rule_ids(p, body)
            if name not in models:
                self.err(p, "not listed in agent-models.json")
        return names

    def check_rules(self) -> None:
        for p in sorted((self.root / "rules").glob("*.md")):
            text = self.read(p)
            if text is None:
                continue
            parsed = split_frontmatter(text)
            if parsed is None or not as_list(parsed[0].get("paths")):
                self.err(p, "path rule needs a non-empty 'paths:' list in frontmatter")
                continue
            body = parsed[1]
            count = self.lines(body)
            if count > self.cfg["limits"]["rule"]:
                self.err(p, f"{count} lines > limit {self.cfg['limits']['rule']}")
            self.check_examples(p, body, f"rule:{p.stem}")
            self.collect_rule_ids(p, body)

    def check_skills(self) -> None:
        for p in sorted((self.root / "skills").glob("*/SKILL.md")):
            text = self.read(p)
            if text is None:
                continue
            parsed = split_frontmatter(text)
            if parsed is None:
                self.err(p, "no YAML frontmatter")
                continue
            fm, body = parsed
            if scalar(fm.get("name")) != p.parent.name:
                self.err(p, f"name must equal directory '{p.parent.name}'")
            if p.parent.name not in self.cfg.get("useWhenExempt", []) \
                    and not scalar(fm.get("description")).startswith("Use when"):
                self.err(p, "description must start with 'Use when'")
            self.collect_rule_ids(p, body)

    def check_output_styles(self) -> None:
        for p in sorted((self.root / "output-styles").glob("*.md")):
            text = self.read(p)
            if text is None:
                continue
            parsed = split_frontmatter(text)
            if parsed is None or not scalar(parsed[0].get("name")):
                self.err(p, "output style needs frontmatter with name")
                continue
            fm, body = parsed
            if fm.get("keep-coding-instructions") is not True:
                self.err(p, "keep-coding-instructions: true is required")
            count = self.lines(body)
            if count > self.cfg["limits"]["outputStyle"]:
                self.err(p, f"body {count} lines > limit {self.cfg['limits']['outputStyle']}")
            if p.stem == "orchestrator" and self.cfg["styleMarker"] not in body:
                self.err(p, f"missing marker {self.cfg['styleMarker']}")
        marker = self.cfg["styleMarker"]
        # Only the installed content is scanned (output-styles/ is not in CONTENT_DIRS): README,
        # .plan and nix/ may name the marker.
        scanned = [d for d in CONTENT_DIRS if (self.root / d).is_dir()]
        for p in sorted(f for d in scanned for f in (self.root / d).rglob("*")):
            if p.is_file() and p.suffix in {".md", ".html", ".json"} \
                    and marker in p.read_text(encoding="utf-8", errors="replace"):
                self.err(p, f"{marker} leaks outside output-styles/")

    def check_templates(self) -> None:
        t = self.root / "templates"
        slides, blank = t / "slides.html", t / "slides.blank.html"
        if slides.exists():
            full = self.read(slides)
            if full is None:
                pass
            elif full.count("<!-- SLIDES:BEGIN") != 1 or full.count("<!-- SLIDES:END -->") != 1:
                self.err(slides, "needs exactly one SLIDES:BEGIN … SLIDES:END block")
            elif not blank.exists():
                self.err(blank, "missing (generate it from slides.html)")
            else:
                expected = re.sub(r"<!-- SLIDES:BEGIN.*?<!-- SLIDES:END -->", "<!-- SLIDES -->", full, flags=re.S)
                blank_text = self.read(blank)
                if blank_text is not None and blank_text != expected:
                    self.err(blank, "out of sync with slides.html (regenerate: block → <!-- SLIDES -->)")
        plan = t / "PLAN.md"
        if plan.exists():
            text = self.read(plan)
            if text is not None:
                if not re.search(r"^### T1 — ", text, re.M):
                    self.err(plan, "needs a task card heading '### T1 — …' (hooks parse it)")
                for field in ("**Status:**", "**Writes (exclusive):**", "**Tests (test-writer):**"):
                    if field not in text:
                        self.err(plan, f"task card field {field} missing (hooks parse it)")
        docs = self.root / "skills" / "project-docs" / "templates"
        if docs.parent.exists():
            for name in self.cfg["docTemplates"]:
                if not (docs / name).exists():
                    self.err(docs, f"template {name} missing")

    def check_json(self, agent_names: list[str], models: dict[str, object]) -> None:
        s = self.root / "settings.fragment.json"
        try:
            settings = json.loads(s.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.err(s, f"invalid: {exc}")
        else:
            env = settings.get("env") if isinstance(settings, dict) else None
            if not isinstance(env, dict) or env.get("CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH") != "1":
                self.err(s, "env.CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH must be \"1\"")
        m = self.root / "agent-models.json"
        for name, spec in models.items():
            if name not in agent_names:
                self.err(m, f"'{name}' is not an agent in agents/")
            if not isinstance(spec, dict):
                self.err(m, f"'{name}': model must be a full claude-* id")
                continue
            if not str(spec.get("model", "")).startswith("claude-"):
                self.err(m, f"'{name}': model must be a full claude-* id")
            elif spec.get("effort") not in self.cfg["allowedEffort"]:
                self.err(m, f"'{name}': bad effort")
            codex = spec.get("codex")
            if not isinstance(codex, dict):
                self.err(m, f"'{name}': codex must be an object with model and effort")
            else:
                cmodel = codex.get("model")
                if not isinstance(cmodel, str) or not cmodel.strip():
                    self.err(m, f"'{name}': codex.model {cmodel!r} must be a non-empty string")
                ceffort = codex.get("effort")
                if ceffort not in self.cfg["allowedEffort"]:
                    self.err(m, f"'{name}': codex.effort {ceffort!r} not in allowedEffort")
            agy = spec.get("agy")
            if not isinstance(agy, dict):
                self.err(m, f"'{name}': agy must be an object with model")
            elif agy.get("model") not in self.cfg["agyModels"]:
                self.err(m, f"'{name}': agy.model {agy.get('model')!r} not in agyModels")

    def check_hooks(self) -> None:
        """hooks/hooks.json: unique br:* ids, descriptions, `@BR_HOOK@ <entry>` commands with existing entries."""
        hdir = self.root / "hooks"
        h = hdir / "hooks.json"
        if not h.exists():
            return
        try:
            data = json.loads(h.read_text(encoding="utf-8"))
        except ValueError as exc:
            self.err(h, f"invalid: {exc}")
            return
        by_event = data.get("hooks") or {} if isinstance(data, dict) else None
        if not isinstance(by_event, dict):
            self.err(h, "top level must be an object with a 'hooks' object")
            return
        seen: set[str] = set()
        used: set[str] = set()
        for event, entries in by_event.items():
            if event not in self.cfg["hookEvents"]:
                self.err(h, f"unknown hook event {event}")
            if not isinstance(entries, list):
                self.err(h, f"{event}: must be a list")
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    self.err(h, f"{event}: every entry must be an object")
                    continue
                hid = scalar(entry.get("id"))
                if not hid.startswith("br:"):
                    self.err(h, f"{event}: id must start with 'br:' ({hid or 'missing'})")
                if hid in seen:
                    self.err(h, f"duplicate hook id {hid}")
                seen.add(hid)
                if not entry.get("description"):
                    self.err(h, f"{hid}: description required")
                cmds = entry.get("hooks", [])
                if not isinstance(cmds, list):
                    self.err(h, f"{hid}: 'hooks' must be a list")
                    continue
                for cmd in cmds:
                    if not isinstance(cmd, dict):
                        self.err(h, f"{hid}: every hook must be an object")
                        continue
                    m = re.fullmatch(r"@BR_HOOK@ ([a-z_]+)", scalar(cmd.get("command")))
                    if not m:
                        self.err(h, f"{hid}: command must be '@BR_HOOK@ <entry>'")
                        continue
                    used.add(m.group(1))
                    if not (hdir / f"{m.group(1)}.py").exists():
                        self.err(h, f"{hid}: hooks/{m.group(1)}.py not found")
                    if not isinstance(cmd.get("timeout"), int) or cmd["timeout"] > self.cfg["maxHookTimeout"]:
                        self.err(h, f"{hid}: timeout must be an int <= {self.cfg['maxHookTimeout']}")
        for py in sorted(hdir.glob("*.py")):
            if py.stem not in used:
                self.err(py, "entry point is not registered in hooks.json")
            if not re.fullmatch(r"(guard|check|fix)_[a-z_]+", py.stem):
                self.err(py, "hook entry names are guard_*/check_*/fix_*")

    def check_commands(self) -> None:
        for p in sorted((self.root / "commands").glob("*.md")):
            text = self.read(p)
            if text is None:
                continue
            parsed = split_frontmatter(text)
            if parsed is None or not scalar(parsed[0].get("description")).strip():
                self.err(p, "command needs frontmatter with description")

    def check_agent_skills(self) -> None:
        available = {p.parent.name for p in (self.root / "skills").glob("*/SKILL.md")}
        for p in sorted((self.root / "agents").glob("*.md")):
            text = self.read(p)
            parsed = split_frontmatter(text) if text is not None else None
            if parsed is None:
                continue
            for skill in as_list(parsed[0].get("skills")):
                if skill not in available:
                    self.err(p, f"preloaded skill '{skill}' is not in skills/")

    def check_exemptions(self) -> None:
        """Stale exemptions silently weaken the checks, so every listed name must still exist."""
        cfg_path = self.root / "tools" / "validate.json"
        agents = {p.stem for p in (self.root / "agents").glob("*.md")}
        skills = {p.parent.name for p in (self.root / "skills").glob("*/SKILL.md")}
        for name in self.cfg.get("buildIsolated", []):
            if name not in agents:
                self.err(cfg_path, f"buildIsolated: agent '{name}' is not in agents/")
        for key in self.cfg.get("examplesExempt", []):
            kind, _, name = key.partition(":")
            if kind == "agent" and name not in agents:
                self.err(cfg_path, f"examplesExempt: agent '{name}' is not in agents/")
            elif kind == "rule" and not (self.root / "rules" / f"{name}.md").is_file():
                self.err(cfg_path, f"examplesExempt: rule '{name}' is not in rules/")
            elif kind not in ("agent", "rule"):
                self.err(cfg_path, f"examplesExempt: unknown key '{key}'")
        for name in self.cfg.get("useWhenExempt", []):
            if name not in skills:
                self.err(cfg_path, f"useWhenExempt: skill '{name}' has no skills/{name}/SKILL.md")

    def load_models(self) -> dict[str, object]:
        path = self.root / "agent-models.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        agents = data.get("agents", {}) if isinstance(data, dict) else None
        if not isinstance(agents, dict):
            self.err(path, "must be an object with an 'agents' object")
            return {}
        return agents

    def run(self) -> list[str]:
        models = self.load_models()
        self.check_core()
        names = self.check_agents(models)
        self.check_rules()
        self.check_skills()
        self.check_output_styles()
        self.check_json(names, models)
        self.check_hooks()
        self.check_templates()
        self.check_commands()
        self.check_agent_skills()
        self.check_exemptions()
        return self.errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, nargs="?", default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args()
    try:
        errors = Validator(args.root.resolve()).run()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"validate: internal error: {exc}", file=sys.stderr)
        return 2
    for e in errors:
        print(e)
    print(f"validate: {len(errors)} problem(s)", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
