"""Tests for validate.py. Run: python3 -I -B -m unittest discover -s tools -p test_*.py"""
from __future__ import annotations

import io
import json
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
PAYLOAD = REPO / "nix" / "payload.py"

COPIED = (
    "agents", "rules", "skills", "commands", "core", "output-styles", "templates", "hooks", "tools",
    "agent-models.json", "settings.fragment.json",
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
    # Explicit allowlist (mirrors the payload.nix fileset): copying the repo root would follow
    # .direnv symlinks into /nix/store and fail to clean up read-only files.
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

    # -- nix/payload.py

    def run_payload(self, agent_text: str) -> subprocess.CompletedProcess[str]:
        """Runs payload.py on a copy of the tree with one extra agent; returns the finished process."""
        out = self.tmp / "out"
        claude = out / "claude"
        for src, dst in (("agents", "agents"), ("skills", "skills"), ("rules", "rules/br"), ("commands", "commands")):
            shutil.copytree(self.root / src, claude / dst, copy_function=shutil.copyfile)
        shutil.copyfile(self.root / "settings.fragment.json", out / "settings.fragment.json")
        (claude / "agents" / "demo-agent.md").write_text(agent_text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-I", "-B", str(PAYLOAD), str(out), str(self.root), "/x/br-hook"],
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

    def test_body_rejects_toml_literal_terminator(self) -> None:
        baseline = validate.Validator(self.root).run()
        target = self.names[0]
        path = self.root / "agents" / f"{target}.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nPrint it as '''text''' please.\n", encoding="utf-8")
        self.assertTrue(self.findings_for(target, baseline), target)


if __name__ == "__main__":
    unittest.main()
