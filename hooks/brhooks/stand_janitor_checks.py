"""Bash gate of stand-operator (AC16) and janitor (AC17): the reader gate plus a few extra commands.

Both agents may run everything a reader may run (bash_checks reader gate). On top of that:
- stand-operator: `docker compose -p NAME [-f FILE] up -d|up --wait|restart SVC|down`, and `nix run .#TARGET`
  for the stand targets named in .plan/PLAN.md; every compose command needs `-p`.
- janitor: `rm FILE...` of explicit untracked project files, `docker rm|container rm|volume rm NAME...`,
  `docker compose -p NAME down`, `docker volume inspect NAME...`, `git ls-files`, and read-only listing of paths
  inside the project: `ls`, `find` (no -exec/-delete/-fprint family), `stat`, `readlink`, `du`.
"""
from __future__ import annotations

import os
import posixpath
import re
import subprocess
from pathlib import Path

from .bash_checks import (
    KEYWORDS, MAX_DEPTH, NIX_DEPTH_REASON, READER_BOOL_FLAGS, READER_VALUE_FLAGS, SHELLS, NestingError,
    _reader_words, _resolve, _scan_redirections, _shell_script, _split_commands, _strip_redirections, split_words,
    strip_env_and_wrappers,
)
from .common import Event

STAND_TARGET = re.compile(r"nix\s+run\s+\.#([\w.-]+)")
STAND_LINE = re.compile(r"^\s*[-*]\s*\*\*Stand:\*\*(.*)$", re.MULTILINE)
HOST_FLAGS = {"-H", "--host", "--context", "-c"}
PATH_FLAGS = {"-f", "--file", "--project-directory", "--env-file"}
DOCKER_ENV = re.compile(r"(?:^|[\s;&|(])DOCKER_(?:HOST|CONTEXT)=")
LISTING = {"ls", "find", "stat", "readlink", "du"}
FIND_REFUSED = {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls", "-files0-from"}
UNSAFE_NAME = re.compile(r"[$`*?\[\]{}~\\<>|;&()'\"]")


def _stand_targets(root: Path) -> set[str]:
    try:
        text = (root / ".plan" / "PLAN.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    lines = STAND_LINE.findall(text)
    names = set(STAND_TARGET.findall("\n".join(lines) if lines else text))   # no Stand line at all: the whole plan
    bases = {n.removesuffix("-down") for n in names}
    return bases | {n + "-down" for n in bases}


def _skip_global_flags(args: list[str], seen: list[tuple[str, str]] | None = None) -> int | None:
    """Index of the first positional word; global flags are skipped. None if a flag is unknown (fail closed).
    Every skipped value flag is appended to `seen` as (flag, value)."""
    i = 0
    while i < len(args) and args[i].startswith("-") and args[i] != "-":
        flag, eq, value = args[i].partition("=")
        if flag in {"-p", "--project-name"} or flag in READER_VALUE_FLAGS:
            if seen is not None:
                seen.append((flag, value if eq else (args[i + 1] if i + 1 < len(args) else "")))
            i += 1 if eq else 2
        elif flag in READER_BOOL_FLAGS:
            i += 1
        else:
            return None
    return i if i < len(args) else None


def _names(args: list[str], flags: set[str]) -> list[str] | None:
    """Explicit names after the allowed flags; None if there is another flag, a pattern, a variable or no name."""
    names = [a for a in args if a not in flags]
    if not names or any(a.startswith("-") or UNSAFE_NAME.search(a) for a in names):
        return None
    return names


class _Gate:
    def __init__(self, ev: Event, cmd: str) -> None:
        self.agent = ev.agent or ""
        self.janitor = self.agent == "janitor"
        self.root = ev.project_root
        self.dynamic = re.search(r"[$`]", cmd) is not None     # a name or path may come from a variable or substitution
        self.cwd = str(ev.cwd)
        self.targets = set() if self.janitor else _stand_targets(self.root)

    def deny(self, shown: str, why: str) -> str:
        return f"`{self.agent}`: `{shown[:200]}` is refused. {why}"

    # -- walk -------------------------------------------------------------------------------------------
    def reason(self, cmd: str, depth: int = 0) -> str | None:
        if depth > MAX_DEPTH:
            return NIX_DEPTH_REASON
        try:
            commands = _split_commands(cmd.replace("\\\n", " "))
        except NestingError:
            return NIX_DEPTH_REASON
        for command in commands:
            raw = split_words(_scan_redirections(command.text)[1], comments=False)
            lead = next((a for a in raw if not re.fullmatch(r"\w+=.*", a) and a not in KEYWORDS), "")
            if Path(lead).name in {"sudo", "doas"}:
                return self.deny(" ".join(raw[:4]), "It runs with elevated rights.")
            reason = self.words(raw, depth)
            if reason:
                return reason
        return None

    def words(self, raw: list[str], depth: int) -> str | None:
        if any(DOCKER_ENV.search(" " + w) for w in raw):
            return self.deny(" ".join(raw[:6]), "The docker host and context are fixed; do not set DOCKER_HOST or DOCKER_CONTEXT.")
        outer = _strip_redirections(strip_env_and_wrappers(raw))
        if (self.targets and len(outer) == 3 and Path(outer[0]).name == "nix" and outer[1] == "run"
                and (m := re.fullmatch(r"\.#([\w.-]+)", outer[2])) and m.group(1) in self.targets):
            return None                                         # a stand target named in the plan
        final = _strip_redirections(_resolve(raw)[0])
        if not final:
            return None
        name = Path(final[0]).name
        args = final[1:]
        shown = " ".join(final)
        if name in SHELLS:
            script = _shell_script(final)
            if script is not None:
                return self.reason(script, depth + 1)
        elif name == "eval":
            return self.reason(" ".join(args), depth + 1)
        elif name in {"cd", "pushd", "popd"}:
            return self.deny(shown, "`cd` is not available here; use project-relative paths from the project root.")
        elif name in {"docker", "docker-compose"}:
            special = self.docker(name, args, shown)
            if special is not None:
                return special or None
        elif name == "rm" and self.janitor:
            return self.rm(args, shown)
        elif name in LISTING and self.janitor:
            return self.listing(name, args, shown)
        elif name == "git":
            if self.janitor and self.git_allowed(args):
                return None
            return self.deny(shown, "Only the janitor runs git, and only `git ls-files` and `git status --porcelain` "
                                    "without global options.")
        return _reader_words(final, self.agent, depth)

    def inside(self, value: str) -> bool:
        if not value or value.startswith("~") or re.search(r"[$`]", value):
            return False
        full = posixpath.normpath(posixpath.join(self.cwd, value))
        root = posixpath.normpath(str(self.root))
        return full == root or full.startswith(root + "/")

    def check_flags(self, seen: list[tuple[str, str]], shown: str) -> str | None:
        for flag, value in seen:
            if flag in HOST_FLAGS:
                return self.deny(shown, "The docker host and context are fixed; `-H`, `--host` and `--context` are refused.")
            if flag in PATH_FLAGS and not self.inside(value):
                return self.deny(shown, f"`{flag} {value}` points outside the project; compose files, the project "
                                        "directory and env files must be project paths.")
        return None

    # -- docker -----------------------------------------------------------------------------------------
    def docker(self, name: str, args: list[str], shown: str) -> str | None:
        """None = not special (the reader gate decides), "" = allowed, text = refused."""
        seen: list[tuple[str, str]] = []
        if name == "docker-compose":
            sub, rest = "compose", args
        else:
            i = _skip_global_flags(args, seen)
            bad = self.check_flags(seen, shown)
            if bad or i is None:
                return bad
            sub, rest = args[i], args[i + 1:]
        if sub == "compose":
            seen = []
            i = _skip_global_flags(rest, seen)
            bad = self.check_flags(seen, shown)
            if bad or i is None:
                return bad
            project = [v for f, v in seen if f in {"-p", "--project-name"}]
            action, tail = rest[i], rest[i + 1:]
            if action in {"ps", "logs"}:
                return None if project and project[-1] else self.deny(shown, "Every compose command needs `-p <name>`.")
            if name == "docker-compose" or action not in {"up", "restart", "down"}:
                return None
            if self.janitor and action != "down":
                return None
            if not (project and project[-1]):
                return self.deny(shown, "Every compose command needs `-p <name>`.")
            if action == "down":
                if all(a == "--remove-orphans" for a in tail):
                    return ""
                return self.deny(shown, "`down` takes no volumes or image flags; volumes are removed by name.")
            if action == "up":
                ok = bool(tail) and all(a in {"-d", "--detach", "--wait"} for a in tail)
                return "" if ok else self.deny(shown, "Only `up -d` and `up --wait` are allowed.")
            ok = bool(tail) and not any(a.startswith("-") or UNSAFE_NAME.search(a) for a in tail)
            return "" if ok else self.deny(shown, "`restart` takes service names only.")
        if self.janitor and sub == "volume" and rest[:1] == ["inspect"]:
            if self.dynamic or _names(rest[1:], set()) is None:
                return self.deny(shown, "Name every volume explicitly: no patterns, variables, substitutions or flags.")
            return ""
        if self.janitor and sub in {"rm", "container", "volume", "network"}:
            if sub == "network" and not (rest and rest[0] == "rm"):
                return None
            if sub != "rm":
                if not rest or rest[0] != "rm":
                    return None
                rest = rest[1:]
            if self.dynamic or _names(rest, {"-f", "--force"}) is None:
                return self.deny(shown, "Name every container or volume explicitly: no patterns, variables, "
                                        "substitutions or other flags.")
            return ""
        return None

    # -- listing ------------------------------------------------------------------------------------------
    def listing(self, name: str, args: list[str], shown: str) -> str | None:
        if self.dynamic or any(a.startswith("~") for a in args):
            return self.deny(shown, "Paths must be explicit project-relative paths: no variables, substitutions or `~`.")
        if name == "find":
            start = 0  # leading options: -H -L -P -O<level> -D<opts>, and -D with its value in the next word
            while start < len(args) and (args[start] in {"-H", "-L", "-P", "-D"} or args[start].startswith(("-O", "-D"))):
                start += 2 if args[start] == "-D" else 1
            end = next((i for i, a in enumerate(args) if i >= start and a.startswith(("-", "(", "!"))), len(args))
            paths, expr = args[start:end], args[end:]
            bad = next((a for a in expr if a in FIND_REFUSED or a.startswith("-files0-from=")), None)
            if bad:
                return self.deny(shown, f"`find {bad}` runs commands, deletes or writes files; `find` only lists.")
        else:
            if any(a.startswith("--files0-from") for a in args):
                return self.deny(shown, "`du --files0-from` reads paths from a file; pass explicit project paths.")
            paths = [a for a in args if not a.startswith("-")]
        for path in paths or ["."]:
            if not self.inside(path):
                return self.deny(shown, f"`{path}` is outside the project; list project-relative paths from the project root.")
        return None

    # -- git, rm ------------------------------------------------------------------------------------------
    @staticmethod
    def git_allowed(args: list[str]) -> bool:
        """`git ls-files ...` and `git status` with plain flags; no global option (-c, --config-env, --exec-path, -C, ...)."""
        if not args or args[0].startswith("-"):
            return False
        if args[0] == "ls-files":
            return not any(a.startswith(("--output", "--exclude-from", "--exclude-standard=")) for a in args[1:])
        if args[0] == "status":
            return all(a in {"--porcelain", "--porcelain=v1", "--porcelain=v2", "--short", "-s", "-b", "--branch", "-z"}
                       or not a.startswith("-") for a in args[1:])
        return False

    def tracked(self, rel: str) -> bool:
        """Fails closed: only git's own "did not match" answer (exit 1) means untracked."""
        try:
            out = subprocess.run(["git", "ls-files", "--error-unmatch", "--", rel], cwd=self.root,
                                 capture_output=True, text=True, timeout=10, env={**os.environ, "LC_ALL": "C"})
        except (OSError, subprocess.SubprocessError):
            return True
        return not (out.returncode == 1 and "did not match" in out.stderr)

    def rm(self, args: list[str], shown: str) -> str | None:
        files = [a for a in args if a != "-f"]
        if not files or self.dynamic or any(a.startswith("-") or UNSAFE_NAME.search(a) for a in files):
            return self.deny(shown, "`rm` takes explicit file paths of untracked files, optionally with `-f`: "
                                    "no recursive flag, patterns, variables or substitutions.")
        root = posixpath.normpath(str(self.root))
        for f in files:
            full = posixpath.normpath(posixpath.join(self.cwd, f))
            if not full.startswith(root + "/"):
                return self.deny(shown, f"`{f}` is outside the project; only untracked project files may be removed.")
            rel = posixpath.relpath(full, root)
            if rel.split("/")[0] in {".git", ".plan"}:
                return self.deny(shown, f"`{rel}` is protected.")
            if self.tracked(rel):
                return self.deny(shown, f"`{rel}` is tracked by git; only untracked files may be removed.")
        return None


def _gate(ev: Event, cmd: str | None, agent: str) -> str | None:
    if ev.agent != agent:
        return None
    text = cmd if cmd is not None else ev.tool_input.get("command", "") or ""
    return _Gate(ev, text).reason(text)


def check_stand_operator(ev: Event, cmd: str | None = None) -> str | None:
    return _gate(ev, cmd, "stand-operator")


def check_janitor(ev: Event, cmd: str | None = None) -> str | None:
    return _gate(ev, cmd, "janitor")
