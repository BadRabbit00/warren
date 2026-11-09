"""Bash gate of stand-operator (AC16) and janitor (AC17): the reader gate plus a few extra commands.

Both agents may run everything a reader may run (bash_checks reader gate). On top of that:
- stand-operator: `docker compose -p NAME [-f FILE] up -d|up --wait|restart SVC|down`, and `nix run .#TARGET`
  for the stand targets named in .plan/PLAN.md; every compose command needs `-p`.
- janitor: `rm FILE...` of explicit untracked project files, `docker rm|container rm|volume rm NAME...`,
  `docker compose -p NAME down`, `git ls-files`.
"""
from __future__ import annotations

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
UNSAFE_NAME = re.compile(r"[$`*?\[\]{}~\\<>|;&()'\"]")


def _stand_targets(root: Path) -> set[str]:
    try:
        text = (root / ".plan" / "PLAN.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    names = set(STAND_TARGET.findall(text))
    return names | {n + "-down" for n in names}


def _skip_global_flags(args: list[str], on_project: list[str] | None = None) -> int | None:
    """Index of the first positional word; global flags are skipped. None if a flag is unknown (fail closed).
    `-p NAME` / `--project-name NAME` values are appended to `on_project`."""
    i = 0
    while i < len(args) and args[i].startswith("-") and args[i] != "-":
        flag, eq, value = args[i].partition("=")
        if flag in {"-p", "--project-name"} and on_project is not None:
            on_project.append(value if eq else (args[i + 1] if i + 1 < len(args) else ""))
            i += 1 if eq else 2
        elif flag in READER_VALUE_FLAGS:
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
        self.cwd: str | None = str(ev.cwd)
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
        elif name == "cd":
            self.track_cd(args[0] if args else "")
            return None
        elif name in {"docker", "docker-compose"}:
            special = self.docker(name, args, shown)
            if special is not None:
                return special or None
        elif name == "rm" and self.janitor:
            return self.rm(args, shown)
        elif name == "git" and self.janitor and self.git_ls_files(args):
            return None
        return _reader_words(final, self.agent, depth)

    def track_cd(self, arg: str) -> None:
        if not arg or arg == "-" or arg.startswith(("~", "$")) or self.cwd is None:
            self.cwd = None
        else:
            self.cwd = posixpath.normpath(posixpath.join(self.cwd, arg))

    # -- docker -----------------------------------------------------------------------------------------
    def docker(self, name: str, args: list[str], shown: str) -> str | None:
        """None = not special (the reader gate decides), "" = allowed, text = refused."""
        project: list[str] = []
        if name == "docker-compose":
            sub, rest = "compose", args
        else:
            i = _skip_global_flags(args)
            if i is None:
                return None
            sub, rest = args[i], args[i + 1:]
        if sub == "compose":
            i = _skip_global_flags(rest, project)
            if i is None:
                return None
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
        if self.janitor and sub in {"rm", "container", "volume"}:
            if sub != "rm":
                if not rest or rest[0] != "rm":
                    return None
                rest = rest[1:]
            if self.dynamic or _names(rest, {"-f", "--force"}) is None:
                return self.deny(shown, "Name every container or volume explicitly: no patterns, variables, "
                                        "substitutions or other flags.")
            return ""
        return None

    # -- git, rm ------------------------------------------------------------------------------------------
    @staticmethod
    def git_ls_files(args: list[str]) -> bool:
        i = 0
        while i < len(args) and args[i].startswith("-"):
            i += 2 if args[i] in {"-C", "-c"} else 1
        return i < len(args) and args[i] == "ls-files"

    def tracked(self, rel: str) -> bool:
        out = subprocess.run(["git", "ls-files", "--error-unmatch", "--", rel], cwd=self.root,
                             capture_output=True, text=True, timeout=10)
        return out.returncode == 0

    def rm(self, args: list[str], shown: str) -> str | None:
        files = [a for a in args if a != "-f"]
        if not files or self.dynamic or any(a.startswith("-") or UNSAFE_NAME.search(a) for a in files):
            return self.deny(shown, "`rm` takes explicit file paths of untracked files, optionally with `-f`: "
                                    "no recursive flag, patterns, variables or substitutions.")
        if self.cwd is None:
            return self.deny(shown, "The directory after `cd` is not known; use project-relative paths.")
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
