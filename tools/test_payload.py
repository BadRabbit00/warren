"""Tests for the codex and agy exports of nix/payload.py. Run: python3 -I -B -m unittest discover -s tools -p test_*.py"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PAYLOAD = REPO / "nix" / "payload.py"

COPIED = (
    "agents", "rules", "skills", "commands", "core", "output-styles", "templates", "hooks", "tools",
    "agent-models.json", "settings.fragment.json", "LICENSE",
)
SKIPPED_PROMPTS = {"ask-astra", "write-astra"}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
AGENTS_MD_LIMIT = 24_000
EXPORTER_TIMEOUT = 120


def split(text: str) -> tuple[dict[str, str], str]:
    """Frontmatter as a flat key -> raw value map, and the text after it."""
    if not text.startswith("---\n"):
        raise ValueError(f"no frontmatter: {text[:40]!r}")
    end = text.index("\n---\n", 4)
    fm: dict[str, str] = {}
    for line in text[4:end].split("\n"):
        key, sep, value = line.partition(":")
        if sep and key and not key.startswith((" ", "-")):
            fm[key] = value.strip()
    return fm, text[end + 5:]


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def tool_list(value: str) -> set[str]:
    v = value.strip()
    if v.startswith("[") and v.endswith("]"):
        v = v[1:-1]
    return {t.strip().strip("'\"") for t in v.split(",") if t.strip()}


def make_tree(tmp: Path) -> Path:
    """Copies the source tree into tmp/br, the way the existing payload tests do."""
    root = tmp / "br"
    root.mkdir()
    for name in COPIED:
        src = REPO / name
        if src.is_dir():
            shutil.copytree(
                src, root / name, symlinks=True, ignore=shutil.ignore_patterns("__pycache__"),
                copy_function=shutil.copyfile,
            )
        else:
            shutil.copyfile(src, root / name)
    return root


def run_exporter(root: Path, out: Path) -> subprocess.CompletedProcess[str]:
    """Lays out the Claude tree like nix/payload.nix installPhase, then runs payload.py on it."""
    claude = out / "claude"
    for src, dst in (
        ("agents", "agents"), ("skills", "skills"), ("rules", "rules/br"), ("commands", "commands"),
        ("output-styles", "output-styles"), ("templates", "br/templates"),
    ):
        shutil.copytree(root / src, claude / dst, copy_function=shutil.copyfile)
    shutil.copyfile(root / "core" / "CLAUDE.md", claude / "CLAUDE.md")
    shutil.copyfile(root / "LICENSE", out / "LICENSE")
    shutil.copyfile(root / "settings.fragment.json", out / "settings.fragment.json")
    return subprocess.run(
        [sys.executable, "-I", "-B", str(PAYLOAD), str(out), str(root), "/x/br-hook"],
        capture_output=True, text=True, check=False, timeout=EXPORTER_TIMEOUT,
    )


@dataclass(frozen=True)
class Probe:
    """One extra agent injected into the source tree; `description` is the raw frontmatter value."""

    name: str
    description: str = "Reviews code."
    tools: str = "Read, Grep"
    body: str = "# Probe\n\nA probe agent.\n"


def add_probes(root: Path, *probes: Probe) -> None:
    models_path = root / "agent-models.json"
    models = json.loads(models_path.read_text(encoding="utf-8"))
    for probe in probes:
        text = f"---\nname: {probe.name}\ndescription: {probe.description}\ntools: {probe.tools}\n---\n\n{probe.body}"
        (root / "agents" / f"{probe.name}.md").write_text(text, encoding="utf-8")
        models["agents"][probe.name] = {
            "model": "claude-sonnet-5-5", "effort": "medium",
            "codex": {"model": "gpt-6-astra", "effort": "high"}, "agy": {"model": "flash"},
        }
    models_path.write_text(json.dumps(models), encoding="utf-8")


def export_with_probes(case: unittest.TestCase, *probes: Probe) -> tuple[Path, subprocess.CompletedProcess[str]]:
    """Runs the exporter on a fresh tree plus the probes; returns the output dir and the finished process."""
    tmp = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
    root = make_tree(tmp)
    add_probes(root, *probes)
    out = tmp / "out"
    return out, run_exporter(root, out)


def files_of(base: Path) -> dict[str, bytes]:
    return {str(p.relative_to(base)): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}


class ExportTest(unittest.TestCase):
    """One exporter run over a copy of the tree; every test inspects the same output."""

    tmp: Path
    root: Path
    out: Path
    proc: subprocess.CompletedProcess[str]
    models: dict[str, dict[str, dict[str, str]]]
    names: list[str]

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        cls.root = make_tree(cls.tmp)
        cls.out = cls.tmp / "out"
        cls.proc = run_exporter(cls.root, cls.out)
        cls.models = json.loads((cls.root / "agent-models.json").read_text(encoding="utf-8"))["agents"]
        cls.names = sorted(cls.models)

    def claude_agent(self, name: str) -> tuple[dict[str, str], str]:
        return split((self.out / "claude" / "agents" / f"{name}.md").read_text(encoding="utf-8"))

    def codex_agent(self, name: str) -> dict[str, object]:
        path = self.out / "codex" / "agents" / f"{name}.toml"
        self.assertTrue(path.is_file(), f"{path} missing; exporter stderr: {self.proc.stderr!r}")
        return tomllib.loads(path.read_text(encoding="utf-8"))

    def test_codex_agent_toml(self) -> None:
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        produced = sorted(p.stem for p in (self.out / "codex" / "agents").glob("*.toml"))
        self.assertEqual(produced, self.names)
        keys = {"name", "description", "model", "model_reasoning_effort", "sandbox_mode", "developer_instructions"}
        for name in self.names:
            data = self.codex_agent(name)
            fm, body = self.claude_agent(name)
            self.assertEqual(set(data), keys, name)
            self.assertEqual(data["name"], name)
            self.assertEqual(data["description"], fm["description"], name)
            self.assertEqual(data["model"], self.models[name]["codex"]["model"], name)
            self.assertEqual(data["model_reasoning_effort"], self.models[name]["codex"]["effort"], name)
            instructions = data["developer_instructions"]
            if not isinstance(instructions, str):
                self.fail(f"{name}: developer_instructions is {type(instructions).__name__}, not str")
            self.assertEqual(instructions.strip(), body.strip(), name)

    def test_codex_sandbox_mode(self) -> None:
        expected: dict[str, str] = {}
        for name in self.names:
            fm, _ = self.claude_agent(name)
            expected[name] = "workspace-write" if tool_list(fm["tools"]) & WRITE_TOOLS else "read-only"
        # Guard the guard: the rule above must give both outcomes on the real agents.
        for name in ("code-reviewer", "researcher"):
            self.assertEqual(expected[name], "read-only", name)
        for name in ("coder", "test-writer"):
            self.assertEqual(expected[name], "workspace-write", name)
        # Bash does not count: the codex read-only sandbox still runs commands, only without writes.
        self.assertEqual(
            sorted(n for n, mode in expected.items() if mode == "workspace-write"),
            [
                "build-fixer", "coder", "nix-build-resolver", "nix-engineer", "nix-test-runner",
                "presenter", "refactorer", "test-writer", "ui-verifier",
            ],
        )
        for name, mode in expected.items():
            self.assertEqual(self.codex_agent(name)["sandbox_mode"], mode, name)

    def test_codex_sandbox_mode_counts_multiedit_as_write(self) -> None:
        out, proc = export_with_probes(self, Probe("probe-multiedit", tools="Read, MultiEdit"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = tomllib.loads((out / "codex" / "agents" / "probe-multiedit.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["sandbox_mode"], "workspace-write")

    def test_codex_agents_fragment(self) -> None:
        path = self.out / "codex" / "agents.toml"
        self.assertTrue(path.is_file(), f"{path} missing; exporter stderr: {self.proc.stderr!r}")
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        agents = data["agents"]
        self.assertEqual(sorted(agents), sorted(n.replace("-", "_") for n in self.names))
        for name in self.names:
            entry = agents[name.replace("-", "_")]
            self.assertEqual(entry["config_file"], f"agents/{name}.toml", name)
            self.assertEqual(entry["description"], self.claude_agent(name)[0]["description"], name)

    def test_agy_agent_md(self) -> None:
        produced = sorted(p.stem for p in (self.out / "agy" / "agents").glob("*.md"))
        self.assertEqual(produced, self.names)
        for name in self.names:
            text = (self.out / "agy" / "agents" / f"{name}.md").read_text(encoding="utf-8")
            fm, body = split(text)
            self.assertEqual(set(fm), {"name", "description", "model", "subagent", "mainAgent"}, name)
            raw_frontmatter = text.split("\n---\n", 1)[0].split("\n")
            self.assertTrue(any(ln.startswith('description: "') for ln in raw_frontmatter), name)  # quoted scalar
            self.assertEqual(unquote(fm["name"]), name)
            self.assertEqual(unquote(fm["description"]), self.claude_agent(name)[0]["description"], name)
            self.assertEqual(unquote(fm["model"]), self.models[name]["agy"]["model"], name)
            self.assertEqual(fm["subagent"], "true", name)
            self.assertEqual(fm["mainAgent"], "true", name)
            self.assertEqual(body.strip(), self.claude_agent(name)[1].strip(), name)

    def test_codex_prompts(self) -> None:
        commands = sorted(p.stem for p in (self.root / "commands").glob("*.md"))
        self.assertTrue(set(commands) >= SKIPPED_PROMPTS)
        wanted = [c for c in commands if c not in SKIPPED_PROMPTS]
        prompts_dir = self.out / "codex" / "prompts"
        self.assertEqual(sorted(p.stem for p in prompts_dir.glob("*.md")), wanted)
        for cmd in wanted:
            lines = (prompts_dir / f"{cmd}.md").read_text(encoding="utf-8").split("\n")
            self.assertEqual(lines[0], f"# /{cmd}")
            self.assertEqual(lines.count(f"# /{cmd}"), 1, cmd)  # the heading is not prepended twice
            self.assertNotIn("---", lines, cmd)
            self.assertFalse(any(ln.startswith(("description:", "argument-hint:")) for ln in lines), cmd)
            _, body = split((self.root / "commands" / f"{cmd}.md").read_text(encoding="utf-8"))
            last = [ln for ln in body.split("\n") if ln.strip()][-1]
            self.assertIn(last, lines, cmd)

    def test_codex_skills_copy(self) -> None:
        source = files_of(self.out / "claude" / "skills")
        self.assertGreater(len(source), 0)
        copy_dir = self.out / "codex" / "skills"
        self.assertTrue(copy_dir.is_dir(), f"{copy_dir} missing; exporter stderr: {self.proc.stderr!r}")
        self.assertEqual(files_of(copy_dir), source)

    def test_agents_md(self) -> None:
        codex = self.out / "codex" / "AGENTS.md"
        agy = self.out / "agy" / "AGENTS.md"
        self.assertTrue(codex.is_file(), f"{codex} missing; exporter stderr: {self.proc.stderr!r}")
        self.assertTrue(agy.is_file(), f"{agy} missing")
        data = codex.read_bytes()
        self.assertEqual(data, agy.read_bytes())
        self.assertLessEqual(len(data), AGENTS_MD_LIMIT)
        text = data.decode("utf-8")
        self.assertTrue(text.startswith((self.root / "core" / "CLAUDE.md").read_text(encoding="utf-8")))
        for name in self.names:
            self.assertIn(name, text)


class ExportFailureTest(unittest.TestCase):
    def test_export_fails_on_literal_terminator(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        root = make_tree(tmp)
        agent = root / "agents" / "coder.md"
        agent.write_text(agent.read_text(encoding="utf-8") + "\nPrint it as '''text''' please.\n", encoding="utf-8")
        out = tmp / "out"
        proc = run_exporter(root, out)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("coder", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertFalse((out / "codex" / "agents" / "coder.toml").exists())

    def test_export_fails_on_block_scalar_description(self) -> None:
        for indicator in (">-", "|"):
            with self.subTest(indicator=indicator):
                name = "probe-block"
                out, proc = export_with_probes(
                    self, Probe(name, description=f"{indicator}\n  Reviews code across\n  several lines."),
                )
                self.assertNotEqual(proc.returncode, 0, proc.stdout)
                self.assertIn(name, proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertFalse((out / "codex" / "agents" / f"{name}.toml").exists())

    def test_export_fails_on_control_character(self) -> None:
        in_body = Probe("probe-ctl-body", body="# Probe\n\nform\x0cfeed\n")
        in_description = Probe("probe-ctl-desc", description="Reviews\x7fcode.")
        out, proc = export_with_probes(self, in_body, in_description)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn(in_body.name, proc.stderr)
        self.assertIn(in_description.name, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        for probe in (in_body, in_description):
            self.assertFalse((out / "codex" / "agents" / f"{probe.name}.toml").exists(), probe.name)


class ExportQuotedDescriptionTest(unittest.TestCase):
    def test_quoted_source_description_round_trips(self) -> None:
        probe = Probe("probe-quoted", description='"Reviews code."')
        out, proc = export_with_probes(self, probe)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        codex = tomllib.loads((out / "codex" / "agents" / "probe-quoted.toml").read_text(encoding="utf-8"))
        self.assertEqual(codex["description"], "Reviews code.")
        fragment = tomllib.loads((out / "codex" / "agents.toml").read_text(encoding="utf-8"))
        self.assertEqual(fragment["agents"]["probe_quoted"]["description"], "Reviews code.")
        agy_text = (out / "agy" / "agents" / "probe-quoted.md").read_text(encoding="utf-8")
        fm, _ = split(agy_text)
        self.assertEqual(unquote(fm["description"]), "Reviews code.")
        self.assertTrue(fm["description"].startswith('"'), fm["description"])


if __name__ == "__main__":
    unittest.main()
