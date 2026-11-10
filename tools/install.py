#!/usr/bin/env python3
"""Installs br into a home directory: ~/.claude, ~/.codex, ~/.gemini/config.

Usage: install.py [--dest <home>] [--dry-run] [--check]
  --dest     target home directory (default: the user's home)
  --dry-run  print the actions, write nothing
  --check    run the validator and the tools and hooks test suites; exit non-zero on a failure
Builds the payload with tools/build.py into a temp dir (the hooks run as python3), copies it,
and merges settings.json: user keys and foreign hooks stay, br-owned hooks (id "br:*") are replaced.
Every target is checked before anything is deleted. ~/.claude/br/manifest.json lists the installed
files, so the next run removes the ones the payload dropped and never touches the user's own files.
Stdlib only; runs on Windows, macOS and Linux.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 900

# (source under the built tree, target under --dest, replace the directory wholesale)
CLAUDE_DIRS = [
    ("agents", False), ("skills", False), ("commands", False), ("workflows", False),
    ("output-styles", False), ("rules/br", True), ("br/templates", True), ("br/hooks", True),
]


class InstallError(Exception):
    """A reason to stop with exit code 1; the message goes to stderr."""


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


def plan_tree(src: Path, dst: Path) -> list[tuple[Path, Path]]:
    return [(f, dst / f.relative_to(src)) for f in sorted(src.rglob("*")) if f.is_file() and "__pycache__" not in f.parts]


def load_settings(path: Path) -> dict:
    """The user's settings.json, checked for the shapes the merge relies on."""
    if not os.path.lexists(path):
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # ValueError covers JSONDecodeError and UnicodeDecodeError
        raise InstallError(f"settings.json: {exc}") from exc
    if not isinstance(data, dict):
        raise InstallError("settings.json: the top level must be an object")
    hooks = data.get("hooks")
    if hooks is not None:
        if not isinstance(hooks, dict):
            raise InstallError("settings.json: 'hooks' must be an object")
        for event, entries in hooks.items():
            if not isinstance(entries, list):
                raise InstallError(f"settings.json: hooks.{event} must be a list")
            if not all(isinstance(e, dict) for e in entries):
                raise InstallError(f"settings.json: every entry of hooks.{event} must be an object")
    return data


def merged_settings(existing: dict, fragment: dict, hooks_built: dict) -> dict:
    """hooks_built already carries the final commands (build.py output, path rewritten by the caller)."""
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
    for event, entries in hooks_built.items():
        hooks[event] = hooks.get(event, []) + entries
    out["hooks"] = hooks
    return out


def writable_dir(path: Path) -> bool:
    return os.access(path, os.W_OK | os.X_OK)


def blocker(target: Path) -> str | None:
    """Why `target` cannot be created or replaced as a file, or None."""
    if os.path.lexists(target):
        if target.is_dir() and not target.is_symlink():
            return f"{target} is a directory, a file must go there"
        if not writable_dir(target.parent):
            return f"cannot replace {target}: {target.parent} is not writable"
        return None
    ancestor = target.parent
    while not os.path.lexists(ancestor):
        ancestor = ancestor.parent
    if not ancestor.is_dir():
        return f"cannot create {target}: {ancestor} is not a directory"
    if not writable_dir(ancestor):
        return f"cannot create {target}: {ancestor} is not writable"
    return None


def wipe_blocker(target: Path) -> str | None:
    """Why the directory `target` cannot be removed (a symlink is just unlinked), or None."""
    if not os.path.lexists(target):
        return _create_blocker(target)
    if not writable_dir(target.parent):
        return f"cannot replace {target}: {target.parent} is not writable"
    if target.is_symlink() or not target.is_dir():
        return None
    for dirpath, dirnames, _ in os.walk(target):
        if not writable_dir(Path(dirpath)):
            return f"cannot remove inside {target}: {dirpath} is not writable"
        dirnames[:] = [d for d in dirnames if not (Path(dirpath) / d).is_symlink()]
    return None


def _create_blocker(target: Path) -> str | None:
    ancestor = target.parent
    while not os.path.lexists(ancestor):
        ancestor = ancestor.parent
    if not ancestor.is_dir():
        return f"cannot create {target}: {ancestor} is not a directory"
    if not writable_dir(ancestor):
        return f"cannot create {target}: {ancestor} is not writable"
    return None


def read_manifest(path: Path, dest: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        files = data["files"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    if not isinstance(files, list):
        return []
    root = dest.resolve()
    good = []
    for rel in files:
        if not isinstance(rel, str) or not rel:
            continue
        parts = Path(rel).parts
        if Path(rel).is_absolute() or ".." in parts:
            continue
        if not (root / rel).parent.resolve().is_relative_to(root):
            continue
        good.append(rel)
    return good


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def check_hook_python() -> None:
    """The installed hooks run as `python3` from PATH; stop early when it is missing or older than 3.11."""
    found = shutil.which("python3")
    if not found:
        raise InstallError("install stopped: python3 is not on PATH; the br hooks run as python3 (3.11+ required)")
    try:
        proc = subprocess.run([found, "--version"], check=False, timeout=30, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as err:
        raise InstallError(f"install stopped: cannot run python3 ({found}): {err}; 3.11+ is required") from err
    out = (proc.stdout + proc.stderr).strip()
    m = re.match(r"Python (\d+)\.(\d+)", out)
    if proc.returncode != 0 or not m or (int(m.group(1)), int(m.group(2))) < (3, 11):
        raise InstallError(
            f"install stopped: python3 ({found}) reports {out or 'no version'}; the br hooks need python3 3.11+"
        )


def backup_name(path: Path, stamp: str) -> Path:
    candidate = path.with_name(f"{path.name}.bak-{stamp}")
    n = 1
    while os.path.lexists(candidate):
        n += 1
        candidate = path.with_name(f"{path.name}.bak-{stamp}-{n}")
    return candidate


def install(dest: Path, dry: bool) -> int:
    check_hook_python()
    with tempfile.TemporaryDirectory() as tmp:
        built = Path(tmp) / "payload"
        proc = subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools" / "build.py"), str(built), str(ROOT), "python3"],
            cwd=ROOT, check=False, timeout=TIMEOUT, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print(proc.stdout + proc.stderr, file=sys.stderr)
            return 1

        claude, codex, gemini = dest / ".claude", dest / ".codex", dest / ".gemini" / "config"
        settings_path = claude / "settings.json"
        existing = load_settings(settings_path)  # first: a bad settings.json stops everything

        copies: list[tuple[Path, Path]] = []
        wipes: list[Path] = []
        copies.append((built / "claude" / "CLAUDE.md", claude / "CLAUDE.md"))
        for rel, replace in CLAUDE_DIRS:
            copies += plan_tree(built / "claude" / rel, claude / rel)
            if replace:
                wipes.append(claude / rel)
        for rel in ("agents", "prompts", "skills"):
            copies += plan_tree(built / "codex" / rel, codex / rel)
        copies += [(built / "codex" / "AGENTS.md", codex / "AGENTS.md"), (built / "codex" / "agents.toml", codex / "agents.toml")]
        copies += plan_tree(built / "agy" / "agents", gemini / "agents")
        copies.append((built / "agy" / "AGENTS.md", gemini / "AGENTS.md"))

        manifest_path = claude / "br" / "manifest.json"
        new_rel = sorted({dst.relative_to(dest).as_posix() for _, dst in copies})
        old_rel = read_manifest(manifest_path, dest)
        stale = [dest / rel for rel in old_rel if rel not in set(new_rel)]
        stale = [p for p in stale if os.path.lexists(p)]
        user_files = [claude / "CLAUDE.md", codex / "AGENTS.md", gemini / "AGENTS.md"]
        backups = []
        for path in user_files:
            if path.is_file() and not path.is_symlink() and path.relative_to(dest).as_posix() not in old_rel:
                new = next(src for src, dst in copies if dst == path)
                if path.read_bytes() != new.read_bytes():
                    backups.append(path)

        # The hook commands are the ones build.py wrote; only the build path becomes the install path.
        built_hooks = json.loads((built / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        text_hooks = json.dumps(built_hooks, ensure_ascii=False).replace(
            json.dumps(f"{built}/claude")[1:-1], json.dumps(str(claude))[1:-1],
        )
        fragment = json.loads((built / "settings.fragment.json").read_text(encoding="utf-8"))
        text = json.dumps(
            merged_settings(existing, fragment, json.loads(text_hooks)), indent=2, ensure_ascii=False,
        ) + "\n"

        # Preflight: every target is checked before anything is deleted.
        problems = [m for m in (wipe_blocker(w) for w in wipes) if m]
        for _, dst in copies:
            if not any(w in dst.parents for w in wipes):
                m = blocker(dst)
                if m:
                    problems.append(m)
        for p in [*stale, manifest_path, settings_path]:
            if p in stale and not writable_dir(p.parent):
                problems.append(f"cannot remove {p}: {p.parent} is not writable")
            elif p not in stale:
                m = blocker(p)
                if m:
                    problems.append(m)
        if backups and not all(writable_dir(b.parent) for b in backups):
            problems.append("cannot back up an existing file: its directory is not writable")
        if problems:
            print("install stopped, nothing was changed:\n" + "\n".join(problems), file=sys.stderr)
            return 1

        stamp = time.strftime("%Y%m%d-%H%M%S")
        if dry:
            for b in backups:
                print(f"back up {b} as {backup_name(b, stamp).name}")
            for s in stale:
                print(f"remove {s} (installed earlier, not in the payload)")
            for w in wipes:
                print(f"replace directory {w}")
            for _, dst in copies:
                print(f"write {dst}")
            print(f"write {manifest_path}")
            print(f"merge {settings_path}")
            return 0

        for b in backups:
            shutil.copy2(b, backup_name(b, stamp))
        for s in stale:
            remove_path(s)
        for w in wipes:
            if os.path.lexists(w):
                remove_path(w)
        for src, dst in copies:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if os.path.lexists(dst):
                dst.unlink()
            shutil.copyfile(src, dst)
        write_atomic(manifest_path, json.dumps({"version": 1, "files": new_rel}, indent=2) + "\n")
        write_atomic(settings_path, text)
        print(f"installed {len(copies)} files into {dest} (.claude, .codex, .gemini/config), merged {settings_path}")
    return 0


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.lexists(tmp_name):
            os.unlink(tmp_name)
        raise


def main() -> int:
    ap = argparse.ArgumentParser(description="Install br into a home directory.")
    ap.add_argument("--dest", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    try:
        if args.check:
            return check()
        dest = (args.dest if args.dest is not None else Path.home()).absolute()
        return install(dest, args.dry_run)
    except InstallError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired as exc:
        print(f"timed out after {exc.timeout}s: {' '.join(map(str, exc.cmd))}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"install failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
