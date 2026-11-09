#!/usr/bin/env python3
"""Installs br into a home directory: ~/.claude, ~/.codex, ~/.gemini/config.

Usage: install.py [--dest <home>] [--dry-run] [--check]
  --dest     target home directory (default: the user's home)
  --dry-run  print the actions, write nothing
  --check    run the validator and the tools and hooks test suites; exit non-zero on a failure
Builds the payload with tools/build.py into a temp dir (hook python = this interpreter), copies it,
and merges settings.json: user keys and foreign hooks stay, br-owned hooks (id "br:*") are replaced.
Stdlib only; runs on Windows, macOS and Linux.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 900

# (source under the built tree, target under --dest, replace the directory wholesale)
CLAUDE_DIRS = [
    ("agents", False), ("skills", False), ("commands", False), ("workflows", False),
    ("output-styles", False), ("rules/br", True), ("br/templates", True), ("br/hooks", True),
]


def run(cmd: list[str], cwd: Path) -> int:
    # Child output (stderr merged) is relayed on stdout: stderr carries only install.py's own errors.
    proc = subprocess.run(
        cmd, cwd=cwd, check=False, timeout=TIMEOUT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    print(proc.stdout, end="")
    return proc.returncode


def check() -> int:
    py = [sys.executable, "-I", "-B"]
    steps = [
        ("validator", [*py, str(ROOT / "tools" / "validate.py"), str(ROOT)], ROOT),
        ("tools tests", [*py, "-m", "unittest", "discover", "-s", "tools", "-p", "test_*.py"], ROOT),
        ("hooks tests", [*py, "-m", "unittest", "discover", "-s", "test", "-t", "test"], ROOT / "hooks"),
    ]
    failed = []
    for label, cmd, cwd in steps:
        print(f"== {label}", flush=True)
        if run(cmd, cwd) != 0:
            failed.append(label)
    if failed:
        print("check failed: " + ", ".join(failed), file=sys.stderr)
        return 1
    print("check passed")
    return 0


def plan_tree(src: Path, dst: Path, replace: bool) -> list[tuple[Path, Path]]:
    """File copies for one directory; stale files are removed first when `replace` is set."""
    return [(f, dst / f.relative_to(src)) for f in sorted(src.rglob("*")) if f.is_file() and "__pycache__" not in f.parts]


def merged_settings(existing: dict, fragment: dict, hooks_src: dict, claude: Path) -> dict:
    out = dict(existing)
    env = out.get("env")
    out["env"] = {**(env if isinstance(env, dict) else {}), **fragment.get("env", {})}
    if "outputStyle" in fragment:
        out["outputStyle"] = fragment["outputStyle"]
    hooks = out.get("hooks")
    hooks = dict(hooks) if isinstance(hooks, dict) else {}
    for event in list(hooks):
        kept = [e for e in hooks[event] if not str(e.get("id", "")).startswith("br:")]
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    for event, entries in hooks_src.items():
        added = []
        for entry in entries:
            entry = json.loads(json.dumps(entry))
            for h in entry["hooks"]:
                script = h["command"].split()[-1]
                h["command"] = f'"{sys.executable}" -I -B "{claude}/br/hooks/{script}.py"'
            added.append(entry)
        hooks[event] = hooks.get(event, []) + added
    out["hooks"] = hooks
    return out


def install(dest: Path, dry: bool) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        built = Path(tmp) / "payload"
        proc = subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools" / "build.py"), str(built), str(ROOT), sys.executable],
            cwd=ROOT, check=False, timeout=TIMEOUT, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print(proc.stdout + proc.stderr, file=sys.stderr)
            return 1

        claude, codex, gemini = dest / ".claude", dest / ".codex", dest / ".gemini" / "config"
        copies: list[tuple[Path, Path]] = []
        wipes: list[Path] = []
        copies.append((built / "claude" / "CLAUDE.md", claude / "CLAUDE.md"))
        for rel, replace in CLAUDE_DIRS:
            copies += plan_tree(built / "claude" / rel, claude / rel, replace)
            if replace:
                wipes.append(claude / rel)
        for rel in ("agents", "prompts", "skills"):
            copies += plan_tree(built / "codex" / rel, codex / rel, False)
        copies += [(built / "codex" / "AGENTS.md", codex / "AGENTS.md"), (built / "codex" / "agents.toml", codex / "agents.toml")]
        copies += plan_tree(built / "agy" / "agents", gemini / "agents", False)
        copies.append((built / "agy" / "AGENTS.md", gemini / "AGENTS.md"))

        settings_path = claude / "settings.json"
        existing: dict = {}
        if settings_path.is_file():
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        fragment = json.loads((built / "settings.fragment.json").read_text(encoding="utf-8"))
        hooks_src = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        text = json.dumps(merged_settings(existing, fragment, hooks_src, claude), indent=2, ensure_ascii=False) + "\n"

        if dry:
            for w in wipes:
                print(f"replace directory {w}")
            for _, dst in copies:
                print(f"write {dst}")
            print(f"merge {settings_path}")
            return 0
        for w in wipes:
            shutil.rmtree(w, ignore_errors=True)
        for src, dst in copies:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(text, encoding="utf-8")
        print(f"installed {len(copies)} files into {dest} (.claude, .codex, .gemini/config), merged {settings_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Install br into a home directory.")
    ap.add_argument("--dest", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        return check()
    dest = (args.dest if args.dest is not None else Path.home()).absolute()
    return install(dest, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
