"""Checks for Bash tool calls. Each check returns a deny reason or None.

These are heuristics over the command text. They stop the common mistakes, not a determined
adversary; the orchestrator's sha256 check of test files and code review are the backstops.
"""
from __future__ import annotations

import os
import posixpath
import re
import shlex
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .common import NO_TEST_WRITE, PROTECTED_BRANCHES, Event, git_branch, is_test_path, rel
from .write_checks import _explicit_write, _is_temp, check_write

# Split a command line into simple commands on ; && || | & and newlines (good enough for policy checks).
SEPARATOR = r"&&|\|\||;|(?<!>)\||(?<![>&])&(?![>&])|\n"      # `>|` is a redirection, not a pipe
SPLIT = re.compile(rf"\s*(?:{SEPARATOR})\s*")
WRAPPERS = {"sudo", "doas", "command", "exec", "time", "nohup", "nice", "env",
            "timeout", "setsid", "stdbuf", "ionice", "chrt", "flock"}
# Shell keywords that may precede a command in a segment (`then python3 x`, `{ python3 x`, `! python3 x`).
KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "do", "while", "until"}
# Wrapper options that take a value as the next word.
WRAPPER_VALUE_FLAGS = {
    "sudo": {"-u", "-g", "-h", "-p", "-C"}, "doas": {"-u", "-C"}, "env": {"-u", "-C", "-S"},
    "nice": {"-n"}, "timeout": {"-k", "-s"}, "time": {"-f", "-o"}, "stdbuf": {"-i", "-o", "-e"},
    "ionice": {"-c", "-n", "-p", "-P", "-u"}, "flock": {"-w", "-E"},
}
WRAPPER_POSITIONAL = {"timeout": 1, "chrt": 1, "flock": 1}   # DURATION / priority / lock file
REDIRECT_WORD = re.compile(r"\d*[<>]&?\S*")
REDIRECT_OPERATOR = re.compile(r"\d*[<>]{1,2}&?")           # `>` `2>` `>>`: the target is the next word


def segments(cmd: str) -> list[str]:
    return [s.strip() for s in SPLIT.split(cmd) if s.strip()]


def split_words(seg: str, comments: bool = True) -> list[str]:
    """Shell-like words. A `#` inside a word (`nixpkgs#x`, `.#dev`) is not a comment; a word that starts
    with `#` is (and everything after it), unless `comments` is off because the caller already cut them."""
    lex = shlex.shlex(seg, posix=True)
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        w = list(lex)
    except ValueError:
        w = seg.split()
    if comments:
        for i, word in enumerate(w):
            if word.startswith("#"):
                return w[:i]
    return w


def _skip_wrapper_options(name: str, w: list[str]) -> list[str]:
    values = WRAPPER_VALUE_FLAGS.get(name, set())
    while w and w[0].startswith("-") and w[0] != "-":
        flag, w = w[0], w[1:]
        if flag == "--":
            break
        if flag in values and w:
            w = (split_words(w[0], comments=False) + w[1:]) if (name, flag) == ("env", "-S") else w[1:]
        elif name == "env" and flag.startswith("-S") and len(flag) > 2:
            w = split_words(flag[2:], comments=False) + w
    for _ in range(WRAPPER_POSITIONAL.get(name, 0)):
        if w:
            w = w[1:]
    return w


def strip_env_and_wrappers(w: list[str]) -> list[str]:
    """Drop what precedes the command word: env assignments, shell keywords, redirections, and
    wrappers that do not change meaning (with their options)."""
    while w:
        a = w[0]
        if re.fullmatch(r"\w+=.*", a) or a in KEYWORDS:
            w = w[1:]
        elif REDIRECT_WORD.fullmatch(a):
            w = w[2:] if REDIRECT_OPERATOR.fullmatch(a) else w[1:]
        elif Path(a).name in WRAPPERS and len(w) > 1:
            if Path(a).name == "command" and w[1] in {"-v", "-V"}:
                return []                     # a lookup, nothing runs
            w = _skip_wrapper_options(Path(a).name, w[1:])
        else:
            break
    return w


def words(seg: str) -> list[str]:
    w = strip_env_and_wrappers(split_words(seg))
    # look inside `nix develop -c …` / `nix shell … -c …`
    if len(w) > 2 and w[0] == "nix" and w[1] in {"develop", "shell"}:
        for flag in ("-c", "--command"):
            if flag in w:
                w = w[w.index(flag) + 1:]
                break
    return w


def expand(cmd: str) -> list[str]:
    """Segments, plus the inner script of `bash -c '…'` / `sh -c` (also behind `nix develop -c`)."""
    out = []
    for seg in segments(cmd):
        out.append(seg)
        w = words(seg)
        if len(w) >= 3 and Path(w[0]).name in {"bash", "sh", "zsh"} and w[1] == "-c":
            out.extend(expand(w[2]))
    return out


# ---------------------------------------------------------------- host installs

HOST_INSTALL = [
    (re.compile(r"^(pip3?|python3?(\.\d+)?\s+-m\s+pip|uv\s+pip)\s+install\b"), "pip install"),
    (re.compile(r"^pipx\s+(install|run)\b"), "pipx"),
    (re.compile(r"^uv\s+(sync|venv|add|tool\s+install)\b"), "uv sync/venv/add"),
    (re.compile(r"^(python3?(\.\d+)?\s+-m\s+venv|virtualenv)\b"), "virtualenv"),
    (re.compile(r"^(npm|pnpm)\s+(i|install|add)\b.*\s(-g|--global)\b"), "global npm/pnpm install"),
    (re.compile(r"^yarn\s+global\b"), "yarn global"),
    (re.compile(r"^go\s+install\b"), "go install"),
    (re.compile(r"^cargo\s+install\b"), "cargo install"),
    (re.compile(r"^rustup\s+(toolchain\s+install|component\s+add|target\s+add)\b"), "rustup"),
    (re.compile(r"^nix-env\s+(-i|--install|-iA)\b"), "nix-env -i"),
    (re.compile(r"^nix\s+profile\s+(install|add)\b"), "nix profile install"),
    (re.compile(r"^(apt|apt-get|dnf|yum|zypper|apk)\s+(install|add)\b"), "system package manager"),
    (re.compile(r"^pacman\s+-S"), "pacman"),
    (re.compile(r"^(brew|snap|flatpak|choco|winget)\s+install\b"), "system package manager"),
    (re.compile(r"^python3?(\.\d+)?\s+-c\b"), "inline python (python -c)"),
    (re.compile(r"^node\s+(-e|--eval|-p)\b"), "inline node (node -e)"),
]
CURL_PIPE_SH = re.compile(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z)?sh\b")


def check_host_install(ev: Event, cmd: str) -> str | None:
    if CURL_PIPE_SH.search(cmd):
        return ("curl | sh installs software on the host. Add the tool to the project devShell "
                "or use `nix shell nixpkgs#<pkg> -c …`.")
    for seg in expand(cmd):
        line = " ".join(words(seg))
        for rx, what in HOST_INSTALL:
            if rx.search(line):
                if what.startswith("inline"):
                    return f"{what} is not allowed: write the script to a file and run it through `nix develop -c`."
                return (f"{what} is not allowed: nothing is installed on the host or into .venv. "
                        "Add the dependency to the project flake/devShell (or pyproject + nixpkgs), "
                        "or run a one-off tool with `nix shell nixpkgs#<pkg> -c <cmd>`.")
    return None


# ---------------------------------------------------------------- Nix only

INTERPRETER = re.compile(
    r"(?:python|pypy|ruby|perl|php|lua|node(?:js)?)[\d.]*[a-z]?|luajit[\d.-]*|ipython[\d.]*|tsx|ts-node"
    r"|Rscript|julia|bun|deno")
# A variable whose name or default value mentions one of these may hold an interpreter.
INTERPRETER_HINT = re.compile(r"python|pypy|node|ruby|perl|php|lua|julia|deno|\bbun\b|interp|^py$|rscript", re.I)
LAUNCHER = {"npx", "bunx", "uvx"}
LAUNCHER_SUBCOMMANDS: dict[str, set[tuple[str, ...]]] = {
    "uv": {("run",), ("tool", "run")}, "pnpm": {("dlx",), ("exec",)}, "poetry": {("run",)},
    "pipenv": {("run",)}, "npm": {("exec",)}, "yarn": {("dlx",)}, "pipx": {("run",)}, "pdm": {("run",)},
    "hatch": {("run",)}, "bundle": {("exec",)}, "conda": {("run",)}, "pyenv": {("exec",)}, "mise": {("exec",)},
}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish", "ash"}
SHELL_VALUE_OPTIONS = {"-o", "+o", "-O", "+O", "--rcfile", "--init-file"}
SHELL_COMMAND_FLAG = re.compile(r"-[A-Za-z]*c[A-Za-z]*")
SHELL_VALUE_CLUSTER = re.compile(r"[-+][A-Za-z]*[oO]")        # `-euo pipefail`: the last letter takes the value
XARGS_VALUE_OPTIONS = {"-n", "-I", "-L", "-P", "-s", "-d", "-E", "-a", "-l"}
NIX_VALUE_OPTIONS = {"--extra-experimental-features": 1, "--experimental-features": 1, "--option": 2,
                     "--max-jobs": 1, "-j": 1, "--cores": 1, "--store": 1, "--eval-store": 1,
                     "--log-format": 1, "--substituters": 1, "--extra-substituters": 1, "--builders": 1,
                     "--override-input": 2, "--update-input": 1, "--inputs-from": 1, "--profile": 1,
                     "--arg": 2, "--argstr": 2}
MAX_DEPTH = 8
MAX_COMMAND_LENGTH = 200_000
DECLARATIONS = {"export", "declare", "local", "readonly", "typeset"}
HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)(\w+)\2")
SEPARATOR_TOKEN = re.compile(SEPARATOR)
SUBST = "$__SUBST__"        # stands for a `$(…)` / backtick that is the command word of a segment


class NestingError(Exception):
    """The command nests substitutions or `sh -c` deeper than MAX_DEPTH."""


@dataclass
class Command:
    text: str
    heredocs: list[str] = field(default_factory=list)   # bodies of the heredocs attached to this command
    piped: bool = False                                  # fed by the previous command through a pipe


@dataclass
class Scan:
    """What earlier commands of the same command line did that later ones depend on."""
    assigned: dict[str, str] = field(default_factory=dict)   # shell variables set so far
    cwd: str | None = None                                   # directory after `cd`, as written; None if unknown
    substitution_ok: bool = False                            # inside `eval`: `$(…)` as a command is expected

    @property
    def in_skill_dir(self) -> bool:
        return self.cwd is not None and _is_skill_path(self.cwd + "/")

    def cd(self, arg: str) -> None:
        """Track `cd ARG`: an absolute path sets the directory, a relative one extends a known one."""
        if not arg or arg == "-":
            self.cwd = None
        elif arg.startswith(("/", "~", "$")):
            self.cwd = arg
        elif self.cwd is not None:
            self.cwd = posixpath.normpath(f"{self.cwd}/{arg}")


def _matching_paren(cmd: str, start: int) -> int:
    """Index of the `)` that closes a `(` opened just before `start` (end of string if unbalanced)."""
    depth = 1
    for i in range(start, len(cmd)):
        depth += {"(": 1, ")": -1}.get(cmd[i], 0)
        if depth == 0:
            return i
    return len(cmd)


def _read_heredoc_bodies(cmd: str, i: int, pending: list[tuple[str, bool, int]]) -> tuple[int, dict[int, list[str]]]:
    """`i` is just after a newline: read the body of every pending heredoc. Returns the index after the
    bodies and the bodies by the start index of the command that owns the heredoc."""
    bodies: dict[int, list[str]] = {}
    for tag, dash, owner in pending:
        lines = []
        while i < len(cmd):
            end = cmd.find("\n", i)
            end = len(cmd) if end < 0 else end
            line = cmd[i:end]
            i = min(end + 1, len(cmd))
            if (line.lstrip("\t") if dash else line) == tag:
                break
            lines.append(line)
        bodies.setdefault(owner, []).append("\n".join(lines))
    return i, bodies


def _split_commands(cmd: str, depth: int = 0) -> list[Command]:
    """Simple commands of a command line. Unlike segments() it respects quotes, drops comments, keeps
    heredoc bodies apart from the commands, and treats `( ) $( ) <( ) >( )` and backticks as separators;
    `$(…)` and backticks inside double quotes are extracted as commands of their own."""
    if depth > MAX_DEPTH:
        raise NestingError
    out: list[Command] = []
    owners: dict[int, Command] = {}
    start = i = 0
    quote = ""
    pending: list[tuple[str, bool, int]] = []
    piped_next = False

    def flush(end: int) -> None:
        nonlocal piped_next
        if cmd[start:end].strip():
            owners[start] = Command(cmd[start:end].strip(), piped=piped_next)
            out.append(owners[start])
            piped_next = False

    while i < len(cmd):
        c = cmd[i]
        if c == "\\" and quote != "'":
            i += 2
        elif quote == "'":
            quote = "" if c == "'" else quote
            i += 1
        elif quote == '"':
            if c == '"':
                quote, i = "", i + 1
            elif cmd.startswith("$(", i):
                end = _matching_paren(cmd, i + 2)
                out.extend(_split_commands(cmd[i + 2:end], depth + 1))
                i = end + 1
            elif c == "`":
                end = cmd.find("`", i + 1)
                end = len(cmd) if end < 0 else end
                out.extend(_split_commands(cmd[i + 1:end], depth + 1))
                i = end + 1
            else:
                i += 1
        elif c in "'\"":
            quote, i = c, i + 1
        elif c == "#" and (i == 0 or cmd[i - 1] in " \t\n;&|()"):
            flush(i)
            end = cmd.find("\n", i)
            start = i = len(cmd) if end < 0 else end
        elif cmd.startswith("<<", i) and not cmd.startswith("<<<", i) and HEREDOC.match(cmd, i):
            m = HEREDOC.match(cmd, i)
            assert m is not None
            pending.append((m.group(3), bool(m.group(1)), start))
            i = m.end()
        elif c == "`" or (c == "(" and i > 0 and cmd[i - 1] == "$"):
            dollar = c == "("
            head_end = i - 1 if dollar else i
            if not cmd[start:head_end].strip():              # the substitution is the command word
                close = _matching_paren(cmd, i + 1) if dollar else cmd.find("`", i + 1)
                close = len(cmd) if close < 0 else close
                out.extend(_split_commands(cmd[i + 1:close], depth + 1))
                cmd = cmd[:head_end] + SUBST + cmd[close + 1:]
                i = head_end + len(SUBST)
            else:
                flush(head_end)
                start = i = i + 1
                piped_next = False
        elif c in "()":
            flush(i)
            start = i = i + 1
            piped_next = False
        elif c in "&|;\n" and (m := SEPARATOR_TOKEN.match(cmd, i)):
            flush(i)
            piped_next = m.group() == "|"
            i = m.end()
            if c == "\n" and pending:
                i, bodies = _read_heredoc_bodies(cmd, i, pending)
                for owner, texts in bodies.items():
                    if owner in owners:
                        owners[owner].heredocs.extend(texts)
                pending = []
            start = i
        else:
            i += 1
    flush(len(cmd))
    return out


@lru_cache(maxsize=4)
def _skill_root(home: str) -> re.Pattern[str]:
    homes = "|".join([re.escape(home.rstrip("/"))] * bool(home.strip("/")) + [r"~[^/]*", r"/home/[^/]+", r"/root",
                                                                              r"\$HOME", r"\$\{HOME\}"])
    agent = r"(?:\.claude|\.codex|\.gemini/config)"
    return re.compile(
        rf"(?:{homes})/{agent}/skills(?:/|$)"
        rf"|/nix/store/[^/]+/(?:[^/]+/)*{agent}?/?skills(?:/|$)"
        r"|/nix/store/[^/]+-skills(?:/|$)")


def _is_skill_path(arg: str) -> bool:
    """True for a path inside an agent skills directory (also `--opt=path`). Packaged wrappers are not."""
    home = os.environ.get("HOME", "")
    for cand in (arg, arg.partition("=")[2]):
        if re.match(r"\$\{?CLAUDE_SKILL_DIR\}?(?:/|$)", cand):
            return True
        if home:
            cand = re.sub(r"^(?:~|\$HOME|\$\{HOME\})(?=/|$)", lambda _: home, cand)
        if not cand:
            continue
        cand = posixpath.normpath(cand)
        if not re.match(r"/nix/store/[^/]+/bin/", cand) and _skill_root(home).match(cand):
            return True
    return False


def _is_interpreter(w: list[str]) -> bool:
    name = Path(w[0]).name
    if INTERPRETER.fullmatch(name) or name in LAUNCHER:
        return True
    subs = LAUNCHER_SUBCOMMANDS.get(name)
    if not subs:
        return False
    i = 1
    while i < len(w) and w[i].startswith("-"):    # `uv --directory . run x`: skip the option and its value
        i += 1
        if "=" not in w[i - 1] and i < len(w) and not any(w[i] == s[0] for s in subs):
            i += 1
    return any(tuple(w[i:i + len(s)]) == s for s in subs)


def _unwrap_nix(w: list[str]) -> tuple[list[str], bool] | None:
    """For `nix develop|shell … -c CMD`, `nix run X -- ARGS`, `nix-shell --run CMD`: the command that
    runs inside Nix and True. None if `w` is not such a call."""
    name = Path(w[0]).name
    if name == "nix-shell":
        for flag in ("--run", "--command"):
            if flag in w[:-1]:
                return ["sh", "-c", w[w.index(flag) + 1]], True
        return [], True
    if name != "nix":
        return None
    i = 1
    while i < len(w) and w[i].startswith("-"):
        i += 1 + NIX_VALUE_OPTIONS.get(w[i], 0)
    sub = w[i] if i < len(w) else ""
    rest = w[i + 1:]
    if sub in {"develop", "shell"}:
        flags = [j for j, a in enumerate(rest) if a in {"-c", "--command"}]
        return (rest[flags[0] + 1:] if flags else []), True
    if sub == "run":
        installable = next((a for a in rest if not a.startswith("-")), "")
        program = installable.partition("#")[2]
        args = rest[rest.index("--") + 1:] if "--" in rest else []
        return ([program] if program else []) + args, True
    return None


def _resolve(w: list[str]) -> tuple[list[str], bool]:
    """The command that finally runs (wrappers, `nix develop -c`, `busybox` peeled off) and whether Nix runs it."""
    in_nix = False
    for _ in range(MAX_DEPTH):
        w = strip_env_and_wrappers(w)
        inner = _unwrap_nix(w) if w else None
        if inner is not None:
            w, in_nix = inner[0], True
        elif w and Path(w[0]).name == "busybox":
            w = w[1:]
        else:
            break
    return w, in_nix


def _find_exec_commands(w: list[str]) -> list[list[str]]:
    out = []
    for i, a in enumerate(w):
        if a in {"-exec", "-execdir", "-ok", "-okdir"}:
            cmd: list[str] = []
            for b in w[i + 1:]:
                if b in {";", "+", "{}"}:
                    break
                cmd.append(b)
            out.append(cmd)
    return out


def _shell_script(w: list[str]) -> str | None:
    """The script of `bash -c SCRIPT` (also `-lc`, `-l -c`, `--norc -c`, `-o pipefail -c`, `-euo pipefail -c`)."""
    i = 1
    while i < len(w) and w[i] != "--" and w[i][0] in "-+":
        if SHELL_COMMAND_FLAG.fullmatch(w[i]):
            return w[i + 1] if i + 1 < len(w) else None
        i += 2 if w[i] in SHELL_VALUE_OPTIONS or SHELL_VALUE_CLUSTER.fullmatch(w[i]) else 1
    return None


NIX_SKILL_REASON = ("Skill scripts are not run from the skills directory. Use the skill's Nix wrapper "
                    "(a /nix/store/…/bin/<name> command); SKILL.md of the skill says which one.")
NIX_VARIABLE_REASON = ("The command comes from a variable or substitution that may hold an interpreter, so it "
                       "cannot be checked. Write the command out and run it through the project environment: "
                       "`nix develop -c …`.")
NIX_DEPTH_REASON = "The command is too deeply nested (substitutions, shell -c inside shell -c …) to check. Simplify it."


def _first_argument(args: list[str]) -> str:
    """First word that is neither an option nor part of a redirection."""
    i = 0
    while i < len(args):
        a = args[i]
        if REDIRECT_WORD.fullmatch(a):
            i += 2 if REDIRECT_OPERATOR.fullmatch(a) else 1
        elif a.startswith("-") and a != "-":
            i += 1
        else:
            return a
    return ""


def _relative(a: str) -> bool:
    return not a.startswith(("-", "/", "~", "$"))


def _runs_from_cwd(w: list[str]) -> bool:
    """After `cd <skills dir>`: a relative command (`./run`), `source x`, or a script for an interpreter/shell."""
    head = w[0]
    if "/" in head and _relative(head):
        return True
    if head in {"source", "."}:
        return any(_relative(a) for a in w[1:])
    return (_is_interpreter(w) or Path(head).name in SHELLS) and any(_relative(a) for a in w[1:])


def _reads_stdin_script(w: list[str]) -> bool:
    """A shell or interpreter without a script argument runs what arrives on its stdin."""
    return (Path(w[0]).name in SHELLS or _is_interpreter(w)) and all(a.startswith("-") for a in w[1:])


def _herestrings(w: list[str]) -> list[str]:
    """Texts of `<<< 'text'` / `<<<text` in the words."""
    out = []
    for i, a in enumerate(w):
        if a == "<<<" and i + 1 < len(w):
            out.append(w[i + 1])
        elif a.startswith("<<<") and len(a) > 3:
            out.append(a[3:])
    return out


def _variable_head_reason(head: str, scan: Scan) -> str | None:
    """Deny a command word that is a bare variable or substitution that may hold an interpreter."""
    if head == SUBST or re.fullmatch(r"\$\(.*\)|`.*`", head):
        return None if scan.substitution_ok else NIX_VARIABLE_REASON
    m = re.fullmatch(r"\$(\w+)|\$\{([^}]*)\}", head)       # `$VAR/path` is a path, not a bare variable
    if not m:
        return None
    text = m.group(1) or m.group(2)
    value = scan.assigned.get(re.split(r"\W", text, maxsplit=1)[0])
    if value is not None:
        first = value.split()[0] if value.split() else ""
        if "$" in value or "`" in value or (first and _is_interpreter([first])):
            return NIX_VARIABLE_REASON
    return NIX_VARIABLE_REASON if INTERPRETER_HINT.search(text) else None


def _nix_commands(cmd: str, wrapped: bool, depth: int, cwd: str | None = None, eval_ok: bool = False) -> str | None:
    if depth > MAX_DEPTH:
        return NIX_DEPTH_REASON
    try:
        commands = _split_commands(cmd.replace("\\\n", " "))
    except NestingError:
        return NIX_DEPTH_REASON
    scan = Scan(cwd=cwd, substitution_ok=eval_ok)
    pipeline_has_skill = False
    pipeline_bodies: list[str] = []                            # heredoc bodies feeding the current pipeline
    for command in commands:
        raw = split_words(command.text, comments=False)
        assignments = raw
        while assignments and assignments[0] in DECLARATIONS:  # `export p=python3`
            assignments = assignments[1:]
            while assignments and assignments[0].startswith("-"):
                assignments = assignments[1:]
        for word in assignments:
            m = re.fullmatch(r"(\w+)=(.*)", word)
            if not m:
                break
            scan.assigned[m.group(1)] = m.group(2)
        w = strip_env_and_wrappers(raw)
        final, in_nix = _resolve(w)
        if not command.piped:
            pipeline_has_skill = any(_is_skill_path(a) for a in final[1:])
            pipeline_bodies = list(command.heredocs)
        else:
            if pipeline_has_skill and final and _reads_stdin_script(final):
                return NIX_SKILL_REASON                        # cat skill.sh | bash
            if final and Path(final[0]).name in SHELLS and _reads_stdin_script(final):
                for body in pipeline_bodies:                   # cat <<EOF | bash
                    reason = _nix_commands(body, wrapped or in_nix, depth + 1, scan.cwd)
                    if reason:
                        return reason
            pipeline_bodies += command.heredocs
        if w and Path(w[0]).name in {"cd", "pushd"}:
            scan.cd(_first_argument(w[1:]))
        elif w and Path(w[0]).name == "popd":
            scan.cwd = None
        reason = _nix_words(w, wrapped, depth, scan, command.heredocs)
        if reason:
            return reason
    return None


def _nix_words(w: list[str], wrapped: bool, depth: int, scan: Scan, heredocs: list[str] | None = None) -> str | None:
    w = strip_env_and_wrappers(w)
    if w:
        w = [re.split(r"[<>]", w[0])[0]] + w[1:]      # `python3>out`, `python3</dev/null`
    if not w or not w[0] or w[0] in {"[", "[["}:
        return None
    head = posixpath.normpath(w[0]) if w[0].startswith("/") else w[0]
    name = Path(head).name
    if _is_skill_path(head):
        return NIX_SKILL_REASON
    if scan.in_skill_dir and _runs_from_cwd(w):
        return NIX_SKILL_REASON
    inner = _unwrap_nix(w)
    if inner is not None:
        return _nix_words(inner[0], True, depth + 1, scan, heredocs)
    if name == "busybox":
        return _nix_words(w[1:], wrapped, depth + 1, scan, heredocs)
    if name == "eval":
        return _nix_commands(" ".join(w[1:]), wrapped, depth + 1, scan.cwd, eval_ok=True)
    if name == "xargs":
        i = 1
        while i < len(w) and w[i].startswith("-"):
            i += 2 if w[i] in XARGS_VALUE_OPTIONS else 1
        return _nix_words(w[i:], wrapped, depth + 1, scan)
    if name == "find":
        return next(filter(None, (_nix_words(c, wrapped, depth + 1, scan) for c in _find_exec_commands(w))), None)
    if name in SHELLS:
        script = _shell_script(w)
        if script is not None:
            return _nix_commands(script, wrapped, depth + 1, scan.cwd)
        for body in (heredocs or []) + _herestrings(w):    # `bash <<EOF`, `bash <<< 'cmd'`: a script on stdin
            reason = _nix_commands(body, wrapped, depth + 1, scan.cwd)
            if reason:
                return reason
    if head in {"source", "."}:                            # `source /dev/stdin <<EOF`
        for body in (heredocs or []) + _herestrings(w):
            reason = _nix_commands(body, wrapped, depth + 1, scan.cwd)
            if reason:
                return reason
    if not wrapped:
        reason = _variable_head_reason(head, scan)
        if reason:
            return reason
    interpreter = _is_interpreter(w)
    if (interpreter or name in SHELLS or head in {"source", "."}) and any(_is_skill_path(a) for a in w[1:]):
        return NIX_SKILL_REASON
    if interpreter and not wrapped and not head.startswith("/nix/store/"):
        return (f"Bare `{name}` is not allowed: run it through the project environment, "
                f"`nix develop -c {name} …`, or a one-off `nix shell nixpkgs#<pkg> -c {name} …`.")
    return None


def check_nix_only(ev: Event, cmd: str) -> str | None:
    if len(cmd) > MAX_COMMAND_LENGTH:
        return f"The command is too long ({len(cmd)} characters) to check. Split it into smaller commands."
    try:
        return _nix_commands(cmd, False, 0)
    except RecursionError:
        return NIX_DEPTH_REASON


# ---------------------------------------------------------------- git

# Subcommands that change history or the index of the current branch.
GIT_WRITE = {"commit", "rebase", "reset", "cherry-pick", "revert", "am", "pull", "restore", "rm", "mv",
             "add", "merge", "apply", "notes", "replace", "filter-branch", "filter-repo"}
GIT_GLOBAL_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


def git_call(seg: str, cwd: Path) -> tuple[list[str], Path] | None:
    """(args after global options, effective cwd) or None if the segment is not git."""
    w = words(seg)
    if not w or Path(w[0]).name != "git":
        return None
    i = 1
    while i < len(w) and w[i].startswith("-"):
        if w[i] == "-C" and i + 1 < len(w):
            cwd = Path(w[i + 1]) if Path(w[i + 1]).is_absolute() else cwd / w[i + 1]
        i += 2 if w[i] in GIT_GLOBAL_WITH_ARG else 1
    return (w[i:], cwd) if i < len(w) else None


def _push_reason(rest: list[str], branch: str | None) -> str | None:
    if any(a in {"--all", "--mirror", "--tags"} for a in rest):
        return "`git push --all/--mirror/--tags` touches develop/main and releases. Push your feature branch only."
    targets = [a for a in rest if not a.startswith("-")]
    refspecs = targets[1:]
    if "--delete" in rest or "-d" in rest:
        if any(t.removeprefix("refs/heads/") in PROTECTED_BRANCHES for t in refspecs):
            return "Deleting develop/main on the remote is not allowed."
        return None
    dests = []
    for r in refspecs:
        dst = r.lstrip("+").split(":")[-1].removeprefix("refs/heads/")
        dests.append(branch if dst in {"HEAD", "@", ""} else dst)
    if not refspecs:
        dests = [branch]          # `git push` / `git push origin` pushes the current branch
    if any(d in PROTECTED_BRANCHES for d in dests):
        return ("Pushing develop/main is done by a human. Push your feature branch only "
                "(`git push -u origin feature/<task-id>-<slug>`).")
    return None


def check_git(ev: Event, cmd: str) -> str | None:
    for seg in expand(cmd):
        call = git_call(seg, ev.cwd)
        if not call:
            continue
        args, cwd = call
        sub, rest = args[0], args[1:]
        cache: dict[str, str | None] = {}

        def branch() -> str | None:
            if "b" not in cache:
                cache["b"] = git_branch(cwd)
            return cache["b"]

        if "--no-verify" in rest or (sub == "commit" and "-n" in rest):
            return "--no-verify bypasses the project's git hooks. Fix the failing check instead."
        if sub == "push":
            reason = _push_reason(rest, branch())
            if reason:
                return reason
            continue
        if sub == "clean" and any("x" in a.lstrip("-").lower() for a in rest if a.startswith("-") and not a.startswith("--")):
            return "`git clean -x` deletes ignored files such as .env and local data. Remove specific files instead."
        if sub == "branch" and any(a in {"-D", "-d", "--delete", "-f", "--force", "-m", "-M"} for a in rest) \
                and any(a in PROTECTED_BRANCHES for a in rest):
            return "Deleting, renaming, or force-moving develop/main is not allowed."
        if sub == "update-ref" and any(a.removeprefix("refs/heads/") in PROTECTED_BRANCHES for a in rest):
            return "Moving develop/main refs directly is not allowed."
        if sub not in GIT_WRITE:
            continue
        b = branch()
        if b not in PROTECTED_BRANCHES:
            continue                      # feature branches: free
        if sub == "merge" and b == "develop":
            if "--abort" in rest or "--quit" in rest:
                continue
            sources = [a for a in rest if not a.startswith("-")]
            if sources and all(s.startswith(("feature/", "hotfix/")) for s in sources):
                continue                  # finishing a task: feature → develop is the one allowed write
        if sub == "pull" and "--ff-only" in rest:
            continue                      # updating the local copy without creating commits
        return (f"`git {sub}` on `{b}` is not allowed. Work on `feature/<task-id>-<slug>`. The only write to develop "
                "is `git merge --no-ff feature/…` when the task is done; resolve conflicts by merging develop into "
                "the feature branch first.")
    return None


# ---------------------------------------------------------------- destructive

REBUILDABLE = {"node_modules", "dist", "build", "target", "__pycache__", ".pytest_cache", ".mypy_cache",
               ".ruff_cache", ".next", ".nuxt", "out", "coverage", ".coverage", "htmlcov", ".turbo",
               ".parcel-cache", ".dart_tool", ".gradle", ".svelte-kit"}
RESULT_LINK = re.compile(r"result(-[\w.-]+)?")
TMP_PREFIXES = ("/tmp/", "/var/tmp/")


def _safe_rm_target(t: str) -> bool:
    if t.startswith(TMP_PREFIXES) or "/scratchpad/" in t:
        return ".." not in Path(t).parts
    parts = Path(t.rstrip("/")).parts
    if not parts or ".." in parts or t.startswith(("/", "~", "$")):
        return False
    return any(p in REBUILDABLE for p in parts) or RESULT_LINK.fullmatch(parts[-1]) is not None


SQL_DESTROY = re.compile(r"\b(DROP\s+(TABLE|DATABASE|SCHEMA|COLLECTION|OWNED)|TRUNCATE\b|FLUSHALL|FLUSHDB)|\.drop\(\)|dropDatabase\(\)", re.I)
SQL_CLIENT = re.compile(r"\b(psql|pgcli|mongosh|mongo|mysql|mariadb|sqlite3|clickhouse-client|redis-cli)\b|docker\s+compose\s+exec", re.I)


def check_destructive(ev: Event, cmd: str) -> str | None:
    # whole command: SQL may come through a heredoc on the next lines
    if (SQL_CLIENT.search(cmd) and SQL_DESTROY.search(cmd)) or re.search(r"(^|[\s;&|])dropdb\s", cmd):
        return "DROP/TRUNCATE/FLUSH needs the user's explicit «да» and must never target a shared or production database."
    for seg in expand(cmd):
        w = words(seg)
        if not w:
            continue
        line = " ".join(w)
        if w[0] == "rm":
            flags = [a for a in w[1:] if a.startswith("-")]
            targets = [a for a in w[1:] if not a.startswith("-")]
            if any(Path(a).name == ".git" or (Path(a).name == ".env" or Path(a).name.startswith(".env."))
                   and not re.search(r"\.(example|sample|template)\b", a) for a in targets):
                return "Deleting .env or .git needs the user's explicit «да»."
            if any(re.fullmatch(r"-[a-zA-Z]*[rR][a-zA-Z]*|--recursive", a) for a in flags):
                unsafe = [t for t in targets if not _safe_rm_target(t)]
                if unsafe or not targets:
                    return (f"Recursive delete of {unsafe or 'unknown targets'} needs the user's explicit «да» "
                            "with a named list. Temp dirs and rebuildable caches (node_modules, dist, target, result…) are fine.")
        if w[0] == "find" and ("-delete" in w or ("-exec" in w and "rm" in w)):
            return "Bulk delete with find needs the user's explicit «да» with a named list."
        # the janitor gate already accepted `docker volume rm NAME...` with explicit names
        if w[0] == "docker":                       # `docker --context x volume rm …`: look past the global flags
            i = 1
            while i < len(w) and w[i].startswith("-"):
                i += 2 if w[i] in READER_VALUE_FLAGS and "=" not in w[i] else 1
            if not any(a.partition("=")[0] in {"-H", "--host", "--context", "-c"} for a in w[1:i]):
                line = " ".join(["docker", *w[i:]])      # a remote host or context is the stand/janitor gates' business
        janitor_volume = ev.agent == "janitor" and re.fullmatch(r"docker\s+volume\s+rm(\s+(-f|--force))?(\s+[\w.-]+)+", line)
        if not janitor_volume and (re.search(r"docker[\s-]compose\b.*\bdown\b.*(\s-v\b|--volumes)", line) or
                                   re.search(r"docker\s+(volume\s+(rm|prune)|system\s+prune\b.*--volumes)", line)):
            return "This destroys Docker volumes (databases of this and other projects). Ask the user with a named list first."
        if re.search(r"nix-collect-garbage\s+(-d|--delete-old)|nix\s+profile\s+wipe-history|nix-store\s+--delete", line):
            return "Deleting old generations removes system rollbacks. Only on the user's direct request."
        if re.search(r"^(reboot|poweroff|shutdown|halt)\b|systemctl\s+(reboot|poweroff|restart\s+(docker|display-manager|nix-daemon))", line):
            return "This interrupts the user's session. Prepare the step and let the user run it."
        if re.search(r"^nixos-rebuild\s+(switch|boot|test)\b|^home-manager\s+switch\b|^darwin-rebuild\s+switch\b", line):
            return "Switching the system/home generation is done by the user. Build with `nixos-rebuild build` and report."
        if re.search(r"^(mkfs(\.\w+)?|wipefs)\b|\bdd\b.*\bof=/dev/", line):
            return "Disk-level destructive command."
    return None


# ---------------------------------------------------------------- secrets

SECRET_FILE = re.compile(
    r"(^|[\s/'\"=])\.env(\.(?!example(?=$|[\s'\"]))[\w.-]+)?(?=$|[\s'\"])"   # .env, .env.local; not .env.example
    r"|[\w-]\.(pem|key|p12|pfx)\b"                                       # cert.pem, tls.key
    r"|\bid_(rsa|ed25519|ecdsa)\b(?!\.pub)"                             # ssh private keys
    r"|\bkeys\.txt\b")                                                  # age / sops key file
SECRET_VAR = re.compile(r"\$\{?\w*(SECRET|TOKEN|PASSWORD|PASSWD|API_KEY|PRIVATE|CREDENTIAL|DSN|DATABASE_URL)\w*", re.I)
READERS = {"cat", "less", "more", "head", "tail", "bat", "nl", "xxd", "od", "hexdump", "strings", "base64",
           "jq", "yq", "sed", "awk", "grep", "rg", "cp", "scp", "rsync", "source", ".", "diff", "vim", "nano"}


def check_secrets(ev: Event, cmd: str) -> str | None:
    for seg in expand(cmd):
        w = words(seg)
        if not w:
            continue
        if (w[0] in {"printenv", "env", "set"} and len(w) == 1) or (w[0] == "export" and (len(w) == 1 or "-p" in w)):
            return "Printing the whole environment exposes secrets. Check one variable with `test -n \"$NAME\"`."
        if w[0] == "printenv" and SECRET_VAR.search("$" + " $".join(w[1:])):
            return "Do not print secret values. Check presence with `test -n \"$NAME\"`."
        if Path(w[0]).name in READERS and SECRET_FILE.search(" " + " ".join(w[1:])):
            if w[0] in {"grep", "rg"} and any(a in {"-q", "--quiet", "-c", "--count", "-l"} for a in w):
                continue
            return "Do not read secret files into the output. To check a variable is set: `grep -q '^NAME=.' .env`."
        if w[0] in {"echo", "printf"} and SECRET_VAR.search(seg):
            return "Do not print secret values."
        if w[:3] == ["gh", "secret", "set"] and any(a in {"--body", "-b"} or a.startswith("--body=") for a in w):
            return "Pass the secret through stdin (`gh secret set NAME < file`), not as an argument."
        if w[0] == "sops" and any(a in {"-d", "--decrypt", "decrypt"} for a in w[1:]):
            if "--extract" in seg and re.search(r">\s*/dev/null", seg):
                continue
            return "Do not decrypt sops files to the terminal or a file. Use `sops exec-env` or `--extract … >/dev/null` to check."
        if (w[:3] == ["docker", "compose", "config"] or w[:2] == ["docker-compose", "config"]) \
                and not any(a in {"--quiet", "-q", "--services", "--volumes", "--images"} for a in w):
            return "`docker compose config` prints resolved secrets. Use `docker compose config --quiet`."
    return None


# ---------------------------------------------------------------- tests via bash

REDIRECT = re.compile(r"(?:\d?>{1,2}\|?|&>>?)\s*['\"]?([^\s;&|'\"<>]+)")
# Commands whose path arguments are written to (for cp/ln/install/rsync only the destination).
WRITE_ANY_ARG = {"tee", "rm", "rmdir", "touch", "truncate", "chmod", "chown", "mkdir", "shred", "unlink"}
WRITE_DEST_ONLY = {"cp", "ln", "install", "rsync"}
GIT_WRITE_PATHS = {"checkout", "restore", "rm", "mv", "apply"}


DIFF_TARGET = re.compile(r"^(?:\+\+\+|---) (?:[ab]/)?(\S+)", re.M)


def _diff_targets(diff_file: str | None, cwd: Path) -> list[str]:
    """Files a patch touches; an unreadable patch (stdin/heredoc) is treated as touching tests."""
    if diff_file:
        p = Path(diff_file) if Path(diff_file).is_absolute() else cwd / diff_file
        try:
            return [t for t in DIFF_TARGET.findall(p.read_text(errors="replace")) if t != "/dev/null"]
        except OSError:
            pass
    return ["test/ (patch target unknown)"]


def _test_paths_written(seg: str, cwd: Path) -> list[str]:
    hits = [p for p in REDIRECT.findall(seg) if is_test_path(p.removeprefix("./"))]
    w = words(seg)
    if not w:
        return hits
    name = Path(w[0]).name
    args = [a for a in w[1:] if not a.startswith("-") and not re.fullmatch(r"\d?[<>]{1,2}&?\d?|<<-?\w*", a)]
    redirected_in = re.search(r"<\s*['\"]?([^\s;&|'\"<>]+)", seg)
    cand: list[str] = []
    if name in WRITE_ANY_ARG or name == "mv":         # moving a test away changes it too
        cand = args
    elif name in WRITE_DEST_ONLY and args:
        cand = [args[-1]]
    elif name in {"sed", "perl"} and any(a.startswith("-i") or a == "--in-place" for a in w[1:]):
        cand = args
    elif name == "patch":
        src = next((a[2:] or None for a in w[1:] if a.startswith("-i")), None) or \
            (redirected_in.group(1) if redirected_in else None)
        cand = _diff_targets(src, cwd)
    elif name == "dd":
        cand = [a[3:] for a in w[1:] if a.startswith("of=")]
    elif name == "git" and len(w) > 1 and w[1] == "apply":
        cand = [t for f in (args[1:] or [None]) for t in _diff_targets(f, cwd)]
    elif name == "git" and len(w) > 1 and w[1] in GIT_WRITE_PATHS:
        cand = args[1:]
    return hits + [c for c in cand if is_test_path(c.removeprefix("./"))]


def check_tests_via_bash(ev: Event, cmd: str) -> str | None:
    if ev.agent not in NO_TEST_WRITE:
        return None
    for seg in expand(cmd):
        written = [p for p in _test_paths_written(seg, ev.cwd)
                   if not _explicit_write(ev.agent, rel(ev.cwd / p, ev.project_root), ev.project_root)]
        if written:
            return (f"`{ev.agent}` may read tests but never change them ({', '.join(written[:3])}). If a test looks "
                    "wrong, stop with STATUS: blocked and explain; the orchestrator returns it to test-writer.")
    return None


# ---------------------------------------------------------------- writes via bash

# Options that take a separate value, per command (so the value is not mistaken for a file).
WRITE_VALUE_FLAGS = {"cp": {"-t", "--target-directory", "-S", "--suffix"},
                     "mv": {"-t", "--target-directory", "-S", "--suffix"},
                     "install": {"-m", "-o", "-g", "-t", "--target-directory", "-S", "--suffix"},
                     "touch": {"-d", "-t", "-r", "--date", "--reference"},
                     "truncate": {"-s", "-r", "--size", "--reference"},
                     "sed": {"-e", "-f", "--expression", "--file"}, "perl": {"-e", "-E", "-I", "-M", "-m"},
                     "awk": {"-v", "-f", "-i", "-F", "--file", "--assign", "--include", "--field-separator"}}
UNRESOLVED = "$(unresolved)"      # stands for a redirection target the hook cannot know (substitution, missing word)
UNKNOWN_DIR = "$UNKNOWN_DIR"      # the directory after `cd $VAR` / `cd -`
DEVICES = {"/dev/null", "/dev/stdout", "/dev/stderr"}
DUP_TARGET = re.compile(r"\d+|-")


def _file_args(name: str, args: list[str]) -> list[str]:
    out: list[str] = []
    skip = False
    for a in args:
        if skip:
            skip = False
        elif a.startswith("-") and a != "-":
            skip = "=" not in a and a in WRITE_VALUE_FLAGS.get(name, set())
        else:
            out.append(a)
    return out


def _read_word(text: str, i: int) -> tuple[str, int]:
    """The shell word that starts at `i` (quotes removed, `$(…)` kept whole) and the index after it."""
    out: list[str] = []
    quote = ""
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\" and quote != "'" and i + 1 < n:
            out.append(text[i + 1])
            i += 2
        elif quote:
            if c == quote:
                quote = ""
            else:
                out.append(c)
            i += 1
        elif c in "'\"":
            quote, i = c, i + 1
        elif c == "$" and text.startswith("$(", i):
            end = _matching_paren(text, i + 2)
            out.append(text[i:end + 1])
            i = end + 1
        elif c in " \t\n;&|<>()":
            break
        else:
            out.append(c)
            i += 1
    return "".join(out), i


def _scan_redirections(text: str) -> tuple[list[str], str]:
    """Targets of unquoted `>` redirections (`>f`, `x>f`, `>>f`, `>|f`, `2>f`, `&>f`, `>&f`, `<<EOF>f`) and the
    text without them. `>&2` / `>&-` duplicate a descriptor and `>(cmd)` is a process substitution: not files."""
    out: list[str] = []
    kept: list[str] = []
    quote = ""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\" and quote != "'":
            kept.append(text[i:i + 2])
            i += 2
        elif quote:
            quote = "" if c == quote else quote
            kept.append(c)
            i += 1
        elif c in "'\"":
            quote = c
            kept.append(c)
            i += 1
        elif c == ">":
            j = i + 1
            j += text.startswith(">", j)
            dup = text.startswith("&", j)
            j += text.startswith(("&", "|"), j)
            while j < n and text[j] in " \t":
                j += 1
            if text.startswith("(", j):
                kept.append(text[i:j])
                i = j
                continue
            word, end = _read_word(text, j)
            if not word:
                out.append(UNRESOLVED)
            elif not (dup and DUP_TARGET.fullmatch(word)):
                out.append(word)
            prefix = re.search(r"(?:(?<=\s)|^)(?:\d+|&)$", "".join(kept))   # the `2` of `2>f`, the `&` of `&>f`
            if prefix:
                del kept[len(kept) - len(prefix.group()):]
            kept.append(" ")
            i = end
        else:
            kept.append(c)
            i += 1
    return out, "".join(kept)


def _strip_redirections(w: list[str]) -> list[str]:
    """Drop redirection words (`>f`, `2>`, `>&2`, `<in`, `<<EOF`) and the target word of a bare operator."""
    out: list[str] = []
    skip = False
    for a in w:
        if skip:
            skip = False
        elif REDIRECT_WORD.fullmatch(a) or re.fullmatch(r"&>>?\S*", a):
            skip = REDIRECT_OPERATOR.fullmatch(a) is not None or a in {"&>", "&>>"}
        else:
            out.append(a)
    return out


def _under(cwd: str, target: str) -> str:
    if cwd == "." or target.startswith(("/", "~", "$")):
        return target
    return posixpath.join(cwd, target)


def _cd(cwd: str, arg: str) -> str:
    if not arg or arg == "-":
        return UNKNOWN_DIR
    if arg.startswith(("/", "~", "$")):
        return arg
    return posixpath.normpath(posixpath.join(cwd, arg))


DEST_SHORT_VALUE = {"cp": "St", "mv": "St", "install": "mogSt", "ln": "St"}   # short options that take a value
DEST_LONG_VALUE = {"--suffix", "--mode", "--owner", "--group", "--strip-program", "--context"}


def _dest_args(name: str, args: list[str]) -> tuple[str | None, list[str], bool]:
    """(directory of -t / --target-directory, positional words, -d given) of cp, mv, install, ln."""
    short = DEST_SHORT_VALUE[name]
    target: str | None = None
    pos: list[str] = []
    directories = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos += args[i + 1:]
            break
        if a.startswith("--"):
            flag, eq, value = a.partition("=")
            if flag == "--target-directory":
                if eq:
                    target = value
                elif i + 1 < len(args):
                    i += 1
                    target = args[i]
            elif flag in DEST_LONG_VALUE and not eq:
                i += 1
        elif a.startswith("-") and a != "-":
            for j, ch in enumerate(a[1:], 1):
                if ch == "d" and name == "install":
                    directories = True
                if ch in short:
                    value = a[j + 1:]
                    if not value and i + 1 < len(args):
                        i += 1
                        value = args[i]
                    if ch == "t":
                        target = value or None
                    break
        else:
            pos.append(a)
        i += 1
    return target, pos, directories


def _into(directory: str, sources: list[str]) -> list[str]:
    """Files created in `directory` by copying or linking `sources` (a source that is not a literal gives `_`)."""
    names = [posixpath.basename(p.rstrip("/")) if not re.search(r"[$`]", p) else "" for p in sources]
    return [posixpath.join(directory, n or "_") for n in names or [""]]


def _copy_writes(name: str, args: list[str]) -> list[str]:
    """Paths written by cp, mv, install and ln: the destination, with -t the directory; mv also removes its
    sources, ln writes the link name."""
    target, pos, directories = _dest_args(name, args)
    if name == "install" and directories:
        return pos
    if target is not None:
        return _into(target, pos) + (pos if name == "mv" else [])
    if name == "mv":
        return pos
    if name == "ln":
        return [posixpath.basename(pos[0].rstrip("/")) or "_"] if len(pos) == 1 else pos[-1:]
    return pos[-1:]


def _command_writes(w: list[str], cwd: str, depth: int) -> list[str]:
    """Files written by one resolved command (redirections are handled by the caller)."""
    if not w:
        return []
    name, args = Path(w[0]).name, w[1:]
    files = _file_args(name, args)
    if name in SHELLS:
        script = _shell_script(w)
        return _written_files(script, depth + 1, cwd) if script is not None else []
    if name == "eval":
        return _written_files(" ".join(args), depth + 1, cwd)
    if name == "xargs":
        i = 0
        while i < len(args) and args[i].startswith("-"):
            i += 2 if args[i] in XARGS_VALUE_OPTIONS else 1
        return _command_writes(_resolve(_strip_redirections(args[i:]))[0], cwd, depth + 1)
    if name == "find":
        return [t for c in _find_exec_commands(w) for t in _command_writes(_resolve(c)[0], cwd, depth + 1)]
    if name == "tee":
        return files
    if name in {"sed", "perl"} and any(re.fullmatch(r"-[A-Za-z]*i\S*|--in-place.*", a) for a in args):
        has_script = any(a in WRITE_VALUE_FLAGS[name] for a in args)
        return files if has_script else files[1:]
    if name in {"awk", "gawk"} and any(a == "-iinplace" or a == "inplace" or a.startswith("--include=inplace")
                                       for a in args):
        return files if any(a in {"-f", "--file"} for a in args) else files[1:]
    if name in {"cp", "install", "mv", "ln"}:
        return _copy_writes(name, args)
    if name in {"touch", "truncate"}:
        return files
    if name == "dd":
        return [a[3:] for a in args if a.startswith("of=")]
    return []


def _written_files(text: str, depth: int = 0, cwd: str = ".") -> list[str]:
    """Paths a command line writes to: redirections, tee, sed/perl -i, awk -i inplace, cp/mv/install, touch,
    truncate, dd. Relative paths are resolved against the directory set by earlier `cd`s (`cwd`, relative to
    the session directory); a path that cannot be known contains `$` or starts with `~`."""
    if depth > MAX_DEPTH:
        return []
    try:
        commands = _split_commands(text.replace("\\\n", " "))
    except NestingError:
        return []
    out: list[str] = []
    for command in commands:
        redirected, bare = _scan_redirections(command.text)
        w = _strip_redirections(_resolve(split_words(bare, comments=False))[0])
        if w and Path(w[0]).name in {"cd", "pushd"}:
            cwd = _cd(cwd, _first_argument(w[1:]))
        targets = redirected + _command_writes(w, cwd, depth)
        out += [_under(cwd, t) for t in targets]
    return out


def _expand_home(target: str) -> str | None:
    """`~/x`, `$HOME/x`, `${HOME}/x` with the real home directory; None if HOME is unknown."""
    m = re.match(r"(~|\$HOME|\$\{HOME\})(?=/|$)", target)
    if not m:
        return target
    home = os.environ.get("HOME", "").rstrip("/")
    return home + target[m.end():] if home.startswith("/") else None


def check_bash_writes(ev: Event, cmd: str) -> str | None:
    """Bash writes follow the rules of Write/Edit for the same agent."""
    if not ev.agent:
        return None
    reader = ev.agent in READER_AGENTS | {"stand-operator", "janitor"}
    for target in _written_files(cmd):
        unresolved = not target or re.search(r"[$`]", target) is not None or target.startswith("~")
        if reader:
            if target in DEVICES:
                continue
            if unresolved:
                return (f"`{ev.agent}` is read-only: the Bash write target `{target or '(missing)'}` cannot be resolved, "
                        "so it is refused. Write only to a literal path under /tmp, /var/tmp or the scratchpad.")
        else:
            expanded = _expand_home(target)
            if expanded is None:
                return (f"`{ev.agent}` writes only inside the project: the Bash write target `{target}` is in the home "
                        "directory, which is unknown here, so it is refused.")
            target = expanded
            if not target or re.search(r"[$`]", target) or target.startswith(("~", "/dev/")):
                continue
        r = rel(ev.cwd / target, ev.project_root)
        if reader:
            if r.startswith("/") and _is_temp(r):
                continue
            return (f"`{ev.agent}` is read-only: the Bash write to `{r}` is refused. Only /tmp, /var/tmp and the "
                    "scratchpad are writable; report what you found in the answer.")
        if r.startswith("/") and _is_temp(r):
            continue                      # temp dirs are free for every subagent
        probe = Event(raw={}, tool="Write", tool_input={"file_path": r}, agent=ev.agent, cwd=ev.cwd)
        reason = check_write(probe)
        if reason:
            return f"Bash write to `{r}` is refused: {reason}"
    return None


# ---------------------------------------------------------------- reader gate (D4, D11)
# deny-by-default: a command of deploy-error-reader / log-collector runs only if every resolved command word is
# an allowed read/status subcommand of a deploy CLI or a read utility.
READER_AGENTS = {"deploy-error-reader", "log-collector"}
READER_ALLOWED = {
    "gh": [("auth", "status"), ("run", "list"), ("run", "view")],
    "railway": [("whoami",), ("logs",), ("status",), ("deployment", "list")],
    "gcloud": [("auth", "list"), ("logging", "read"), ("run", "services", "logs", "read")],
    "doctl": [("account", "get"), ("apps", "logs"), ("apps", "list"), ("apps", "get"), ("apps", "list-deployments"),
              ("apps", "get-deployment")],
    "yc": [("iam", "whoami"), ("config", "get", "folder-id"), ("config", "get", "cloud-id"), ("logging", "read"),
           ("logging", "group", "list")],
    "wrangler": [("whoami",), ("tail",)],
    "cf": [("auth", "whoami"), ("auth", "list"), ("docs", "search"), ("cli", "search"), ("schema",),
           ("workers", "list"), ("workers", "get"), ("workers", "deployments"), ("workers", "versions")],
    "docker": [("compose", "ps"), ("compose", "logs"), ("logs",), ("version",), ("ps",), ("container", "ls"),
               ("volume", "ls"), ("network", "ls"), ("compose", "ls")],
}
# Global flags that take a separate value / flags without one. Any other flag before the subcommand is refused.
READER_VALUE_FLAGS = {"-R", "--repo", "-f", "--file", "-p", "--project-name", "--context", "-H", "--host",
                      "-c", "--config", "--profile", "--project-directory", "--env-file", "--project", "--account",
                      "--configuration", "-t", "--access-token", "-z", "--folder-id", "--cloud-id"}
READER_BOOL_FLAGS = {"--help", "-h", "--version", "--debug", "-D", "--quiet", "-q", "--verbose"}
READER_UTILS = {"date", "echo", "printf", "test", "[", "[[", "true", "sleep", "fi", "done", "ss"}
READER_FILTERS = {"head", "tail", "grep", "jq", "wc", "sort", "uniq", "cut", "tr"}   # stdin only, no file operands
TRUSTED_BIN = ("/nix/store/", "/usr/bin/", "/bin/", "/run/current-system/sw/bin/")
AWK_UNSAFE = re.compile(r"system\s*\(|\|\s*getline|getline\s*<|\bprintf?\b[^;}]*(\||>>?\s*[\"\w$(])")


def _reader_cli_allowed(name: str, args: list[str]) -> bool:
    """The first positional words of `args` form an allowed subcommand; flags before it must be known."""
    allowed = READER_ALLOWED[name]
    pos: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("-") and a != "-":
            flag = a.partition("=")[0]
            if flag in READER_VALUE_FLAGS:
                i += 1 if "=" in a else 2
            elif flag in READER_BOOL_FLAGS:
                i += 1
            else:
                return False
            continue
        pos.append(a)
        i += 1
        if any(tuple(pos[:len(p)]) == p for p in allowed):
            return True
    return False


SECRET_COMMANDS = [
    (("yc", "config", "list"), "prints the profile with the token"),
    (("yc", "iam", "create-token"), "prints a token"),
    (("gh", "auth", "token"), "prints a token"),
    (("railway", "variable", "list"), "prints variable values"),
    (("railway", "variables"), "prints variable values"),
    (("doctl", "auth", "token"), "prints a token"),
    (("doctl", "databases", "connection"), "prints a connection string with the password"),
]


def _positionals(args: list[str]) -> list[str]:
    """Words that are not flags or flag values (the global flags of the deploy CLIs take a value)."""
    out: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("-") and a != "-":
            i += 2 if a in READER_VALUE_FLAGS else 1
        else:
            out.append(a)
            i += 1
    return out


def _secret_reason(name: str, args: list[str], agent: str, shown: str) -> str | None:
    """Readers never print secrets (AC15)."""
    why = None
    if name == "printenv" or (name == "env" and not [a for a in args if not a.startswith("-") and "=" not in a]):
        why = "dumps the environment"
    else:
        pos = _positionals(args)
        for head, text in SECRET_COMMANDS:
            if name == head[0] and tuple(pos[:len(head) - 1]) == head[1:]:
                why = text
        if name == "gh" and pos[:2] == ["auth", "status"] and any(
                a.startswith("--show-token") or (a.startswith("-") and not a.startswith("--") and "t" in a)
                for a in args):
            why = "prints a token"
    if why is None:
        return None
    return f"`{agent}` never prints secrets: `{shown}` {why} and is refused."


SS_ARGS = re.compile(r"-[a-zA-Z]*|--(listening|numeric|tcp|udp|processes|all|summary|ipv4|ipv6|unix)")
SED_BAD = "sed {} runs a command or writes a file (e, w, W, s///e, s///w and -f are refused)"


def _sed_script_reason(script: str) -> str | None:
    """Walk a sed script command by command: the e, w and W commands and the e and w flags of s///."""
    i, n = 0, len(script)
    while i < n:
        while i < n and script[i] in " \t\n;{}!":
            i += 1
        while i < n:                                    # the address
            c = script[i]
            if c == "/" or (c == "\\" and i + 1 < n):
                delim = c if c == "/" else script[i + 1]
                i += 1 if c == "/" else 2
                while i < n and script[i] != delim:
                    i += 2 if script[i] == "\\" else 1
                i += 1
            elif c.isdigit() or c in "$,~+IM \t!":
                i += 1
            else:
                break
        if i >= n:
            break
        cmd = script[i]
        i += 1
        if cmd in "ewW":
            return f"the `{cmd}` command"
        if cmd in "sy" and i < n:
            delim = script[i]
            i += 1
            for _ in range(2):
                while i < n and script[i] != delim:
                    i += 2 if script[i] == "\\" else 1
                i += 1
            end = i
            while end < n and script[end] not in ";\n}":
                end += 1
            if cmd == "s" and re.search(r"[ew]", script[i:end]):
                return "an `e` or `w` flag of s///"
            i = end
        elif cmd == "#" or cmd in "aicrR:btTlLqQ":      # text, file or label up to the end of the line / command
            while i < n and script[i] not in ("\n" if cmd in "aicrR#" else ";\n"):
                i += 1
    return None


def _sed_reason(args: list[str]) -> str | None:
    scripts: list[str] = []
    positional: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            positional += args[i + 1:]
            break
        if a.startswith("--"):
            flag, eq, value = a.partition("=")
            if len(flag) >= 4 and "--file".startswith(flag):
                return SED_BAD.format("-f / --file")
            if len(flag) >= 3 and "--expression".startswith(flag):
                if not eq and i + 1 < len(args):
                    i += 1
                    value = args[i]
                scripts.append(value)
        elif a.startswith("-") and a != "-":
            for j, ch in enumerate(a[1:], 1):
                if ch == "f":
                    return SED_BAD.format("-f / --file")
                if ch in "el":
                    value = a[j + 1:]
                    if not value and i + 1 < len(args):
                        i += 1
                        value = args[i]
                    if ch == "e":
                        scripts.append(value)
                    break
                if ch == "i":
                    break
        else:
            positional.append(a)
        i += 1
    if not scripts and positional:
        scripts = [positional[0]]
    for script in scripts:
        why = _sed_script_reason(script)
        if why:
            return SED_BAD.format(f"with {why}")
    return None


def _reader_util_reason(name: str, args: list[str]) -> str | None:
    """Why a read utility is refused with these arguments, or None."""
    if name == "sort" and any(re.fullmatch(r"-[A-Za-z]*o\S*|--output.*", a) for a in args):
        return "sort -o writes a file"
    if name == "uniq" and len(_file_args("uniq", [a for a in args if a != "-f"])) > 2:
        return "uniq with an output file writes it"
    if name == "rg" and any(a.startswith("--pre") for a in args):
        return "rg --pre runs a command"
    if name == "date" and any(a in {"-s", "--set"} or a.startswith("--set=") for a in args):
        return "date -s changes the clock"
    if name == "sort" and any(a.startswith("--compress") for a in args):
        return "sort --compress-program runs a command"
    if name == "awk" and any(re.fullmatch(r"-[fiE]\S*|--(file|include|exec|source)\S*", a) for a in args):
        return "awk -f, -i and --include load a program or extension"
    if name == "awk" and any(AWK_UNSAFE.search(a) for a in args):
        return "awk program runs commands or writes files"
    if name == "sed":
        return _sed_reason(args)
    if name == "ss" and not all(SS_ARGS.fullmatch(a) or not a.startswith("-") for a in args):
        return "ss options other than the listing ones can kill sockets or write files"
    return None


# per filter: (short options with a value, short flags, long options with a value, long flags, max positionals)
_F = {
    "head": ("nc", "qvz0123456789", {"--lines", "--bytes"}, {"--quiet", "--silent", "--verbose", "--zero-terminated"}, 0),
    "tail": ("ncs", "qvzfF0123456789", {"--lines", "--bytes", "--pid", "--sleep-interval"},
             {"--quiet", "--silent", "--verbose", "--zero-terminated", "--follow", "--retry"}, 0),
    "grep": ("eAmBC", "EFGPiIvwxcLlnoqsHhTaUzVb", {"--regexp", "--max-count", "--after-context", "--before-context",
                                                    "--context", "--label"},
             {"--extended-regexp", "--fixed-strings", "--basic-regexp", "--perl-regexp", "--ignore-case",
              "--no-ignore-case", "--invert-match", "--word-regexp", "--line-regexp", "--count", "--files-with-matches",
              "--files-without-match", "--line-number", "--only-matching", "--quiet", "--silent", "--no-messages",
              "--with-filename", "--no-filename", "--text", "--null", "--null-data", "--byte-offset", "--initial-tab",
              "--binary", "--line-buffered", "--color", "--colour"}, 1),
    "jq": ("", "cCrjasSneRM", {"--indent"}, {"--null-input", "--raw-input", "--slurp", "--compact-output",
                                            "--raw-output", "--join-output", "--ascii-output", "--sort-keys",
                                            "--color-output", "--monochrome-output", "--tab", "--exit-status",
                                            "--seq", "--stream", "--unbuffered"}, 1),
    "wc": ("", "clmLw", set(), {"--bytes", "--chars", "--lines", "--words", "--max-line-length"}, 0),
    "sort": ("ktSTo", "bdfghiMnRrsuVzcCm", {"--key", "--field-separator", "--buffer-size", "--temporary-directory",
                                            "--parallel", "--batch-size"},
             {"--reverse", "--numeric-sort", "--unique", "--ignore-case", "--stable", "--human-numeric-sort",
              "--version-sort", "--month-sort", "--general-numeric-sort", "--ignore-leading-blanks",
              "--dictionary-order", "--ignore-nonprinting", "--check", "--zero-terminated", "--merge", "--debug",
              "--random-sort"}, 0),
    "uniq": ("fsw", "cdDuiz", {"--skip-fields", "--skip-chars", "--check-chars"},
             {"--count", "--repeated", "--unique", "--ignore-case", "--zero-terminated"}, 0),
    "cut": ("dfcb", "snz", {"--delimiter", "--fields", "--characters", "--bytes", "--output-delimiter"},
            {"--complement", "--only-delimited", "--zero-terminated"}, 0),
    "tr": ("", "cCdst", set(), {"--complement", "--delete", "--squeeze-repeats", "--truncate-set1"}, 2),
}
JQ_FILE_WORDS = re.compile(r"\benv\b|\$ENV|input_filename|\bimport\b|\binclude\b|\$__prog|get_search_list")


def _filter_reason(name: str, args: list[str]) -> str | None:
    """A stdin filter reads its standard input only: no file operand, no option that reads or runs a file."""
    short_val, short_flag, long_val, long_flag, max_pos = _F[name]
    pos: list[str] = []
    patterns = 0
    i = 0
    while i < len(args):
        a = args[i]
        i += 1
        if a == "--":
            pos += args[i:]
            break
        if a.startswith("--"):
            flag, eq, _ = a.partition("=")
            if flag in long_val:
                if not eq:
                    i += 1
                if flag == "--regexp":
                    patterns += 1
            elif flag not in long_flag:
                return f"the option `{a}` is not a plain stdin filter option"
        elif a.startswith("-") and a != "-":
            for j, ch in enumerate(a[1:], 1):
                if ch in short_val:
                    if j == len(a) - 1:
                        i += 1
                    if ch == "e" and name == "grep":
                        patterns += 1
                    break
                if ch not in short_flag:
                    return f"the option `{a}` is not a plain stdin filter option"
        else:
            pos.append(a)
    if name == "grep":
        if (patterns and pos) or len(pos) > 1:
            return "grep reads its standard input only; a file operand is refused"
        return None
    if name == "jq" and any(JQ_FILE_WORDS.search(p) for p in pos[:1]):
        return "the jq program reads the environment or a file"
    if len(pos) > max_pos:
        return f"{name} reads its standard input only; the file operand is refused"
    return None


def _reader_words(w: list[str], agent: str, depth: int) -> str | None:
    """Reason to refuse one resolved command (word list), or None."""
    if depth > MAX_DEPTH:
        return NIX_DEPTH_REASON
    if not w:
        return None
    head = w[0]
    shown = " ".join(w)[:200]
    deny = (f"`{agent}` is read-only: `{shown}` is not an allowed read/status command. Allowed: auth checks and "
            "run/log/status listings of gh, railway, gcloud, doctl, yc, wrangler, cf, docker, plus grep, jq, head, "
            "tail, wc, sort, uniq, cut, tr as filters on a pipe. Files are read with Read, Grep and Glob. "
            "Report what must be done to the orchestrator.")
    if re.search(r"[$`*?]", head) or ("/" in head and not head.startswith(TRUSTED_BIN)):
        return f"`{agent}` is read-only: the command word `{head}` cannot be resolved, `{shown}` is refused."
    name = Path(head).name
    args = w[1:]
    secret = _secret_reason(name, args, agent, shown)
    if secret:
        return secret
    if name in SHELLS:
        script = _shell_script(w)
        return _reader_reason(script, agent, depth + 1) if script is not None else deny
    if name == "eval":
        return _reader_reason(" ".join(args), agent, depth + 1)
    if name == "xargs":
        i = 0
        while i < len(args) and args[i].startswith("-"):
            i += 2 if args[i] in XARGS_VALUE_OPTIONS else 1
        return _reader_words(_resolve(_strip_redirections(args[i:]))[0], agent, depth + 1)
    if name in READER_ALLOWED or name == "docker-compose":
        if name == "docker-compose":
            name, args = "docker", ["compose", *args]
        return None if _reader_cli_allowed(name, args) else deny
    if name in READER_FILTERS:
        why = _reader_util_reason(name, args) or _filter_reason(name, args)
        return f"`{agent}` is read-only: `{shown}` is refused ({why})." if why else None
    if name in READER_UTILS:
        why = _reader_util_reason(name, args)
        return f"`{agent}` is read-only: `{shown}` is refused ({why})." if why else None
    return deny


def _reader_reason(cmd: str, agent: str, depth: int = 0) -> str | None:
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
            return f"`{agent}` is read-only: `{' '.join(raw[:4])}` runs with elevated rights and is refused."
        final = _strip_redirections(_resolve(raw)[0])
        reason = _reader_words(final, agent, depth)
        if reason:
            return reason
    return None


def check_deploy_reader(ev: Event, cmd: str) -> str | None:
    if ev.agent not in READER_AGENTS:
        return None
    return _reader_reason(cmd, ev.agent)


# ---------------------------------------------------------------- reader inputs (AC20)
# Every agent that runs "what a reader may run": environment prefixes and credential files are refused for all four.
ALL_READER_AGENTS = READER_AGENTS | {"stand-operator", "janitor"}
SAFE_ENV = re.compile(r"TZ|NO_COLOR|LC_\w+")
LOCAL_VAR = re.compile(r"(?![a-z0-9_]*_proxy$)[a-z][a-z0-9_]*")      # lowercase names mean nothing to a shell or a CLI
CREDENTIAL_DIRS = (r"(?:\.config/(?:gh|gcloud|yandex-cloud|doctl|\.wrangler)(?![\w-])|\.railway(?![\w-])"
                   r"|\.wrangler(?![\w-])|\.docker/config\.json|\.kube/config(?![\w-]))[^\s;&|)]*")


@lru_cache(maxsize=4)
def _credential_path(home: str) -> re.Pattern[str]:
    homes = [r"~[^/\s]*", r"\$HOME", r"\$\{HOME\}", r"/home/[^/\s]+", r"/root"]
    if home.startswith("/") and home.strip("/"):
        homes.append(re.escape(home.rstrip("/")))
    return re.compile("(?:" + "|".join(homes) + ")/" + CREDENTIAL_DIRS)


def _env_reason_words(w: list[str], agent: str, depth: int) -> str | None:
    """Assignments in front of the command (also behind env, nix shell -c, bash -c) other than TZ, LC_*, NO_COLOR."""
    if depth > MAX_DEPTH:
        return NIX_DEPTH_REASON
    shown = " ".join(w)[:200]
    for _ in range(MAX_DEPTH):
        stripped = strip_env_and_wrappers(w)
        dropped = w[:max(0, len(w) - len(stripped))]
        if any(a.startswith("-S") for a in dropped if not a.startswith("--")):
            return f"`{agent}` is read-only: `{shown}` uses `env -S`, which hides assignments, and is refused."
        for a in dropped:
            m = re.fullmatch(r"(\w+)=.*", a)
            if m and not stripped and LOCAL_VAR.fullmatch(m.group(1)):
                continue        # `out=$(…)` alone sets a shell variable for the later commands, not an environment
            if m and not SAFE_ENV.fullmatch(m.group(1)):
                return (f"`{agent}` is read-only: `{shown}` sets {m.group(1)} in front of the command and is refused. "
                        "Only TZ, LC_* and NO_COLOR may be set.")
        w = stripped
        inner = _unwrap_nix(w) if w else None
        if inner is not None:
            w = inner[0]
        elif w and Path(w[0]).name == "busybox":
            w = w[1:]
        else:
            break
    if not w:
        return None
    name, args = Path(w[0]).name, w[1:]
    if name in SHELLS:
        script = _shell_script(w)
        return _env_reason(script, agent, depth + 1) if script is not None else None
    if name == "eval":
        return _env_reason(" ".join(args), agent, depth + 1)
    if name == "xargs":
        i = 0
        while i < len(args) and args[i].startswith("-"):
            i += 2 if args[i] in XARGS_VALUE_OPTIONS else 1
        return _env_reason_words(_strip_redirections(args[i:]), agent, depth + 1)
    if name == "find":
        return next(filter(None, (_env_reason_words(_strip_redirections(c), agent, depth + 1)
                                  for c in _find_exec_commands(w))), None)
    return None


def _env_reason(cmd: str, agent: str, depth: int = 0) -> str | None:
    if depth > MAX_DEPTH:
        return NIX_DEPTH_REASON
    try:
        commands = _split_commands(cmd.replace("\\\n", " "))
    except NestingError:
        return NIX_DEPTH_REASON
    for command in commands:
        raw = split_words(_scan_redirections(command.text)[1], comments=False)
        reason = _env_reason_words([a for a in raw if a not in KEYWORDS], agent, depth)
        if reason:
            return reason
    return None


def _cd_reason(ev: Event, cmd: str) -> str | None:
    """Readers may `cd` only inside the project and the temp dirs: no `cd ~`, `cd $HOME`, bare `cd`, `cd -`."""
    try:
        commands = _split_commands(cmd.replace("\\\n", " "))
    except NestingError:
        return NIX_DEPTH_REASON
    root = str(ev.project_root).rstrip("/")
    cwd = "."
    for command in commands:
        w = [a for a in split_words(_scan_redirections(command.text)[1], comments=False) if a not in KEYWORDS]
        if not w or Path(w[0]).name not in {"cd", "pushd"}:
            continue
        arg = _first_argument(w[1:])
        shown = " ".join(w)[:200]
        why = f"`{ev.agent}` may not `{shown}`: cd only inside the project or /tmp, /var/tmp and the scratchpad."
        if not arg or arg == "-" or arg.startswith(("~", "$")) or re.search(r"[`$*?]", arg):
            return why
        if arg.startswith("/"):
            path = posixpath.normpath(arg)
            if not (path == root or path.startswith(root + "/") or path.startswith(TMP_PREFIXES)
                    or path in {"/tmp", "/var/tmp"} or "/scratchpad" in path):
                return why
            cwd = "."
            continue
        cwd = posixpath.normpath(posixpath.join(cwd, arg))
        if cwd == ".." or cwd.startswith("../"):
            return why
    return None


def check_reader_inputs(ev: Event, cmd: str) -> str | None:
    """Readers run nothing through the environment and never read the credential files of the deploy CLIs."""
    if ev.agent not in ALL_READER_AGENTS:
        return None
    text = cmd.replace('"', "").replace("'", "")
    hit = _credential_path(os.environ.get("HOME", "")).search(text)
    if hit:
        return (f"`{ev.agent}` never reads the credential files of the deploy CLIs: `{hit.group()}` is refused. "
                "Check access with the auth/whoami commands instead.")
    return _cd_reason(ev, cmd) or _env_reason(cmd, ev.agent or "")


from .infra_checks import check_infra  # noqa: E402 — after the checks above on purpose (import cycle)
from .stand_janitor_checks import check_janitor, check_stand_operator  # noqa: E402

CHECKS = [check_infra, check_reader_inputs, check_deploy_reader, check_stand_operator, check_janitor, check_host_install, check_nix_only, check_git, check_destructive, check_secrets, check_bash_writes, check_tests_via_bash]


def run(ev: Event) -> str | None:
    cmd = ev.tool_input.get("command", "") or ""
    for check in CHECKS:
        try:
            reason = check(ev, cmd)
        except Exception as exc:  # noqa: BLE001 — a bug in one check must not skip the others
            return f"internal error in {check.__name__} ({type(exc).__name__}): denied. Simplify the command."
        if reason:
            return reason
    return None
