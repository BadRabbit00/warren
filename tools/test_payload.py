"""Tests for tools/build.py: the br payload tree and the codex and agy exports. Run: python3 -I -B -m unittest discover -s tools -p test_*.py"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import types
import unittest
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BUILD = REPO / "tools" / "build.py"
# Absolute path of the interpreter the hooks run with; the space proves that build.py quotes it.
HOOK_PYTHON = "/opt/br test/bin/python3"

COPIED = (
    "agents", "rules", "skills", "commands", "core", "output-styles", "templates", "hooks", "tools",
    "agent-models.json", "settings.fragment.json", "LICENSE",
)
WORKFLOWS = (
    "br-ci.js", "br-deploy.js", "br-diagnose.js", "br-e2e.js",
    "br-janitor.js", "br-research.js", "br-review.js", "br-wave.js",
)
# Pins (P261110 D2): the shipped agents, skills and commands after the removal of everything Nix.
AGENTS_PINNED = (
    "architect-critic", "build-fixer", "ci-engineer", "code-reviewer", "coder", "db-reviewer",
    "deploy-engineer", "deploy-error-reader", "flutter-dart-reviewer", "go-coder", "go-reviewer",
    "janitor", "log-collector", "log-writer", "optimizer", "presenter", "python-coder", "python-reviewer",
    "refactorer", "researcher", "rust-coder", "rust-reviewer", "security-reviewer", "stand-operator",
    "test-runner", "test-writer", "ts-coder", "ts-react-reviewer", "ui-verifier", "web-researcher",
)
SKILLS_PINNED = (
    "api-design", "architecture-guide", "auth-service", "ci-github-actions", "cli-cloudflare",
    "cli-docker", "cli-doctl", "cli-gcloud", "cli-gh", "cli-railway", "cli-yc", "cloud-cloudflare",
    "cloud-digitalocean", "cloud-gcp", "cloud-railway", "cloud-yandex", "cost-aware-llm-pipeline",
    "dart-flutter-patterns", "database-migrations", "deploy-variants", "design-system",
    "docker-patterns", "documentation-lookup", "e2e-testing", "frontend-data-layer",
    "golang-patterns", "homelab-network-readiness", "homelab-network-setup", "homelab-pihole-dns",
    "homelab-vlan-segmentation", "homelab-wireguard-vpn", "iac", "logging", "mcp-server-patterns",
    "network-config-validation", "postgres-patterns", "project-docs", "prompt-caching-strategy",
    "python-service", "react-patterns", "recsys-pipeline-architect", "redis-patterns",
    "registry-dockerhub-ghcr", "rust-patterns", "security-review", "sops", "stack-choice",
    "user-flows", "vite-patterns",
)
COMMANDS_PINNED = (
    "ask-agy", "ask-argon", "ask-astra", "optimize", "policy-review", "test-affected",
    "write-agy", "write-argon", "write-astra",
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
    # workflows/*.js; a tree without workflows/ gets an empty directory, so a missing source fails an assertion.
    (root / "workflows").mkdir()
    for script in sorted((REPO / "workflows").glob("*.js")):
        shutil.copyfile(script, root / "workflows" / script.name)
    return root


def run_exporter(root: Path, out: Path) -> subprocess.CompletedProcess[str]:
    """Runs `python3 tools/build.py <out> <repo> <hook-python>` on the source tree `root`.

    build.py lays out the whole tree itself (the old Nix installPhase did the copying),
    so there is nothing to prepare in `out`.
    """
    return subprocess.run(
        [sys.executable, "-I", "-B", str(BUILD), str(out), str(root), HOOK_PYTHON],
        capture_output=True, text=True, check=False, timeout=EXPORTER_TIMEOUT,
    )


@dataclass(frozen=True)
class Probe:
    """One extra agent injected into the source tree; `description` is the raw frontmatter value."""

    name: str
    description: str = "Reviews code."
    tools: str = "Read, Grep"
    disallowed: str = ""
    body: str = "# Probe\n\nA probe agent.\n"


def add_probes(root: Path, *probes: Probe) -> None:
    models_path = root / "agent-models.json"
    models = json.loads(models_path.read_text(encoding="utf-8"))
    for probe in probes:
        denied = f"disallowedTools: {probe.disallowed}\n" if probe.disallowed else ""
        text = (
            f"---\nname: {probe.name}\ndescription: {probe.description}\ntools: {probe.tools}\n{denied}"
            f"---\n\n{probe.body}"
        )
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

    # AC1: the tree the Nix payload produced, with hooks called through the given interpreter
    def test_build_tree(self) -> None:
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        self.assertEqual(
            sorted(p.name for p in self.out.iterdir()),
            ["LICENSE", "agy", "claude", "codex", "hooks.json", "settings.fragment.json"],
        )
        claude = self.out / "claude"
        self.assertEqual(
            sorted(p.name for p in claude.iterdir()),
            ["CLAUDE.md", "agents", "br", "commands", "output-styles", "rules", "skills", "workflows"],
        )
        self.assertEqual(sorted(p.name for p in (claude / "br").iterdir()), ["hooks", "templates"])
        self.assertEqual((claude / "CLAUDE.md").read_bytes(), (self.root / "core" / "CLAUDE.md").read_bytes())
        self.assertEqual((self.out / "LICENSE").read_bytes(), (self.root / "LICENSE").read_bytes())
        self.assertEqual(
            (self.out / "settings.fragment.json").read_bytes(), (self.root / "settings.fragment.json").read_bytes(),
        )
        self.assertEqual(
            sorted(p.name for p in (claude / "rules" / "br").iterdir()),
            sorted(p.name for p in (self.root / "rules").glob("*.md")),
        )
        self.assertEqual(
            files_of(claude / "output-styles"), files_of(self.root / "output-styles"),
        )
        self.assertEqual(files_of(claude / "br" / "templates"), files_of(self.root / "templates"))

        # The hook files are copied next to the commands that call them.
        installed = claude / "br" / "hooks"
        sources = sorted(self.root.joinpath("hooks").glob("*.py")) + sorted(self.root.joinpath("hooks", "brhooks").glob("*.py"))
        self.assertGreaterEqual(len(sources), 5)
        for src in sources:
            rel = src.relative_to(self.root / "hooks")
            copy = installed / rel
            self.assertTrue(copy.is_file(), f"{copy} missing")
            self.assertEqual(copy.read_bytes(), src.read_bytes(), str(rel))

        # hooks.json: same ids and events as the source, commands through the interpreter, no placeholder.
        source_hooks = json.loads((self.root / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        built = json.loads((self.out / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(sorted(built), sorted(source_hooks))
        checked = 0
        for event, entries in source_hooks.items():
            self.assertEqual([e["id"] for e in built[event]], [e["id"] for e in entries], event)
            for src_entry, entry in zip(entries, built[event]):
                self.assertEqual(len(entry["hooks"]), len(src_entry["hooks"]))
                for src_hook, hook in zip(src_entry["hooks"], entry["hooks"]):
                    script = src_hook["command"].split()[-1]
                    want = f'"{HOOK_PYTHON}" -I -B "{self.out}/claude/br/hooks/{script}.py"'
                    self.assertEqual(hook["command"], want, entry["id"])
                    self.assertTrue((installed / f"{script}.py").is_file(), script)
                    checked += 1
        self.assertGreaterEqual(checked, 4)
        self.assertNotIn("@BR_HOOK@", (self.out / "hooks.json").read_text(encoding="utf-8"))

    # AC5: the pinned lists, without the Nix agents, skills and commands (D2)
    def test_payload_pins_agents_skills_commands(self) -> None:
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        claude = self.out / "claude"
        self.assertEqual(sorted(p.stem for p in (claude / "agents").glob("*.md")), sorted(AGENTS_PINNED))
        self.assertEqual(sorted(p.name for p in (claude / "skills").iterdir()), sorted(SKILLS_PINNED))
        self.assertEqual(sorted(p.stem for p in (claude / "commands").glob("*.md")), sorted(COMMANDS_PINNED))
        self.assertEqual(self.names, sorted(AGENTS_PINNED))
        self.assertEqual(sorted(p.stem for p in (self.out / "codex" / "agents").glob("*.toml")), sorted(AGENTS_PINNED))
        self.assertEqual(sorted(p.stem for p in (self.out / "agy" / "agents").glob("*.md")), sorted(AGENTS_PINNED))
        self.assertEqual(
            sorted(p.stem for p in (self.out / "codex" / "prompts").glob("*.md")),
            sorted(set(COMMANDS_PINNED) - SKIPPED_PROMPTS),
        )
        self.assertEqual(sorted(p.name for p in (self.out / "codex" / "skills").iterdir()), sorted(SKILLS_PINNED))
        self.assertEqual(
            sorted(p.stem for p in (claude / "rules" / "br").glob("*.md")),
            sorted(p.stem for p in (self.root / "rules").glob("*.md")),
        )
        self.assertFalse((claude / "rules" / "br" / "nix.md").exists())

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
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
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
                "build-fixer", "ci-engineer", "coder", "deploy-engineer", "go-coder",
                "log-writer",
                "presenter", "python-coder", "refactorer", "rust-coder", "test-writer",
                "ts-coder", "ui-verifier",
            ],
        )
        for name, mode in expected.items():
            self.assertEqual(self.codex_agent(name)["sandbox_mode"], mode, name)

    def test_codex_sandbox_mode_counts_multiedit_as_write(self) -> None:
        out, proc = export_with_probes(self, Probe("probe-multiedit", tools="Read, MultiEdit"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = tomllib.loads((out / "codex" / "agents" / "probe-multiedit.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["sandbox_mode"], "workspace-write")

    def test_codex_sandbox_mode_subtracts_disallowed(self) -> None:
        probe = Probe("probe-denied-write", tools="Read, Write", disallowed="Write, Agent, Skill, mcp__*")
        out, proc = export_with_probes(self, probe)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = tomllib.loads((out / "codex" / "agents" / "probe-denied-write.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["sandbox_mode"], "read-only")

    def test_codex_sandbox_mode_keeps_write_when_only_agent_disallowed(self) -> None:
        probe = Probe("probe-edit-kept", tools="Read, Edit", disallowed="Agent")
        out, proc = export_with_probes(self, probe)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = tomllib.loads((out / "codex" / "agents" / "probe-edit-kept.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["sandbox_mode"], "workspace-write")

    def test_codex_toml_self_check_rejects_bad_files(self) -> None:
        self.assertIn("codex toml ok", self.proc.stdout)
        spec = importlib.util.spec_from_file_location("br_build_under_test", BUILD)
        if spec is None or spec.loader is None:
            self.fail(f"cannot load {BUILD}")
        payload: types.ModuleType = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(payload)
        expected = len(self.names)

        def check(mutate: Callable[[Path], None]) -> list[str]:
            """Copies the real codex output, breaks it with `mutate`, runs the self-check, returns its errors."""
            work = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, work, ignore_errors=True)
            codex = work / "codex"
            shutil.copytree(self.out / "codex", codex, copy_function=shutil.copyfile)
            mutate(codex)
            payload.errors.clear()
            payload.codex_toml_check(codex, expected)
            return list(payload.errors)

        victim = self.names[0]

        def drop_sandbox(codex: Path) -> None:
            path = codex / "agents" / f"{victim}.toml"
            lines = path.read_text(encoding="utf-8").split("\n")
            path.write_text("\n".join(ln for ln in lines if not ln.startswith("sandbox_mode")), encoding="utf-8")

        def add_key(codex: Path) -> None:
            path = codex / "agents" / f"{victim}.toml"
            path.write_text('extra_key = "x"\n' + path.read_text(encoding="utf-8"), encoding="utf-8")

        def drop_table(codex: Path) -> None:
            path = codex / "agents.toml"
            tables = path.read_text(encoding="utf-8").split("\n[agents.")
            path.write_text("\n[agents.".join(tables[:-1]), encoding="utf-8")

        def drop_description(codex: Path) -> None:
            path = codex / "agents.toml"
            lines = path.read_text(encoding="utf-8").split("\n")
            index = next(i for i, ln in enumerate(lines) if ln.startswith("description"))
            del lines[index]
            path.write_text("\n".join(lines), encoding="utf-8")

        self.assertEqual(check(lambda codex: None), [], "untouched exporter output must pass")
        for label, mutate in (("missing sandbox_mode", drop_sandbox), ("extra key", add_key)):
            with self.subTest(case=label):
                found = check(mutate)
                self.assertTrue(any(f"{victim}.toml" in e for e in found), found)
        for label, mutate in (("table removed", drop_table), ("table without description", drop_description)):
            with self.subTest(case=label):
                found = check(mutate)
                self.assertTrue(any("agents.toml" in e for e in found), found)

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
            self.assertEqual(set(fm), {"name", "description", "model", "subagent", "mainAgent", "inheritMcp"}, name)
            raw_frontmatter = text.split("\n---\n", 1)[0].split("\n")
            self.assertIn("inheritMcp: false", raw_frontmatter, name)  # unquoted bool
            self.assertTrue(any(ln.startswith('description: "') for ln in raw_frontmatter), name)  # quoted scalar
            self.assertEqual(unquote(fm["name"]), name)
            self.assertEqual(unquote(fm["description"]), self.claude_agent(name)[0]["description"], name)
            self.assertEqual(unquote(fm["model"]), self.models[name]["agy"]["model"], name)
            self.assertEqual(fm["subagent"], "true", name)
            self.assertEqual(fm["mainAgent"], "true", name)
            self.assertEqual(body.strip(), self.claude_agent(name)[1].strip(), name)

    def test_workflows_installed(self) -> None:
        installed = self.out / "claude" / "workflows"
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        self.assertEqual(sorted(p.name for p in installed.iterdir()), sorted(WORKFLOWS))
        for name in WORKFLOWS:
            self.assertEqual((installed / name).read_bytes(), (self.root / "workflows" / name).read_bytes(), name)

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

    def test_export_fails_on_escaped_quoted_description(self) -> None:
        # Fail closed: YAML escapes inside a quoted description are not decoded by the exporter.
        probes = (
            Probe("probe-single-esc", description="'It''s fine.'"),
            Probe("probe-double-esc", description='"Say \\"hi\\""'),
        )
        for probe in probes:
            with self.subTest(agent=probe.name):
                out, proc = export_with_probes(self, probe)
                self.assertNotEqual(proc.returncode, 0, proc.stdout)
                self.assertIn(probe.name, proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)


class ExportWorkflowFailureTest(unittest.TestCase):
    def test_payload_rejects_workflow_without_meta(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        root = make_tree(tmp)
        bad = root / "workflows" / "bad.js"
        bad.write_text(
            "const x = 1\nexport const meta = {name: 'bad', description: 'x'}\n", encoding="utf-8",
        )
        proc = run_exporter(root, tmp / "out")
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("bad.js", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    # build.py copies the workflows itself now, so the old "installed tree was broken between the
    # copy and the check" tests (missing, modified, extra installed file) cannot be expressed: a
    # broken source workflow is the remaining way to hand it unreadable entries (AC1).
    def test_payload_rejects_binary_or_dir_source_workflow(self) -> None:
        def binary_js(workflows: Path) -> None:
            (workflows / "blob.js").write_bytes(b"\xff\xfe\x00\x80 not utf-8")

        def known_workflow_replaced_by_binary(workflows: Path) -> None:
            (workflows / "br-review.js").write_bytes(b"\xff\xfe\x00\x80")

        def known_workflow_replaced_by_dir(workflows: Path) -> None:
            path = workflows / "br-review.js"
            path.unlink()
            path.mkdir()

        cases = (
            ("blob.js", binary_js),
            ("br-review.js", known_workflow_replaced_by_binary),
            ("br-review.js", known_workflow_replaced_by_dir),
        )
        for name, break_source in cases:
            with self.subTest(case=break_source.__name__):
                tmp = Path(tempfile.mkdtemp())
                self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
                root = make_tree(tmp)
                break_source(root / "workflows")
                proc = run_exporter(root, tmp / "out")
                self.assertNotEqual(proc.returncode, 0, proc.stdout)
                self.assertIn(name, proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)

    def test_payload_accepts_block_comment_before_meta(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        root = make_tree(tmp)
        (root / "workflows" / "ok.js").write_text(
            "/* licence */\n// note\nexport const meta={name:'ok',description:'x'}\n", encoding="utf-8",
        )
        proc = run_exporter(root, tmp / "out")
        self.assertEqual(proc.returncode, 0, proc.stderr)


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
