"""Tests for validate.py. Run: python3 -I -B -m unittest discover -s tools -p test_*.py"""
from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

import validate

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BUILD = REPO / "tools" / "build.py"

COPIED = (
    "agents", "rules", "skills", "commands", "core", "output-styles", "templates", "hooks", "tools", "workflows",
    "agent-models.json", "settings.fragment.json", "LICENSE",
)

GOOD_AGENT = """---
name: demo-agent
description: Reviews demo code when the orchestrator asks.
tools: Read, Grep
disallowedTools: Agent, Skill, mcp__*
omitClaudeMd: true
maxTurns: 20
model: sonnet
effort: medium
---

# Demo

## Examples

### R-DEMO-ONE — demo rule

Bad:
```python
x = eval(s)
```
Why: code injection.

Good:
```python
x = int(s)
```

## Output

```text
STATUS: done
```
"""

GOOD_RULE = """---
paths:
  - "**/*.py"
---

# Demo rules

### R-DEMO-TWO — demo

Bad:
```python
print(x)
```
Why: no structure.

Good:
```python
log.info("x", x=x)
```
"""


def make_root(tmp: Path) -> Path:
    """Copies the shipped tree (explicit allowlist) into tmp/br and returns that root."""
    root = tmp / "br"
    root.mkdir()
    # Explicit allowlist (the directories build.py reads): copying the repo root would follow
    # symlinks out of the tree and fail to clean up read-only files.
    for name in COPIED:
        src = REPO / name
        if src.is_dir():
            shutil.copytree(
                src, root / name, symlinks=True, ignore=shutil.ignore_patterns("__pycache__"),
                copy_function=shutil.copyfile,  # a read-only source tree must not give read-only copies
            )
        else:
            shutil.copyfile(src, root / name)
    return root


class ValidateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = make_root(self.tmp)
        models = json.loads((self.root / "agent-models.json").read_text(encoding="utf-8"))
        models["agents"]["demo-agent"] = {
            "model": "claude-sonnet-5-5",
            "effort": "medium",
            "codex": {"model": "gpt-6-astra", "effort": "high"},
            "agy": {"model": "flash"},
        }
        (self.root / "agent-models.json").write_text(json.dumps(models), encoding="utf-8")

    def run_validator(self) -> list[str]:
        return validate.Validator(self.root).run()

    def write_agent(self, text: str) -> None:
        (self.root / "agents" / "demo-agent.md").write_text(text, encoding="utf-8")

    def test_shipped_tree_is_clean(self) -> None:
        models = json.loads((self.root / "agent-models.json").read_text(encoding="utf-8"))
        del models["agents"]["demo-agent"]
        (self.root / "agent-models.json").write_text(json.dumps(models), encoding="utf-8")
        self.assertEqual(self.run_validator(), [])

    def test_good_agent_and_rule_pass(self) -> None:
        self.write_agent(GOOD_AGENT)
        (self.root / "rules" / "demo.md").write_text(GOOD_RULE, encoding="utf-8")
        self.assertEqual(self.run_validator(), [])

    def test_agent_without_omit_claude_md_fails(self) -> None:
        self.write_agent(GOOD_AGENT.replace("omitClaudeMd: true\n", ""))
        self.assertTrue(any("omitClaudeMd" in e for e in self.run_validator()))

    def test_agent_must_disallow_agent_tool(self) -> None:
        self.write_agent(GOOD_AGENT.replace("Agent, Skill, mcp__*", "Skill, mcp__*"))
        self.assertTrue(any("disallowedTools must include Agent" in e for e in self.run_validator()))

    def test_proactive_description_fails(self) -> None:
        self.write_agent(GOOD_AGENT.replace("Reviews demo code", "Use PROACTIVELY to review demo code"))
        self.assertTrue(any("auto-invoke" in e for e in self.run_validator()))

    def test_agent_without_examples_fails(self) -> None:
        self.write_agent(GOOD_AGENT.replace("Bad:", "Wrong:"))
        self.assertTrue(any("no example pair" in e for e in self.run_validator()))

    def test_rule_without_paths_fails(self) -> None:
        (self.root / "rules" / "demo.md").write_text(GOOD_RULE.replace('paths:\n  - "**/*.py"\n', "x: 1\n"), encoding="utf-8")
        self.assertTrue(any("paths" in e for e in self.run_validator()))

    def test_duplicate_rule_id_fails(self) -> None:
        self.write_agent(GOOD_AGENT)
        (self.root / "rules" / "demo.md").write_text(GOOD_RULE.replace("R-DEMO-TWO", "R-DEMO-ONE"), encoding="utf-8")
        self.assertTrue(any("duplicate rule id R-DEMO-ONE" in e for e in self.run_validator()))

    def test_agent_missing_from_models_fails(self) -> None:
        text = GOOD_AGENT.replace("name: demo-agent", "name: other-agent")
        (self.root / "agents" / "other-agent.md").write_text(text, encoding="utf-8")
        self.assertTrue(any("not listed in agent-models.json" in e for e in self.run_validator()))

    def test_crlf_is_reported(self) -> None:
        (self.root / "agents" / "demo-agent.md").write_bytes(GOOD_AGENT.replace("\n", "\r\n").encode())
        self.assertTrue(any("CRLF" in e for e in self.run_validator()))

    def test_spawn_depth_setting_required(self) -> None:
        (self.root / "settings.fragment.json").write_text('{"env": {}}', encoding="utf-8")
        self.assertTrue(any("SPAWN_DEPTH" in e for e in self.run_validator()))

    def test_hook_without_entry_fails(self) -> None:
        h = self.root / "hooks" / "hooks.json"
        data = json.loads(h.read_text(encoding="utf-8"))
        data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = "@BR_HOOK@ guard_missing"
        h.write_text(json.dumps(data), encoding="utf-8")
        errs = self.run_validator()
        self.assertTrue(any("guard_missing.py not found" in e for e in errs))
        self.assertTrue(any("guard_bash.py: entry point is not registered" in e for e in errs))

    def test_hook_raw_command_fails(self) -> None:
        h = self.root / "hooks" / "hooks.json"
        data = json.loads(h.read_text(encoding="utf-8"))
        data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = "python3 hooks/guard_bash.py"
        h.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(any("@BR_HOOK@" in e for e in self.run_validator()))

    def test_duplicate_hook_id_fails(self) -> None:
        h = self.root / "hooks" / "hooks.json"
        data = json.loads(h.read_text(encoding="utf-8"))
        data["hooks"]["PreToolUse"][1]["id"] = data["hooks"]["PreToolUse"][0]["id"]
        h.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(any("duplicate hook id" in e for e in self.run_validator()))

    def test_style_marker_leak_fails(self) -> None:
        self.write_agent(GOOD_AGENT.replace("# Demo", "# Demo\nBR-ORCHESTRATOR-STYLE-ACTIVE"))
        self.assertTrue(any("leaks outside output-styles" in e for e in self.run_validator()))

    def test_style_needs_keep_coding_instructions(self) -> None:
        p = self.root / "output-styles" / "orchestrator.md"
        p.write_text(p.read_text(encoding="utf-8").replace("keep-coding-instructions: true\n", ""))
        self.assertTrue(any("keep-coding-instructions" in e for e in self.run_validator()))

    def test_blank_slides_out_of_sync_fails(self) -> None:
        p = self.root / "templates" / "slides.blank.html"
        p.write_text(p.read_text(encoding="utf-8").replace("--accent: #6A3FD6", "--accent: #000000"))
        self.assertTrue(any("out of sync" in e for e in self.run_validator()))

    def test_plan_template_fields_required(self) -> None:
        p = self.root / "templates" / "PLAN.md"
        p.write_text(p.read_text(encoding="utf-8").replace("**Tests (test-writer):**", "**Test files:**"))
        self.assertTrue(any("Tests (test-writer)" in e for e in self.run_validator()))

    def test_missing_preloaded_skill_fails(self) -> None:
        self.write_agent(GOOD_AGENT.replace("effort: medium\n", "effort: medium\nskills: [no-such-skill]\n"))
        self.assertTrue(any("no-such-skill" in e for e in self.run_validator()))

    def test_command_without_description_fails(self) -> None:
        (self.root / "commands").mkdir(exist_ok=True)
        (self.root / "commands" / "demo.md").write_text("---\nargument-hint: x\n---\n# demo\n", encoding="utf-8")
        self.assertTrue(any("command needs frontmatter" in e for e in self.run_validator()))

    # -- exemptions from tools/validate.json

    def patch_cfg(self, **extra: list[str]) -> None:
        path = self.root / "tools" / "validate.json"
        cfg = json.loads(path.read_text(encoding="utf-8"))
        for key, names in extra.items():
            cfg[key] = cfg.get(key, []) + names
        path.write_text(json.dumps(cfg), encoding="utf-8")

    def test_build_isolated_agent_skips_isolation_fields(self) -> None:
        bare = GOOD_AGENT.replace("omitClaudeMd: true\n", "").replace("maxTurns: 20\n", "")
        bare = bare.replace("disallowedTools: Agent, Skill, mcp__*\n", "").replace("## Output", "## Result")
        self.write_agent(bare)
        self.assertTrue(any("omitClaudeMd" in e for e in self.run_validator()))
        self.patch_cfg(buildIsolated=["demo-agent"])
        self.assertEqual(self.run_validator(), [])

    def test_build_isolated_agent_still_checks_description_words(self) -> None:
        self.patch_cfg(buildIsolated=["demo-agent"])
        # The build strips this sentence, so it is allowed ...
        self.write_agent(GOOD_AGENT.replace("when the orchestrator asks.", "when asked. Use PROACTIVELY for demos."))
        self.assertEqual(self.run_validator(), [])
        # ... but a forbidden word elsewhere survives the build and must fail.
        self.write_agent(GOOD_AGENT.replace("when the orchestrator asks.", "and runs automatically."))
        self.assertTrue(any("auto-invoke" in e for e in self.run_validator()))

    def test_skill_description_needs_use_when_unless_exempt(self) -> None:
        d = self.root / "skills" / "demo-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: demo-skill\ndescription: Demo things.\n---\n\n# Demo\n", encoding="utf-8")
        self.assertTrue(any("must start with 'Use when'" in e for e in self.run_validator()))
        self.patch_cfg(useWhenExempt=["demo-skill"])
        self.assertEqual([e for e in self.run_validator() if "demo-skill" in e], [])

    def test_agent_without_examples_passes_when_exempt(self) -> None:
        self.write_agent(GOOD_AGENT.replace("Bad:", "Wrong:"))
        self.assertTrue(any("no example pair" in e for e in self.run_validator()))
        self.patch_cfg(examplesExempt=["agent:demo-agent"])
        self.assertEqual(self.run_validator(), [])

    def test_stale_exemptions_fail(self) -> None:
        self.write_agent(GOOD_AGENT)
        self.patch_cfg(
            buildIsolated=["ghost"],
            examplesExempt=["agent:ghost2", "rule:ghost4", "bogus:x"],
            useWhenExempt=["ghost3"],
        )
        errs = self.run_validator()
        for needle in (
            "buildIsolated: agent 'ghost'", "examplesExempt: agent 'ghost2'", "useWhenExempt: skill 'ghost3'",
            "rule 'ghost4'", "unknown key 'bogus:x'",
        ):
            self.assertTrue(any(needle in e for e in errs), needle)

    # -- empty values, block lists, encodings, exit codes, per-rule pairs

    def test_agent_with_empty_description_fails(self) -> None:
        self.write_agent(GOOD_AGENT.replace("description: Reviews demo code when the orchestrator asks.", "description:"))
        self.assertTrue(any("description missing" in e for e in self.run_validator()))

    def test_command_with_empty_description_fails(self) -> None:
        (self.root / "commands").mkdir(exist_ok=True)
        (self.root / "commands" / "demo.md").write_text("---\ndescription:\n---\n# demo\n", encoding="utf-8")
        self.assertTrue(any("command needs frontmatter" in e for e in self.run_validator()))

    def test_agent_block_list_is_rejected(self) -> None:
        self.write_agent(GOOD_AGENT.replace("disallowedTools: Agent, Skill, mcp__*", "disallowedTools:\n  - Agent\n  - Skill\n  - mcp__*"))
        self.assertTrue(any("block-style list for 'disallowedTools'" in e for e in self.run_validator()))

    def test_bom_gives_exactly_one_error(self) -> None:
        (self.root / "agents" / "demo-agent.md").write_bytes(b"\xef\xbb\xbf" + GOOD_AGENT.encode())
        errs = self.run_validator()
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("UTF-8 BOM", errs[0])

    def test_non_utf8_file_is_reported_not_crashed(self) -> None:
        (self.root / "rules" / "bad.md").write_bytes(b"---\npaths:\n  - x\n---\n\xff\xfe\n")
        self.assertTrue(any("bad.md: not UTF-8" in e for e in self.run_validator()))
        proc = subprocess.run(
            [sys.executable, "-I", "-B", str(HERE / "validate.py"), str(self.root)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("not UTF-8", proc.stdout)

    def test_missing_root_is_internal_error(self) -> None:
        err = io.StringIO()
        argv = sys.argv
        sys.argv = ["validate.py", str(self.tmp / "nope")]
        try:
            with redirect_stderr(err):
                rc = validate.main()
        finally:
            sys.argv = argv
        self.assertEqual(rc, 2)
        self.assertIn("internal error", err.getvalue())

    def test_bad_json_config_is_internal_error(self) -> None:
        (self.root / "tools" / "validate.json").write_text("{", encoding="utf-8")
        err = io.StringIO()
        argv = sys.argv
        sys.argv = ["validate.py", str(self.root)]
        try:
            with redirect_stderr(err):
                rc = validate.main()
        finally:
            sys.argv = argv
        self.assertEqual(rc, 2)

    def test_pair_must_sit_inside_its_own_rule(self) -> None:
        second = """### R-DEMO-THREE — second rule

Bad:
```python
y = eval(s)
```
Why: injection.
"""
        # Rule ONE has only Good-less Bad; THREE has a Bad. The Good of nothing follows: no pairing across sections.
        text = GOOD_AGENT.replace("Why: code injection.\n\nGood:\n```python\nx = int(s)\n```\n", "Why: code injection.\n")
        text = text.replace("## Output", second + "\n### R-DEMO-FOUR — third\n\nGood:\n```python\nz = 1\n```\n\n## Output")
        self.write_agent(text)
        errs = self.run_validator()
        self.assertTrue(any("R-DEMO-ONE: no example pair" in e for e in errs), errs)
        self.assertTrue(any("R-DEMO-THREE: no example pair" in e for e in errs), errs)

    def test_unclosed_fence_fails(self) -> None:
        self.write_agent(GOOD_AGENT + "\n```text\n")
        self.assertTrue(any("unclosed code fence" in e for e in self.run_validator()))

    # -- tools/build.py

    def run_payload(self, agent_text: str) -> subprocess.CompletedProcess[str]:
        """Runs `build.py <out> <repo> <hook-python>` on a copy of the tree with one extra agent."""
        self.write_agent(agent_text)
        return subprocess.run(
            [sys.executable, "-I", "-B", str(BUILD), str(self.tmp / "out"), str(self.root), "/x/python3"],
            capture_output=True, text=True, check=False,
        )

    def test_payload_rejects_block_list(self) -> None:
        block = GOOD_AGENT.replace("disallowedTools: Agent, Skill, mcp__*", "disallowedTools:\n  - Bash")
        proc = self.run_payload(block)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("demo-agent: block-style list for 'disallowedTools' is not supported", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_payload_reports_missing_frontmatter_without_traceback(self) -> None:
        proc = self.run_payload("# no frontmatter\n")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("demo-agent: no frontmatter", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


# AC4: Nix wording the validator must refuse in the text agents read. Each entry is one line that
# names one forbidden thing; (phrase, the sentence that carries it).
NIX_LINES = (
    ("nix develop", "Run `nix develop -c pytest` before you finish."),
    ("nix shell", "Use `nix shell nixpkgs-tool -c gh` for one-off tools."),
    ("nix run", "Start it with `nix run .#app`."),
    ("nix build", "Build it with `nix build .#pkg`."),
    ("nix flake", "Check it with `nix flake check`."),
    ("nixpkgs#", "Take the CLI from `nixpkgs#gh`."),
    ("flake.nix", "The inputs live in flake.nix."),
    ("devShell", "Add the tool to the devShell."),
    ("dockerTools", "Build the image with dockerTools.buildLayeredImage."),
    ("nix-engineer agent name", "Hand the work to the nix-engineer agent."),
    ("nix-toolkit skill name", "Read the nix-toolkit skill first."),
    ("nix-build command name", "Run the /nix-build command."),
)
NIX_WORDS = ("nix", "devshell", "dockertools")
GOOD_SKILL = "---\nname: demo-skill\ndescription: Use when demoing the validator.\n---\n\n# Demo\n"
GOOD_COMMAND = "---\ndescription: Demo command.\n---\n# demo\n"
GOOD_WORKFLOW = "export const meta = {name: 'demo', description: 'Demo.'}\n"


class NoNixTest(unittest.TestCase):
    """The validator keeps Nix out of the text agents read: agents, skills, commands, rules, core,
    output-styles, workflows, templates and settings.fragment.json. Hooks code and tests may name Nix."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = make_root(self.tmp)
        models = json.loads((self.root / "agent-models.json").read_text(encoding="utf-8"))
        models["agents"]["demo-agent"] = {
            "model": "claude-sonnet-5-5", "effort": "medium",
            "codex": {"model": "gpt-6-astra", "effort": "high"}, "agy": {"model": "flash"},
        }
        (self.root / "agent-models.json").write_text(json.dumps(models), encoding="utf-8")

    def findings_for(self, rel: str) -> list[str]:
        """Validator findings that name the file or directory `rel`."""
        return [e for e in validate.Validator(self.root).run() if e.startswith(rel)]

    def nix_findings_for(self, rel: str) -> list[str]:
        """Findings for `rel` whose message (after the path) speaks about Nix."""
        return [e for e in self.findings_for(rel) if any(w in e.split(":", 1)[-1].lower() for w in NIX_WORDS)]

    def put(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_validator_rejects_nix(self) -> None:
        # Every forbidden phrase in an agent.
        for label, line in NIX_LINES:
            with self.subTest(place="agent", phrase=label):
                path = self.put("agents/demo-agent.md", GOOD_AGENT + "\n" + line + "\n")
                self.assertTrue(self.nix_findings_for("agents/demo-agent.md"), line)
                path.unlink()

        # A phrase in each of the other text directories and in the settings fragment.
        places = (
            ("skills/demo-skill/SKILL.md", lambda line: GOOD_SKILL + "\n" + line + "\n"),
            ("commands/demo.md", lambda line: GOOD_COMMAND + "\n" + line + "\n"),
            ("rules/demo.md", lambda line: GOOD_RULE + "\n" + line + "\n"),
            ("core/demo.md", lambda line: "# Demo core\n\n" + line + "\n"),
            ("output-styles/demo.md", lambda line: "---\nname: demo\n---\n\n" + line + "\n"),
            ("workflows/demo.js", lambda line: GOOD_WORKFLOW + f"// {line}\n"),
            ("templates/demo.md", lambda line: "# Demo template\n\n" + line + "\n"),
        )
        for i, (rel, make) in enumerate(places):
            label, line = NIX_LINES[i % len(NIX_LINES)]
            with self.subTest(place=rel, phrase=label):
                path = self.put(rel, make(line))
                self.assertTrue(self.nix_findings_for(rel), line)
                path.unlink()

        settings = self.root / "settings.fragment.json"
        original = settings.read_text(encoding="utf-8")
        data = json.loads(original)
        data["env"]["DEMO_CMD"] = "nix develop -c pytest"
        with self.subTest(place="settings.fragment.json"):
            settings.write_text(json.dumps(data), encoding="utf-8")
            self.assertTrue(self.nix_findings_for("settings.fragment.json"))
        settings.write_text(original, encoding="utf-8")

        # Files and directories named nix-* in those places are findings even with clean content.
        named = (
            ("agents/nix-foo.md", GOOD_AGENT.replace("name: demo-agent", "name: nix-foo")),
            ("skills/nix-foo/SKILL.md", GOOD_SKILL.replace("name: demo-skill", "name: nix-foo")),
            ("commands/nix-foo.md", GOOD_COMMAND),
            ("rules/nix.md", GOOD_RULE),
        )
        for rel, text in named:
            with self.subTest(nix_named=rel):
                path = self.put(rel, text)
                shown = rel.removesuffix("/SKILL.md")
                self.assertTrue(self.findings_for(shown), rel)
                self.assertTrue(
                    [e for e in self.findings_for(shown) if "nix" in e.split(":", 1)[-1].lower()], rel,
                )
                path.unlink()

    def test_validator_ignores_words_that_only_contain_nix(self) -> None:
        # AC4 is about Nix, not about substrings: Unix, Linux and minix are fine.
        self.put("agents/demo-agent.md", GOOD_AGENT + "\nOn Unix and Linux read a unix socket; minix is a toy.\n")
        self.assertEqual(self.findings_for("agents/demo-agent.md"), [])

    def test_validator_exempts_hooks_code_and_tests_from_nix(self) -> None:
        text = "\n".join(line for _, line in NIX_LINES) + "\n"
        self.put("hooks/brhooks/nix_wrapper.py", f'"""{text}"""\n')
        self.put("hooks/test/test_no_nix.py", f'"""{text}"""\n')
        self.assertEqual(self.findings_for("hooks/brhooks/nix_wrapper.py"), [])
        self.assertEqual(self.findings_for("hooks/test/test_no_nix.py"), [])

    def test_validate_config_drops_nix_exemptions(self) -> None:
        cfg = (REPO / "tools" / "validate.json").read_text(encoding="utf-8")
        self.assertNotIn("nix", cfg.lower())


class ModelTableTest(unittest.TestCase):
    """agent-models.json codex/agy schema and the TOML-literal guard on agent bodies."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = make_root(self.tmp)
        # A complete, valid table written here, so the tests do not depend on the repo's own file content.
        self.models_path = self.root / "agent-models.json"
        models = json.loads(self.models_path.read_text(encoding="utf-8"))
        for spec in models["agents"].values():
            spec["codex"] = {"model": "gpt-6-astra", "effort": "high"}
            spec["agy"] = {"model": "flash"}
        self.save(models)
        self.names = sorted(models["agents"])

    def load(self) -> dict[str, dict[str, dict[str, object]]]:
        data: dict[str, dict[str, dict[str, object]]] = json.loads(self.models_path.read_text(encoding="utf-8"))
        return data

    def save(self, models: dict[str, dict[str, dict[str, object]]]) -> None:
        self.models_path.write_text(json.dumps(models), encoding="utf-8")

    def findings_for(self, name: str, baseline: list[str]) -> list[str]:
        """New findings (absent from the baseline run) about exactly this agent.

        Model-table findings read "agent-models.json: '<name>': ...", body findings "agents/<name>.md: ...".
        """
        mine = (f"agent-models.json: '{name}':", f"agents/{name}.md:")
        return [e for e in validate.Validator(self.root).run() if e not in baseline and e.startswith(mine)]

    def test_models_complete_table_is_clean(self) -> None:
        self.assertEqual(validate.Validator(self.root).run(), [])

    def test_models_require_codex_and_agy(self) -> None:
        baseline = validate.Validator(self.root).run()
        no_codex, no_agy = self.names[0], self.names[1]
        models = self.load()
        del models["agents"][no_codex]["codex"]
        del models["agents"][no_agy]["agy"]
        self.save(models)
        self.assertTrue(any("codex" in e for e in self.findings_for(no_codex, baseline)), no_codex)
        self.assertTrue(any("agy" in e for e in self.findings_for(no_agy, baseline)), no_agy)

    def test_agy_model_vocabulary(self) -> None:
        baseline = validate.Validator(self.root).run()
        bad, good = self.names[0], self.names[1]
        models = self.load()
        models["agents"][bad]["agy"] = {"model": "gemini-4-argon-high"}
        models["agents"][good]["agy"] = {"model": "flash"}
        self.save(models)
        self.assertTrue(
            any("gemini-4-argon-high" in e for e in self.findings_for(bad, baseline)), bad,
        )
        self.assertEqual(self.findings_for(good, baseline), [])

    def test_codex_effort_vocabulary(self) -> None:
        baseline = validate.Validator(self.root).run()
        bad = self.names[0]
        models = self.load()
        models["agents"][bad]["codex"] = {"model": "gpt-6-astra", "effort": "ultra"}
        self.save(models)
        self.assertTrue(any("ultra" in e for e in self.findings_for(bad, baseline)), bad)

    def test_models_reject_wrong_shapes(self) -> None:
        baseline = validate.Validator(self.root).run()
        list_codex, str_agy, int_model, blank_model = self.names[:4]
        models = self.load()
        models["agents"][list_codex]["codex"] = ["x"]
        models["agents"][str_agy]["agy"] = "flash"
        models["agents"][int_model]["codex"] = {"model": 5, "effort": "high"}
        models["agents"][blank_model]["codex"] = {"model": "   ", "effort": "high"}
        self.save(models)
        for name in (list_codex, str_agy, int_model, blank_model):
            self.assertTrue(self.findings_for(name, baseline), name)  # reports, does not raise

    def test_config_list_keys_must_be_lists(self) -> None:
        path = self.root / "tools" / "validate.json"
        cfg = json.loads(path.read_text(encoding="utf-8"))
        cfg["agyModels"] = "flash"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        with self.assertRaises(TypeError):
            validate.Validator(self.root).run()
        err = io.StringIO()
        argv = sys.argv
        sys.argv = ["validate.py", str(self.root)]
        try:
            with redirect_stderr(err):
                rc = validate.main()
        finally:
            sys.argv = argv
        self.assertEqual(rc, 2)

    def set_description(self, name: str, replacement: str) -> None:
        path = self.root / "agents" / f"{name}.md"
        lines = path.read_text(encoding="utf-8").split("\n")
        index = next(i for i, ln in enumerate(lines) if ln.startswith("description:"))
        lines[index] = replacement
        path.write_text("\n".join(lines), encoding="utf-8")

    def test_description_block_scalar_is_a_finding(self) -> None:
        baseline = validate.Validator(self.root).run()
        folded, literal = self.names[0], self.names[1]
        self.set_description(folded, "description: >-\n  Reviews code across\n  several lines.")
        self.set_description(literal, "description: |\n  Reviews code across\n  several lines.")
        for name in (folded, literal):
            with self.subTest(agent=name):
                self.assertTrue(any("description" in e for e in self.findings_for(name, baseline)), name)

    def test_quoted_description_with_yaml_escapes_is_a_finding(self) -> None:
        baseline = validate.Validator(self.root).run()
        single, double, plain = self.names[0], self.names[1], self.names[2]
        self.set_description(single, "description: 'It''s fine.'")
        self.set_description(double, 'description: "Say \\"hi\\""')
        self.set_description(plain, 'description: "Reviews code."')
        for name in (single, double):
            with self.subTest(agent=name):
                self.assertTrue(any("description" in e for e in self.findings_for(name, baseline)), name)
        self.assertEqual(self.findings_for(plain, baseline), [], "a plain quoted description stays valid")

    def test_body_rejects_toml_literal_terminator(self) -> None:
        baseline = validate.Validator(self.root).run()
        target = self.names[0]
        path = self.root / "agents" / f"{target}.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nPrint it as '''text''' please.\n", encoding="utf-8")
        self.assertTrue(self.findings_for(target, baseline), target)

    # -- agent names: charset and reserved codex [agents] keys

    RESERVED_KEYS = [
        "max_depth", "max_threads", "max_concurrent_threads_per_session", "default_subagent_model",
        "default_subagent_reasoning_effort", "job_max_runtime_seconds", "interrupt_message",
    ]

    def inject_agent(self, name: str) -> None:
        """Adds agents/<name>.md (a real agent's frontmatter and body, renamed) and a complete model entry."""
        source = (self.root / "agents" / "code-reviewer.md").read_text(encoding="utf-8")
        prefix = "".join(c for c in name.upper() if c.isalnum())  # keeps rule ids unique across injected agents
        text = source.replace("name: code-reviewer", f"name: {name}", 1).replace("R-CR-", f"R-{prefix}-")
        (self.root / "agents" / f"{name}.md").write_text(text, encoding="utf-8")
        models = self.load()
        models["agents"][name] = {
            "model": "claude-sonnet-5-5", "effort": "medium",
            "codex": {"model": "gpt-6-astra", "effort": "high"}, "agy": {"model": "flash"},
        }
        self.save(models)

    def test_agent_name_charset(self) -> None:
        baseline = validate.Validator(self.root).run()
        self.inject_agent("Bad_Name")
        self.inject_agent("good-name-2")
        bad = [e.partition(": ")[2] for e in self.findings_for("Bad_Name", baseline)]
        self.assertTrue(any("name" in e for e in bad), bad)
        self.assertEqual(self.findings_for("good-name-2", baseline), [])

    def test_agent_name_not_codex_reserved(self) -> None:
        shipped = json.loads((Path(validate.__file__).resolve().parent / "validate.json").read_text(encoding="utf-8"))
        self.assertEqual(shipped.get("codexReservedAgentKeys"), self.RESERVED_KEYS)
        path = self.root / "tools" / "validate.json"
        cfg = json.loads(path.read_text(encoding="utf-8"))
        cfg["codexReservedAgentKeys"] = self.RESERVED_KEYS
        path.write_text(json.dumps(cfg), encoding="utf-8")
        baseline = validate.Validator(self.root).run()
        for name in ("max-depth", "max-threads"):
            with self.subTest(agent=name):
                self.inject_agent(name)
                found = [e.partition(": ")[2] for e in self.findings_for(name, baseline)]
                self.assertTrue(any("reserved" in e for e in found), found)


class WorkflowTest(unittest.TestCase):
    """D9: workflows/*.js are structurally checked (meta block first, agent() calls typed and resolvable,
    no non-deterministic calls). Findings are matched by the file they are reported on."""

    STEM = "demo-flow"  # no digits: tests look for line numbers inside findings

    META = (
        "export const meta = {\n"
        "  name: 'demo-flow',\n"
        "  description: 'Demo workflow for the validator tests',\n"
        "}\n"
    )
    BODY = (
        "\n"
        "const plan = await agent(\n"
        "  'make a plan',\n"
        "  { agentType: 'researcher', label: 'plan' },\n"
        ")\n"
        "const run = await agent('run', { agentType: 'coder', label: 'run' })\n"
        "const note = 'wrong_reason (import, syntax or fixture error)'\n"
    )
    GOOD = "// demo workflow\n" + META + BODY  # BODY starts on line 6; the last line is line 12

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = make_root(self.tmp)

    def findings(self, text: str) -> list[str]:
        """Writes workflows/<STEM>.js, runs the validator, returns the findings reported on that file."""
        (self.root / "workflows" / f"{self.STEM}.js").write_text(text, encoding="utf-8")
        prefix = f"workflows/{self.STEM}.js:"
        return [e for e in validate.Validator(self.root).run() if e.startswith(prefix)]

    def assert_line(self, found: list[str], line: int) -> None:
        self.assertTrue(any(re.search(rf"\b{line}\b", e) for e in found), f"no finding names line {line}: {found}")

    def test_good_workflow_has_no_findings(self) -> None:
        # Positive control: the template the other tests mutate is itself accepted.
        self.assertEqual(self.findings(self.GOOD), [])

    # AC1: missing or non-first `export const meta` is a finding
    def test_workflow_meta_first(self) -> None:
        cases = {
            "missing": self.BODY,
            "after a const": "const LIMIT = 3\n\n" + self.META + self.BODY,
            "after an agent call": "const early = await agent('x', { agentType: 'coder' })\n" + self.META + self.BODY,
            "not exported": self.META.replace("export ", "", 1) + self.BODY,
        }
        for label, text in cases.items():
            with self.subTest(case=label):
                found = self.findings(text)
                self.assertTrue(any("meta" in e for e in found), found)
        with self.subTest(case="leading comments are fine"):
            self.assertEqual(self.findings("// one\n/* two */\n" + self.META + self.BODY), [])

    # AC2: meta.name must equal the file stem; description must be present
    def test_workflow_meta_fields(self) -> None:
        with self.subTest(case="name differs from file stem"):
            found = self.findings(self.GOOD.replace("name: 'demo-flow'", "name: 'other-flow'"))
            self.assertTrue(any("name" in e for e in found), found)
        with self.subTest(case="name missing"):
            found = self.findings(self.GOOD.replace("  name: 'demo-flow',\n", ""))
            self.assertTrue(any("name" in e for e in found), found)
        with self.subTest(case="description missing"):
            found = self.findings(self.GOOD.replace("  description: 'Demo workflow for the validator tests',\n", ""))
            self.assertTrue(any("description" in e for e in found), found)
        with self.subTest(case="double-quoted name matching the stem is fine"):
            self.assertEqual(self.findings(self.GOOD.replace("name: 'demo-flow'", 'name: "demo-flow"')), [])

    # AC3: an agent( call without agentType: is a finding naming its line
    def test_workflow_agent_requires_agent_type(self) -> None:
        bad_line = 13  # the first line appended to GOOD
        with self.subTest(case="one-line call without options"):
            found = self.findings(self.GOOD + "const bad = await agent('no type here')\n")
            self.assert_line(found, bad_line)
            self.assertFalse(any(re.search(r"\b(7|11)\b", e) for e in found), found)  # the valid calls
        with self.subTest(case="options object without agentType"):
            self.assert_line(self.findings(self.GOOD + "const bad = await agent('p', { label: 'x' })\n"), bad_line)
        with self.subTest(case="multi-line call reports the line of agent("):
            text = self.GOOD + "const bad = await agent(\n  'p',\n  { label: 'x' },\n)\n"
            self.assert_line(self.findings(text), bad_line)
        with self.subTest(case="agentType in a neighbouring call does not excuse this one"):
            text = (self.GOOD + "const bad = await agent('p', { label: 'x' })\n"
                    "const ok = await agent('q', { agentType: 'coder' })\n")
            found = self.findings(text)
            self.assert_line(found, bad_line)
            self.assertFalse(any(re.search(r"\b14\b", e) for e in found), found)

    # AC4: agentType naming an agent that is not in agents/ is a finding
    def test_workflow_agent_type_exists(self) -> None:
        found = self.findings(self.GOOD + "const bad = await agent('p', { agentType: 'no-such-agent' })\n")
        self.assertTrue(any("no-such-agent" in e for e in found), found)
        with self.subTest(case="every shipped agent name resolves"):
            names = sorted(p.stem for p in (self.root / "agents").glob("*.md"))
            calls = "".join(f"await agent('p', {{ agentType: '{n}' }})\n" for n in names)
            self.assertEqual(self.findings(self.GOOD + calls), [])
        with self.subTest(case="a non-literal agentType cannot be resolved and is not flagged"):
            text = self.GOOD + "const name = 'coder'\nawait agent('p', { agentType: name, label: 'x' })\n"
            self.assertEqual(self.findings(text), [])
        with self.subTest(case="a removed agent stops resolving"):
            (self.root / "agents" / "coder.md").unlink()
            found = self.findings(self.GOOD)
            self.assertTrue(any("coder" in e for e in found), found)

    # AC5: Date.now(, Math.random(, new Date(), import( are findings naming their line
    def test_workflow_forbidden_calls(self) -> None:
        cases = {
            "Date.now(": "const t = Date.now()\n",
            "Math.random(": "const r = Math.random()\n",
            "new Date()": "const d = new Date()\n",
            "import(": "const m = await import('node:fs')\n",
        }
        for token, line in cases.items():
            with self.subTest(token=token):
                self.assert_line(self.findings(self.GOOD + line), 13)
        with self.subTest(case="the word import inside a string is not a call"):
            self.assertEqual(self.findings(self.GOOD + "const s = 'import, then run'\n"), [])

    # AC7: code inside ${...} of a template literal is checked like any other code; template text is not
    def test_workflow_template_interpolation(self) -> None:
        with self.subTest(case="forbidden call inside ${...} is a finding on its line"):
            found = self.findings(self.GOOD + "const s = `${Date.now()}`\n")
            self.assertTrue(any("Date.now(" in e for e in found), found)
            self.assert_line(found, 13)
        with self.subTest(case="untyped agent() inside ${...} is a finding on its line"):
            found = self.findings(self.GOOD + "const s = `${await agent('p')}`\n")
            self.assertTrue(any("agentType" in e for e in found), found)
            self.assert_line(found, 13)
        with self.subTest(case="interpolation on a later line of a multi-line template names that line"):
            found = self.findings(self.GOOD + "const s = `first\nsecond ${Math.random()}\nthird`\n")
            self.assertTrue(any("Math.random(" in e for e in found), found)
            self.assert_line(found, 14)
        with self.subTest(case="text inside a nested template is not code"):
            self.assertEqual(self.findings(self.GOOD + "const s = `a ${x ? `import(y)` : ''}`\n"), [])
        with self.subTest(case="plain template text is not code"):
            self.assertEqual(self.findings(self.GOOD + "const s = `call Date.now() and agent('p') later`\n"), [])
        with self.subTest(case="code after a template on the same line is still checked"):
            found = self.findings(self.GOOD + "const s = `${x}` + Date.now()\n")
            self.assert_line(found, 13)

    # AC8 (D13): a regex literal in expression position is a finding on its line; division, comments,
    # strings and template text are not; the rest of the file is still checked afterwards
    def assert_regex_finding(self, found: list[str], line: int) -> None:
        self.assertTrue(
            any("regex" in e and re.search(rf"\b{line}\b", e) for e in found),
            f"no regex finding names line {line}: {found}",
        )

    def test_workflow_regex_literal(self) -> None:
        positions = {
            "after (": "const t = check(/ab+c/)\n",
            "after ,": "const t = [1, /ab+c/]\n",
            "after =": "const re = /ab+c/g\n",
            "after :": "const o = { re: /ab+c/ }\n",
            "after [": "const l = [/ab+c/]\n",
            "after !": "const n = !/ab+c/.test(s)\n",
            "after &": "const b = ok && /ab+c/.test(s)\n",
            "after |": "const b = ok || /ab+c/.test(s)\n",
            "after ?": "const b = ok ? /ab+c/ : null\n",
            "after {": "if (ok) { /ab+c/.test(s) }\n",
            "after }": "if (ok) {} /ab+c/.test(s)\n",
            "after ;": "go(); /ab+c/.test(s)\n",
            "after return": "function f(s) { return /ab+c/.test(s) }\n",
            "at line start": "/ab+c/.test(s)\n",
            "with an escaped slash": "const re = /a\\/b/\n",
        }
        for label, line in positions.items():
            with self.subTest(position=label):
                self.assert_regex_finding(self.findings(self.GOOD + line), 13)
        with self.subTest(case="the finding says to use new RegExp"):
            found = self.findings(self.GOOD + "const re = /ab+c/\n")
            self.assertTrue(any("new RegExp" in e for e in found), found)
        with self.subTest(case="a regex holding quote characters does not hide the rest of the file"):
            text = self.GOOD + "const re = /['\"]/g\nconst k = 1\nconst bad = await agent('p')\n"
            found = self.findings(text)
            self.assert_regex_finding(found, 13)
            self.assertTrue(any("agentType" in e and re.search(r"\b15\b", e) for e in found), found)
        with self.subTest(case="an untyped agent() two lines after a regex is still reported"):
            text = self.GOOD + "const re = /ab+c/\nconst k = 1\nconst bad = await agent('p')\n"
            found = self.findings(text)
            self.assert_regex_finding(found, 13)
            self.assertTrue(any("agentType" in e and re.search(r"\b15\b", e) for e in found), found)
        with self.subTest(case="a forbidden call after a regex on the same line is still reported"):
            found = self.findings(self.GOOD + "const t = /ab+c/.test(String(Date.now()))\n")
            self.assertTrue(any("Date.now(" in e for e in found), found)
            self.assert_regex_finding(found, 13)
        with self.subTest(case="only the regex line is reported among division and comments"):
            text = self.GOOD + "const h = x/2\n// see /ab+c/ here\n/* and /ab+c/ here */\nconst re = /y/\n"
            found = self.findings(text)
            self.assert_regex_finding(found, 16)
            self.assertFalse(any(re.search(r"\b1[345]\b", e) for e in found), found)
        not_regex = {
            "division with spaces": "const q = a / b\n",
            "division without spaces": "const h = x/2\n",
            "chained division": "const d = a/b/c\n",
            "line comment": "// matches /ab+c/ here\n",
            "line comment after code": "const k = 1 // then /ab+c/\n",
            "block comment": "/* matches /ab+c/ here */\n",
            "multi-line block comment": "/*\n * matches /ab+c/ here\n */\n",
            "slashes in a single-quoted string": "const s = 'a/b/c'\n",
            "regex-looking double-quoted string": 'const s = "/ab+c/"\n',
            "url in a string": "const u = 'https://example.test/x'\n",
            "slashes in template text": "const s = `/ab+c/ and a/b`\n",
            "slashes in a template next to interpolation": "const s = `a/${x}/b`\n",
        }
        for label, line in not_regex.items():
            with self.subTest(case=label):
                self.assertEqual(self.findings(self.GOOD + line), [])

    # AC9: a regex literal is also recognised after `=>`, operator characters and keywords; quote or backtick
    # characters inside it do not hide the rest of the file; division after `)`, `]`, an identifier or a number stays
    def test_workflow_regex_literal_after_operators(self) -> None:
        positions = {
            "after =>": "const f = (s) => /ab+c/.test(s)\n",
            "after => without parens": "const f = s =>/ab+c/.test(s)\n",
            "after +": "const r = a + /ab+c/.source\n",
            "after -": "const r = a - /ab+c/.source\n",
            "after *": "const r = a * /ab+c/.source\n",
            "after %": "const r = a % /ab+c/.source\n",
            "after <": "const r = a < /ab+c/.source\n",
            "after >": "const r = a > /ab+c/.source\n",
            "after ~": "const r = ~/ab+c/.exec(s)\n",
            "after ^": "const r = a ^ /ab+c/.source\n",
            "after return": "function f(s) { return /ab+c/.test(s) }\n",
            "after typeof": "const r = typeof /ab+c/\n",
            "after case": "switch (k) { case /ab+c/: break }\n",
            "after void": "const r = void /ab+c/\n",
            "after delete": "const r = delete /ab+c/.x\n",
            "after throw": "function f() { throw /ab+c/ }\n",
            "after in": "const r = k in /ab+c/\n",
            "after of": "for (const m of /ab+c/g) { go(m) }\n",
            "after instanceof": "const r = k instanceof /ab+c/\n",
            "after new": "const r = new /ab+c/\n",
            "after await": "const r = await /ab+c/\n",
            "after yield": "function* g() { yield /ab+c/ }\n",
        }
        for label, line in positions.items():
            with self.subTest(position=label):
                self.assert_regex_finding(self.findings(self.GOOD + line), 13)
        tails = "const t = Date.now()\nconst bad = await agent('p')\n"
        hiding = {
            "backtick after =>": "const f = s => /[`]/.test(s)\n",
            "single quote after =>": "const f = s => /[']/.test(s)\n",
            "double quote after =>": 'const f = s => /["]/.test(s)\n',
            "backtick after +": "const r = a + /[`]/.source\n",
            "single quote after -": "const r = a - /[']/.source\n",
            "double quote after <": 'const r = a < /["]/.source\n',
            "backtick after ~": "const r = ~/[`]/.exec(s)\n",
            "quote after return": "function f(s) { return /['\"]/.test(s) }\n",
            "backtick after typeof": "const r = typeof /[`]/\n",
            "quote after case": "switch (k) { case /[']/: break }\n",
            "backtick after await": "const r = await /[`]/\n",
        }
        for label, line in hiding.items():
            with self.subTest(hidden=label):
                found = self.findings(self.GOOD + line + tails)
                self.assert_regex_finding(found, 13)
                self.assertTrue(any("Date.now(" in e and re.search(r"\b14\b", e) for e in found), found)
                self.assertTrue(any("agentType" in e and re.search(r"\b15\b", e) for e in found), found)
        division = {
            "after an identifier, past a >": "const r = a > b / 2\n",
            "after an identifier, past a -": "const r = a - b / 2\n",
            "after a closing paren": "const r = (a + b) / 2\n",
            "after a closing paren, chained": "const r = (a + b) / 2 / c\n",
            "after a closing bracket": "const r = arr[0] / 2\n",
            "after a number": "const r = 3 / 4\n",
            "after a number, chained": "const r = 3 / 4 / 5\n",
            "after an identifier, chained": "const r = x > y / 2 / z\n",
            "after an identifier ending in a keyword (of)": "const r = proof / 2 / 3\n",
            "after an identifier ending in a keyword (in)": "const r = margin / 2 / 3\n",
            "after an identifier starting with a keyword": "const r = returned / 2 / 3\n",
            "after an identifier containing new": "const r = renew / 2 / 3\n",
        }
        for label, line in division.items():
            with self.subTest(division=label):
                self.assertEqual(self.findings(self.GOOD + line), [])

    # AC6: the shipped workflows/*.js are clean (the whole tree is also covered by test_shipped_tree_is_clean)
    def test_shipped_workflows_are_clean(self) -> None:
        shipped = sorted(p.name for p in (self.root / "workflows").glob("*.js"))
        self.assertEqual(shipped, [
            "br-ci.js", "br-deploy.js", "br-diagnose.js", "br-e2e.js",
            "br-janitor.js", "br-research.js", "br-review.js", "br-wave.js",
        ])
        self.assertEqual(validate.Validator(self.root).run(), [])


if __name__ == "__main__":
    unittest.main()
