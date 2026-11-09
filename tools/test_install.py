"""Tests for tools/install.py: layout, settings merge, idempotence, --dry-run and --check.
Run: python3 -I -B -m unittest discover -s tools -p test_*.py

install.py is stdlib-only and runs the same on every OS; the tests run it as a user would
(`python3 tools/install.py --dest <home>`) with HOME pointed at an empty scratch directory, so a
write outside --dest shows up as a file in that directory.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
INSTALL = REPO / "tools" / "install.py"
RUN_TIMEOUT = 300

CONTRACT_HEADING = "## Contract (all br subagents)"
SKIPPED_PROMPTS = {"ask-astra", "write-astra"}
CACHES = shutil.ignore_patterns("__pycache__", ".ruff_cache", ".mypy_cache")


def files_of(base: Path) -> dict[str, bytes]:
    """Every regular file under base, keyed by its path relative to base."""
    if not base.exists():
        return {}
    return {str(p.relative_to(base)): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}


def source_hooks() -> dict[str, list[dict[str, object]]]:
    data = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    return data["hooks"]


def command_for(python: str, claude: Path, source_command: str) -> str:
    """The command install.py must write into settings.json for a hooks.json source command
    (`@BR_HOOK@ guard_bash`): the installing interpreter, then the copied hook file (D4)."""
    script = source_command.split()[-1]
    return f'"{python}" -I -B "{claude}/br/hooks/{script}.py"'


class InstallCase(unittest.TestCase):
    """A scratch directory with an empty fake HOME and a --dest next to it."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"  # HOME of the process: must stay empty
        self.home.mkdir()
        self.dest = self.tmp / "dest"
        self.claude = self.dest / ".claude"

    def install(self, *args: str, script: Path = INSTALL) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "HOME": str(self.home), "USERPROFILE": str(self.home)}
        return subprocess.run(
            [sys.executable, "-B", str(script), *args],
            capture_output=True, text=True, check=False, timeout=RUN_TIMEOUT, env=env, cwd=self.tmp,
        )

    def install_ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        proc = self.install("--dest", str(self.dest), *args)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        return proc

    def assert_nothing_outside_dest(self) -> None:
        self.assertEqual(files_of(self.home), {}, "install.py wrote into HOME instead of --dest")

    def write_user_settings(self) -> dict[str, object]:
        user: dict[str, object] = {
            "permissions": {"allow": ["Bash(ls)"], "deny": ["Read(./secrets/**)"]},
            "model": "opus",
            "env": {"MY_VAR": "1"},
            "outputStyle": "default",
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "/usr/local/bin/my-guard"}]},
                    {"id": "user:audit", "matcher": "Read", "hooks": [{"type": "command", "command": "audit-read"}]},
                    {
                        "id": "br:guard:bash", "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "/old/store/bin/br-hook guard_bash", "timeout": 10}],
                    },
                    {
                        "id": "br:retired:hook", "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "/old/store/bin/br-hook retired"}],
                    },
                ],
                "Stop": [{"hooks": [{"type": "command", "command": "say done"}]}],
            },
        }
        self.claude.mkdir(parents=True)
        (self.claude / "settings.json").write_text(json.dumps(user, indent=2), encoding="utf-8")
        return user


class InstallTest(InstallCase):
    # AC2: --dest lays out ~/.claude, ~/.codex and ~/.gemini/config
    def test_install_layout(self) -> None:
        self.install_ok()
        self.assert_nothing_outside_dest()

        agents = sorted(p.stem for p in (REPO / "agents").glob("*.md"))
        skills = sorted(p.name for p in (REPO / "skills").iterdir() if p.is_dir())
        commands = sorted(p.stem for p in (REPO / "commands").glob("*.md"))
        claude = self.claude

        self.assertEqual((claude / "CLAUDE.md").read_bytes(), (REPO / "core" / "CLAUDE.md").read_bytes())
        self.assertEqual(sorted(p.stem for p in (claude / "agents").glob("*.md")), agents)
        for name in agents:
            text = (claude / "agents" / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn(CONTRACT_HEADING, text, name)  # the built agent, not the raw source
            self.assertIn("omitClaudeMd: true", text, name)
        self.assertEqual(sorted(p.name for p in (claude / "skills").iterdir()), skills)
        self.assertEqual(sorted(p.stem for p in (claude / "commands").glob("*.md")), commands)
        self.assertEqual(files_of(claude / "workflows"), {p.name: p.read_bytes() for p in (REPO / "workflows").glob("*.js")})
        self.assertEqual(
            files_of(claude / "rules" / "br"), {p.name: p.read_bytes() for p in (REPO / "rules").glob("*.md")},
        )
        self.assertEqual(files_of(claude / "output-styles"), files_of(REPO / "output-styles"))
        self.assertEqual(files_of(claude / "br" / "templates"), files_of(REPO / "templates"))
        for src in sorted((REPO / "hooks").glob("*.py")) + sorted((REPO / "hooks" / "brhooks").glob("*.py")):
            copy = claude / "br" / "hooks" / src.relative_to(REPO / "hooks")
            self.assertTrue(copy.is_file(), f"{copy} missing")
            self.assertEqual(copy.read_bytes(), src.read_bytes(), str(copy))

        codex = self.dest / ".codex"
        self.assertEqual(sorted(p.stem for p in (codex / "agents").glob("*.toml")), agents)
        for toml in (codex / "agents").glob("*.toml"):
            self.assertEqual(tomllib.loads(toml.read_text(encoding="utf-8"))["name"], toml.stem)
        self.assertEqual(
            sorted(p.stem for p in (codex / "prompts").glob("*.md")), sorted(set(commands) - SKIPPED_PROMPTS),
        )
        self.assertEqual(sorted(p.name for p in (codex / "skills").iterdir()), skills)
        agents_md = (codex / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(agents_md.startswith((REPO / "core" / "CLAUDE.md").read_text(encoding="utf-8")))
        # The [agents.*] tables reach codex: as agents.toml next to config.toml, or merged into config.toml.
        tables = "".join(
            p.read_text(encoding="utf-8") for p in (codex / "agents.toml", codex / "config.toml") if p.is_file()
        )
        self.assertIn("[agents.coder]", tables)

        gemini_agents = self.dest / ".gemini" / "config" / "agents"
        self.assertEqual(sorted(p.stem for p in gemini_agents.glob("*.md")), agents)

        settings = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["outputStyle"], "orchestrator")
        self.assertEqual(settings["env"]["CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"], "1")
        for event, entries in source_hooks().items():
            installed = {e["id"]: e for e in settings["hooks"][event]}
            for entry in entries:
                hooks = installed[entry["id"]]["hooks"]
                self.assertEqual(
                    [h["command"] for h in hooks],
                    [command_for(sys.executable, claude, h["command"]) for h in entry["hooks"]],  # type: ignore[index]
                    entry["id"],
                )

    # AC2: the merge keeps what the user has and replaces only br-owned hooks
    def test_install_merges_settings(self) -> None:
        user = self.write_user_settings()
        self.install_ok()
        settings = json.loads((self.claude / "settings.json").read_text(encoding="utf-8"))

        # Unknown user keys stay exactly as they were.
        self.assertEqual(settings["permissions"], user["permissions"])
        self.assertEqual(settings["model"], "opus")
        self.assertEqual(settings["env"]["MY_VAR"], "1")
        # What br owns is set.
        self.assertEqual(settings["outputStyle"], "orchestrator")
        self.assertEqual(settings["env"]["CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"], "1")

        user_hooks = user["hooks"]  # type: ignore[index]
        pre = settings["hooks"]["PreToolUse"]
        for foreign in user_hooks["PreToolUse"][:2]:  # type: ignore[index]
            self.assertIn(foreign, pre)
        self.assertEqual(settings["hooks"]["Stop"], user_hooks["Stop"])  # type: ignore[index]

        br_ids = [e["id"] for entries in settings["hooks"].values() for e in entries if str(e.get("id", "")).startswith("br:")]
        want_ids = [e["id"] for entries in source_hooks().values() for e in entries]
        self.assertEqual(sorted(br_ids), sorted(want_ids))  # one entry per br hook: replaced, not duplicated
        self.assertNotIn("br:retired:hook", br_ids)  # br-owned entries that br no longer ships are dropped
        text = json.dumps(settings)
        self.assertNotIn("/old/store", text)
        replaced = next(e for e in pre if e.get("id") == "br:guard:bash")
        self.assertEqual(
            replaced["hooks"][0]["command"],
            f'"{sys.executable}" -I -B "{self.claude}/br/hooks/guard_bash.py"',
        )

    # AC2: a second run changes nothing
    def test_install_idempotent(self) -> None:
        self.write_user_settings()
        self.install_ok()
        first = files_of(self.dest)
        self.assertIn(".claude/settings.json", first)
        self.install_ok()
        second = files_of(self.dest)
        self.assertEqual(sorted(second), sorted(first))
        changed = [name for name in first if first[name] != second[name]]
        self.assertEqual(changed, [])
        self.assert_nothing_outside_dest()

    # AC2: --dry-run lists what it would do and writes nothing
    def test_install_dry_run(self) -> None:
        proc = self.install("--dest", str(self.dest), "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(files_of(self.dest), {}, "dry run created files")
        self.assertEqual([p for p in self.dest.rglob("*")] if self.dest.exists() else [], [], "dry run created entries")
        self.assert_nothing_outside_dest()
        for needle in (".claude", ".codex", ".gemini", "settings.json"):
            self.assertIn(needle, proc.stdout, f"the action list does not mention {needle}")

        # With an existing install and user settings: still byte-for-byte the same afterwards.
        self.write_user_settings()
        self.install_ok()
        (self.claude / "agents" / "coder.md").write_text("changed by the user\n", encoding="utf-8")
        before = files_of(self.dest)
        again = self.install("--dest", str(self.dest), "--dry-run")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(files_of(self.dest), before)
        self.assertIn("settings.json", again.stdout)


def chmod_tree_writable(path: Path) -> None:
    """Undo the read-only modes of a test so the scratch directory can be removed."""
    if not path.exists():
        return
    for p in [path, *path.rglob("*")]:
        if not p.is_symlink():
            p.chmod(0o755 if p.is_dir() else 0o644)


def posix(text: str) -> str:
    return text.replace("\\\\", "/").replace("\\", "/")


class InstallSafetyTest(InstallCase):
    """AC6-AC10 (checkpoint C1): old layouts, manifest, backups, malformed settings, hook commands."""

    def make_store(self) -> Path:
        """A read-only 'store' like the one home-manager links into: files 0444, directories 0555."""
        store = self.tmp / "store"
        (store / "agents").mkdir(parents=True)
        (store / "rules-br").mkdir()
        (store / "CLAUDE.md").write_text("old store CLAUDE.md\n", encoding="utf-8")
        (store / "agents" / "coder.md").write_text("old store coder\n", encoding="utf-8")
        (store / "rules-br" / "python.md").write_text("old store rule\n", encoding="utf-8")
        for p in sorted(store.rglob("*"), reverse=True):
            p.chmod(0o555 if p.is_dir() else 0o444)
        store.chmod(0o555)
        self.addCleanup(chmod_tree_writable, store)
        return store

    # AC6: symlinks into a read-only store are replaced by regular files, the store is not touched
    def test_install_over_readonly_symlinks(self) -> None:
        store = self.make_store()
        before_store = files_of(store)
        (self.claude / "agents").mkdir(parents=True)
        (self.claude / "rules").mkdir()
        (self.claude / "CLAUDE.md").symlink_to(store / "CLAUDE.md")
        (self.claude / "agents" / "coder.md").symlink_to(store / "agents" / "coder.md")
        (self.claude / "rules" / "br").symlink_to(store / "rules-br", target_is_directory=True)

        self.install_ok()

        self.assertFalse((self.claude / "CLAUDE.md").is_symlink())
        self.assertEqual((self.claude / "CLAUDE.md").read_bytes(), (REPO / "core" / "CLAUDE.md").read_bytes())
        self.assertFalse((self.claude / "agents" / "coder.md").is_symlink())
        self.assertIn(CONTRACT_HEADING, (self.claude / "agents" / "coder.md").read_text(encoding="utf-8"))
        self.assertFalse((self.claude / "rules" / "br").is_symlink())
        self.assertTrue((self.claude / "rules" / "br").is_dir())
        self.assertEqual(
            files_of(self.claude / "rules" / "br"), {p.name: p.read_bytes() for p in (REPO / "rules").glob("*.md")},
        )
        self.assertEqual(files_of(store), before_store, "the read-only store was modified")
        self.assert_nothing_outside_dest()

    # AC6: a target that cannot be replaced stops the run before anything is deleted
    @unittest.skipIf(
        hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores read-only modes, so the blocker cannot be built",
    )
    def test_install_preflight_stops_before_deleting(self) -> None:
        user = self.write_user_settings()
        for rel, text in (
            ("agents/coder.md", "old coder\n"),
            ("agents/mine.md", "my agent\n"),
            ("rules/br/old-rule.md", "old rule\n"),
            ("br/templates/old.md", "old template\n"),
        ):
            path = self.claude / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        # br/hooks must become a directory, but it is a regular file inside a read-only parent.
        (self.claude / "br" / "hooks").write_text("not a directory\n", encoding="utf-8")
        (self.claude / "br").chmod(0o555)
        self.addCleanup(chmod_tree_writable, self.claude)
        before = files_of(self.dest)

        proc = self.install("--dest", str(self.dest))

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn(str(self.claude / "br"), proc.stderr, "the message does not name the blocking path")
        self.assertEqual(files_of(self.dest), before, "the run changed or deleted files before stopping")
        self.assertEqual(
            json.loads((self.claude / "settings.json").read_text(encoding="utf-8")), user, "settings.json changed",
        )
        self.assert_nothing_outside_dest()

    def copy_tree(self, name: str) -> Path:
        """A copy of the repo's payload sources (no tests) whose install.py can run on its own."""
        root = self.tmp / name
        root.mkdir()
        for sub in (
            "agents", "rules", "skills", "commands", "core", "output-styles", "templates", "hooks", "tools", "workflows",
        ):
            shutil.copytree(REPO / sub, root / sub, symlinks=True, ignore=CACHES, copy_function=shutil.copyfile)
        for sub in ("agent-models.json", "settings.fragment.json", "LICENSE"):
            shutil.copyfile(REPO / sub, root / sub)
        for old in (root / "tools").glob("test_*.py"):
            old.unlink()
        shutil.rmtree(root / "hooks" / "test", ignore_errors=True)
        return root

    # AC7: the manifest drives removal of files br installed before and the payload dropped
    def test_install_removes_files_it_installed_before(self) -> None:
        root = self.copy_tree("tree")
        script = root / "tools" / "install.py"
        proc = self.install("--dest", str(self.dest), script=script)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        manifest_path = self.claude / "br" / "manifest.json"
        self.assertTrue(manifest_path.is_file(), "no manifest at ~/.claude/br/manifest.json")
        manifest_text = posix(manifest_path.read_text(encoding="utf-8"))
        json.loads(manifest_text)  # valid JSON
        self.assertIn("commands/optimize.md", manifest_text)
        self.assertIn("workflows/br-research.js", manifest_text)

        (self.claude / "agents" / "my-own-agent.md").write_text("mine\n", encoding="utf-8")
        (self.claude / "commands" / "my-own.md").write_text("mine\n", encoding="utf-8")
        self.assertTrue((self.claude / "commands" / "optimize.md").is_file())
        self.assertTrue((self.claude / "workflows" / "br-research.js").is_file())
        self.assertTrue((self.dest / ".codex" / "prompts" / "optimize.md").is_file())

        (root / "commands" / "optimize.md").unlink()
        (root / "workflows" / "br-research.js").unlink()
        proc = self.install("--dest", str(self.dest), script=script)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

        self.assertFalse((self.claude / "commands" / "optimize.md").exists(), "dropped command still installed")
        self.assertFalse((self.claude / "workflows" / "br-research.js").exists(), "dropped workflow still installed")
        self.assertFalse((self.dest / ".codex" / "prompts" / "optimize.md").exists(), "dropped codex prompt still there")
        self.assertEqual((self.claude / "agents" / "my-own-agent.md").read_text(encoding="utf-8"), "mine\n")
        self.assertEqual((self.claude / "commands" / "my-own.md").read_text(encoding="utf-8"), "mine\n")
        self.assertTrue((self.claude / "commands" / "policy-review.md").is_file())  # shipped files stay
        manifest_text = posix(manifest_path.read_text(encoding="utf-8"))
        self.assertNotIn("commands/optimize.md", manifest_text)
        self.assertIn("commands/policy-review.md", manifest_text)
        self.assertNotIn("my-own", manifest_text, "the manifest lists a user's own file")

    # AC8: a different user file is kept as <name>.bak-<timestamp>; an identical one is not
    def test_install_backs_up_replaced_user_files(self) -> None:
        targets = [
            self.claude / "CLAUDE.md",
            self.dest / ".codex" / "AGENTS.md",
            self.dest / ".gemini" / "config" / "AGENTS.md",
        ]
        for path in targets:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"my own notes in {path.parent.name}\n", encoding="utf-8")

        self.install_ok()

        for path in targets:
            backups = sorted(path.parent.glob(f"{path.name}.bak-*"))
            self.assertEqual(len(backups), 1, f"{path}: backups {[b.name for b in backups]}")
            self.assertGreater(len(backups[0].name), len(f"{path.name}.bak-"), "empty timestamp")
            self.assertEqual(backups[0].read_text(encoding="utf-8"), f"my own notes in {path.parent.name}\n")
            self.assertNotEqual(path.read_text(encoding="utf-8"), backups[0].read_text(encoding="utf-8"))
        self.assertEqual((self.claude / "CLAUDE.md").read_bytes(), (REPO / "core" / "CLAUDE.md").read_bytes())

        # Second run: the files are br's own now, so no new backups appear.
        self.install_ok()
        for path in targets:
            self.assertEqual(len(list(path.parent.glob(f"{path.name}.bak-*"))), 1, f"{path}: a second backup appeared")

    # AC8: nothing to back up on a fresh home
    def test_install_makes_no_backup_when_nothing_was_there(self) -> None:
        self.install_ok()
        self.assertEqual(list(self.dest.rglob("*.bak-*")), [])

    # AC9: a malformed settings.json stops the run before anything is written
    def test_install_rejects_malformed_settings(self) -> None:
        cases = {
            "invalid json": "{not json",
            "empty file": "",
            "top level not an object": "[]",
            "hooks not an object": json.dumps({"model": "opus", "hooks": []}),
            "event value not a list": json.dumps({"hooks": {"PreToolUse": {"matcher": "Bash"}}}),
        }
        for label, text in cases.items():
            with self.subTest(case=label):
                shutil.rmtree(self.dest, ignore_errors=True)
                self.claude.mkdir(parents=True)
                (self.claude / "settings.json").write_text(text, encoding="utf-8")
                before = files_of(self.dest)

                proc = self.install("--dest", str(self.dest))

                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertIn("settings.json:", proc.stderr)
                self.assertEqual(files_of(self.dest), before, "files were written despite the bad settings.json")
                self.assert_nothing_outside_dest()

    # AC9: settings are written atomically: no temporary file is left behind
    def test_install_leaves_no_temporary_settings_file(self) -> None:
        self.write_user_settings()
        self.install_ok()
        self.install_ok()
        leftovers = [str(p) for p in self.dest.rglob("*") if ".tmp" in p.name]
        self.assertEqual(leftovers, [])

    # AC10: the hook commands in settings.json are the built hooks.json commands, one substitution
    def test_install_hook_commands_match_build(self) -> None:
        built = self.tmp / "built"
        proc = subprocess.run(
            [sys.executable, "-B", str(REPO / "tools" / "build.py"), str(built), str(REPO), sys.executable],
            capture_output=True, text=True, check=False, timeout=RUN_TIMEOUT,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        built_hooks = json.loads((built / "hooks.json").read_text(encoding="utf-8"))["hooks"]

        self.write_user_settings()
        self.install_ok()
        settings = json.loads((self.claude / "settings.json").read_text(encoding="utf-8"))

        count = 0
        for event, entries in built_hooks.items():
            installed = {e["id"]: e for e in settings["hooks"][event] if "id" in e}
            for entry in entries:
                got = [h["command"] for h in installed[entry["id"]]["hooks"]]
                want = [h["command"].replace(f"{built}/claude", str(self.claude)) for h in entry["hooks"]]
                self.assertEqual(got, want, entry["id"])
                count += len(want)
        self.assertGreater(count, 0)

    # AC10: a hook python in a temporary path is warned about (the installed hooks would break)
    def test_install_warns_when_hook_python_is_temporary(self) -> None:
        link = self.tmp / "venv-like" / "bin" / "python"
        link.parent.mkdir(parents=True)
        link.symlink_to(sys.executable)
        env = {**os.environ, "HOME": str(self.home), "USERPROFILE": str(self.home)}
        proc = subprocess.run(
            [str(link), "-B", str(INSTALL), "--dest", str(self.dest)],
            capture_output=True, text=True, check=False, timeout=RUN_TIMEOUT, env=env, cwd=self.tmp,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("warning", (proc.stdout + proc.stderr).lower())


class InstallCheckTest(InstallCase):
    """--check runs the validator, the tools tests and the hooks tests of the tree install.py sits in.

    The real tree is not used: its tools tests include this file, so `--check` on it would recurse.
    Each case copies the tree, empties both test directories, puts one marker test in each and
    replaces the validator with a stub, then checks that exactly the broken part fails the run.
    """

    PASSING = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_marker_passes(self) -> None:\n        self.assertTrue(True)\n"
    FAILING = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_{name}(self) -> None:\n        self.fail('{name}-marker')\n"
    STUB = (
        "import sys\n\nFINDINGS = {findings!r}\n\n\nclass Validator:\n"
        "    def __init__(self, root, *a, **k):\n        self.root = root\n\n"
        "    def run(self):\n        return list(FINDINGS)\n\n\n"
        "def main():\n    for f in FINDINGS:\n        print(f)\n    return 1 if FINDINGS else 0\n\n\n"
        "if __name__ == '__main__':\n    sys.exit(main())\n"
    )

    def make_tree(self, *, findings: list[str], tools_test: str, hooks_test: str) -> Path:
        root = self.tmp / "tree"
        root.mkdir()
        for name in (
            "agents", "rules", "skills", "commands", "core", "output-styles", "templates", "hooks", "tools", "workflows",
        ):
            shutil.copytree(REPO / name, root / name, symlinks=True, ignore=CACHES, copy_function=shutil.copyfile)
        for name in ("agent-models.json", "settings.fragment.json", "LICENSE"):
            shutil.copyfile(REPO / name, root / name)
        for old in (root / "tools").glob("test_*.py"):
            old.unlink()
        for old in (root / "hooks" / "test").glob("*.py"):
            old.unlink()
        (root / "tools" / "validate.py").write_text(self.STUB.format(findings=findings), encoding="utf-8")
        (root / "tools" / "test_marker.py").write_text(tools_test, encoding="utf-8")
        (root / "hooks" / "test" / "test_marker.py").write_text(hooks_test, encoding="utf-8")
        return root

    def run_check(self, root: Path) -> tuple[int, str]:
        proc = self.install("--check", script=root / "tools" / "install.py")
        out = proc.stdout + proc.stderr
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(files_of(self.home), {}, "--check wrote into HOME")
        return proc.returncode, out

    # AC3
    def test_install_check(self) -> None:
        failing_tools = self.FAILING.format(name="tools_suite")
        failing_hooks = self.FAILING.format(name="hooks_suite")
        cases = (
            ("everything passes", [], self.PASSING, self.PASSING, True, ""),
            ("validator finding", ["agents/demo.md: validator-marker"], self.PASSING, self.PASSING, False, "validator-marker"),
            ("tools test fails", [], failing_tools, self.PASSING, False, "tools_suite-marker"),
            ("hooks test fails", [], self.PASSING, failing_hooks, False, "hooks_suite-marker"),
        )
        for label, findings, tools_test, hooks_test, ok, marker in cases:
            with self.subTest(case=label):
                shutil.rmtree(self.tmp / "tree", ignore_errors=True)
                root = self.make_tree(findings=findings, tools_test=tools_test, hooks_test=hooks_test)
                code, out = self.run_check(root)
                if ok:
                    self.assertEqual(code, 0, out)
                else:
                    self.assertNotEqual(code, 0, out)
                    self.assertIn(marker, out, "the failing part is not shown")


if __name__ == "__main__":
    unittest.main()
