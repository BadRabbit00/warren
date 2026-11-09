"""Tests for the codex and agy exports of nix/payload.py. Run: python3 -I -B -m unittest discover -s tools -p test_*.py"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PAYLOAD = REPO / "nix" / "payload.py"

COPIED = (
    "agents", "rules", "skills", "commands", "core", "output-styles", "templates", "hooks", "tools",
    "agent-models.json", "settings.fragment.json", "LICENSE",
)
SKIPPED_PROMPTS = {"ask-astra", "write-astra"}
WRITE_TOOLS = {"Write", "Edit", "NotebookEdit"}
AGENTS_MD_LIMIT = 24_000


def split(text: str) -> tuple[dict[str, str], str]:
    """Frontmatter as a flat key -> raw value map, and the text after it."""
    assert text.startswith("---\n"), text[:40]
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
        capture_output=True, text=True, check=False,
    )


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
            assert isinstance(instructions, str)
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
            fm, body = split((self.out / "agy" / "agents" / f"{name}.md").read_text(encoding="utf-8"))
            self.assertEqual(set(fm), {"name", "description", "model", "subagent", "mainAgent"}, name)
            self.assertEqual(unquote(fm["name"]), name)
            self.assertEqual(unquote(fm["description"]), self.claude_agent(name)[0]["description"], name)
            self.assertEqual(unquote(fm["model"]), self.models[name]["agy"]["model"], name)
            self.assertEqual(fm["subagent"], "true", name)
            self.assertEqual(fm["mainAgent"], "true", name)
            self.assertEqual(body.strip(), self.claude_agent(name)[1].strip(), name)

    def test_codex_prompts(self) -> None:
        commands = sorted(p.stem for p in (self.root / "commands").glob("*.md"))
        self.assertTrue(SKIPPED_PROMPTS <= set(commands))
        wanted = [c for c in commands if c not in SKIPPED_PROMPTS]
        prompts_dir = self.out / "codex" / "prompts"
        self.assertEqual(sorted(p.stem for p in prompts_dir.glob("*.md")), wanted)
        for cmd in wanted:
            lines = (prompts_dir / f"{cmd}.md").read_text(encoding="utf-8").split("\n")
            self.assertEqual(lines[0], f"# /{cmd}")
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


if __name__ == "__main__":
    unittest.main()
