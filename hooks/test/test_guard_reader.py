"""Round 7 (checkpoint C2): the reader allowlist runs nothing and writes nothing (AC20);
Bash write targets cover every form of cp, mv, install, ln and the outside-the-project rule (AC21).
Round 8: readers run only R-marked CLI commands and stdin-only filters (AC23).

Same harness as test_guard_bash.py: PreToolUse events for guard_bash.py through helpers.call.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import call, denied, git_repo, reason


def bash(cmd, **kw):
    return call("guard_bash", "Bash", {"command": cmd}, **kw)


# every agent whose Bash is gated by the reader allowlist (stand-operator and janitor run "everything a reader may run")
GATE_AGENTS = ["deploy-error-reader", "log-collector"]
ALL_READERS = [*GATE_AGENTS, "stand-operator", "janitor"]
CODE_EXECUTORS = ["coder", "python-coder", "go-coder", "ts-coder", "rust-coder", "deploy-engineer", "ci-engineer"]
ALL_EXECUTORS = [*CODE_EXECUTORS, "refactorer", "test-writer"]
SCRATCHPAD = "/tmp/claude-1000/-home-user-project/0a1b2c3d-0000-4000-8000-000000000000/scratchpad"
HOME = os.environ.get("HOME", "/home/BadRabbit")
OUTSIDE = "/home/BadRabbit/other/y"        # outside the project (which lives in a temp dir) and not a temp dir
NIX_PKG = {"gh": "gh", "railway": "railway", "gcloud": "google-cloud-sdk", "doctl": "doctl", "yc": "yandex-cloud",
           "wrangler": "wrangler", "docker": "docker", "git": "git"}

PLAN = """# Plan

### T1 — code, green
- **Status:** green
- **Writes (exclusive):** `src/a/app.py`, `src/a/lib/**`
- **Tests (test-writer):** `src/a/tests/test_a.py`

### T2 — tests, red
- **Status:** `red`
- **Writes (exclusive):** `src/b/app.py`
- **Tests (test-writer):** `src/b/tests/test_b.py`, `src/b/tests/unit/**`
"""


def plan_project(plan: str | None = PLAN) -> Path:
    d = Path(tempfile.mkdtemp(prefix="t1r7-proj-"))
    if plan is not None:
        (d / ".plan").mkdir()
        (d / ".plan" / "PLAN.md").write_text(plan)
    return d


def in_nix_shell(cmd):
    return f"nix shell nixpkgs#{NIX_PKG[cmd.split()[0]]} -c {cmd}"


class ReaderGateRunsAndWritesNothing(unittest.TestCase):
    """AC20: the reader allowlist runs nothing and writes nothing."""

    SED = ["sed -n '1e touch src/pwned' README.md",           # e command
           "sed '1e id' README.md",
           "sed -e 'e id' README.md",
           "sed --expression='1e id' README.md",
           "sed 's/a/b/w src/out.txt' README.md",             # w flag of s///
           "sed -n 's/a/b/pw src/out.txt' README.md",
           "sed 's/a/b/e' README.md",                         # e flag of s///
           "sed 's/a/b/ge' README.md",
           "sed 'w src/out.txt' README.md",                   # w and W commands
           "sed -n '/a/w /tmp/t1r7-out.txt' README.md",
           "sed -n '1W src/out.txt' README.md",
           "sed -f s.sed README.md",                          # script file
           "sed --file=s.sed README.md",
           "sed -nf s.sed README.md",
           "nix shell nixpkgs#gnused -c sed -n '1e id' README.md",
           "bash -c \"sed -n '1e id' README.md\"",
           "cat logs/run.txt | sed 's/a/b/w src/out.txt'"]
    GIT = ["git -c core.fsmonitor='touch src/pwned' status",   # -c runs a configured program
           "git -c core.pager=sh log",
           "git -c alias.x='!sh' x",
           "git --config-env=core.pager=X log",
           "git --exec-path=/tmp/t1r7 status",
           "git --exec-path status",
           "git -p log",                                       # -p before the subcommand is --paginate
           "git --paginate log",
           "git diff --ext-diff",
           "git diff --ext-diff HEAD~1",
           "git log -p --ext-diff",
           "git diff --textconv",
           "git show --textconv HEAD:README.md",
           "git log --textconv -p",
           "nix shell nixpkgs#git -c git -c core.pager=sh log",
           "bash -c 'git --paginate log'"]
    SORT_AWK_LESS = ["sort --compress-program=sh logs/run.txt",
                     "sort --compress-program sh logs/run.txt",
                     "sort -u --compress-program=gzip logs/run.txt",
                     "cat logs/run.txt | sort --compress-program=sh",
                     "awk -f p.awk logs/run.txt",
                     "awk --file=p.awk logs/run.txt",
                     "awk -i inplace '{print}' logs/run.txt",
                     "awk -i p.awk '{print}' logs/run.txt",
                     "less logs/run.txt",                      # less runs $LESSOPEN and has the | and ! commands
                     "cat logs/run.txt | less",
                     "bash -c 'less logs/run.txt'"]
    ENV_PREFIX = ["GIT_EXTERNAL_DIFF=sh git diff",
                  "GIT_PAGER=sh git log",
                  "PAGER=sh git log",
                  "LESSOPEN='|sh' cat x",
                  "LD_PRELOAD=/tmp/t1r7/x.so cat logs/run.txt",
                  "PATH=/tmp/t1r7 cat logs/run.txt",
                  "FOO=1 cat logs/run.txt",
                  "TZ=UTC GIT_EXTERNAL_DIFF=sh git diff",
                  "GIT_EXTERNAL_DIFF=sh git diff && date",
                  "date && GIT_EXTERNAL_DIFF=sh git diff",
                  "bash -c 'GIT_EXTERNAL_DIFF=sh git diff'"]
    CREDENTIAL_FILES = ["~/.config/gh/hosts.yml", "~/.config/gcloud/credentials.db",
                        "~/.config/gcloud/application_default_credentials.json",
                        "~/.config/yandex-cloud/config.yaml", "~/.railway/config.json",
                        "~/.config/doctl/config.yaml", "~/.wrangler/config/default.toml",
                        "~/.config/.wrangler/config/default.toml", "~/.docker/config.json", "~/.kube/config",
                        "$HOME/.config/gh/hosts.yml", "${HOME}/.docker/config.json",
                        f"{HOME}/.config/gh/hosts.yml", f"{HOME}/.docker/config.json", f"{HOME}/.kube/config"]
    SHOW_TOKEN = ["gh auth status --show-token", "gh -R o/r auth status --show-token",
                  "gh --repo o/r auth status --show-token", "gh auth status --show-token=true",
                  "gh auth status --show-token=1", "gh auth status -t", "gh -R o/r auth status -t",
                  "gh auth status -h github.com --show-token", "gh auth status --hostname github.com -t",
                  "gh auth status --show-token | head -n 3"]
    SECRET_AFTER_GLOBAL_FLAGS = ["yc --profile x iam create-token", "yc --profile=x iam create-token",
                                 "yc --profile x config list", "yc --folder-id b1g0000 iam create-token",
                                 "gh -R o/r auth token", "doctl --context x auth token",
                                 "doctl --context x databases connection 1111-2222",
                                 "docker --context stand compose config"]
    LISTINGS = ["docker ps", "docker ps -a", "docker container ls", "docker container ls -a", "docker volume ls",
                "docker network ls", "docker compose ls", "docker compose ls -a", "ss -ltn"]
    LISTING_NEIGHBOURS = ["docker volume rm v", "docker volume create v", "docker network rm br-net",
                          "docker network create br-net", "docker container rm c", "docker rm c",
                          "docker run --rm alpine true", "docker volume prune -f"]
    # AC23: `LC_ALL=C sort logs/run.txt` moved out (a filter with a file operand is gone); the stdin form replaces it
    ENV_ALLOWED = ["TZ=UTC date", "docker logs api | LC_ALL=C sort", "LC_ALL=C TZ=UTC date", "NO_COLOR=1 gh run list",
                   "TZ=UTC date && echo ok", "NO_COLOR=1 docker logs api"]

    def assert_denied_for(self, agents, cmds):
        for agent in agents:
            for cmd in cmds:
                with self.subTest(agent=agent, denied=cmd):
                    res = bash(cmd, agent=agent)
                    self.assertTrue(denied(res), f"{agent}: {cmd!r} was allowed")

    def assert_allowed_for(self, agents, cmds):
        for agent in agents:
            for cmd in cmds:
                with self.subTest(agent=agent, allowed=cmd):
                    res = bash(cmd, agent=agent)
                    self.assertFalse(denied(res), f"{agent}: {cmd!r}: {reason(res)}")

    def test_reader_gate_runs_and_writes_nothing(self):
        # sed e/w/W commands, s///e, s///w and -f
        self.assert_denied_for(ALL_READERS, self.SED)
        # git options that run a program
        self.assert_denied_for(ALL_READERS, self.GIT)
        # sort --compress-program, awk -f / -i, less
        self.assert_denied_for(ALL_READERS, self.SORT_AWK_LESS)
        # environment assignments in front of a command, except TZ, LC_*, NO_COLOR
        self.assert_denied_for(ALL_READERS, self.ENV_PREFIX)
        self.assert_allowed_for(ALL_READERS, self.ENV_ALLOWED)
        # CLI credential files cannot be read by any utility
        for agent in ALL_READERS:
            for path in self.CREDENTIAL_FILES:
                for tpl in ("cat {p}", "head -n 5 {p}", "grep -i token {p}", "jq . {p}", "tail {p}",
                            "cat < {p}", "bash -c 'cat {p}'"):
                    cmd = tpl.format(p=path)
                    with self.subTest(agent=agent, denied=cmd):
                        res = bash(cmd, agent=agent)
                        self.assertTrue(denied(res), f"{agent}: {cmd!r} was allowed")
        # gh auth status --show-token in every spelling, SECRET_COMMANDS after global flags
        for agent in ALL_READERS:
            for cmd in [*self.SHOW_TOKEN, *self.SECRET_AFTER_GLOBAL_FLAGS]:
                forms = [cmd, f"bash -c '{cmd}'", f"echo \"$({cmd})\""]
                if cmd.split()[0] in NIX_PKG:
                    forms.append(in_nix_shell(cmd))
                for form in forms:
                    with self.subTest(agent=agent, denied=form):
                        res = bash(form, agent=agent)
                        self.assertTrue(denied(res), f"{agent}: {form!r} was allowed")
                        self.assertIn(cmd.split(" | ")[0], reason(res), f"{form}: the reason does not quote the command")
        # readers may not cd to ~, $HOME or outside the project and temp dirs (no reading a credential file via cd)
        self.assert_denied_for(ALL_READERS, [
            "cd ~/.config && cat gh/hosts.yml", "cd ~ && cat .docker/config.json",
            "cd $HOME/.config/gh && cat hosts.yml", "cd /home/BadRabbit/.config/gh && cat hosts.yml",
            "cd /etc && cat passwd"])
        # AC23: cd and the file readers after it are gone for readers, so these two moved from allowed to denied
        self.assert_denied_for(ALL_READERS, ["cd logs && tail -n 5 run.txt", "cd /tmp && ls"])
        # the janitor git ls-files path denies -c and --config-env too
        self.assert_denied_for(["janitor"], ["git -c core.fsmonitor=x ls-files src/a.py",
                                             "git --config-env=core.pager=X ls-files src/a.py"])
        # read-only listings are added; the removal and creation neighbours stay denied
        for agent in ALL_READERS:
            for cmd in self.LISTINGS:
                forms = [cmd, f"{cmd} | head -n 20", f"{cmd} | grep -i api"]
                if cmd.split()[0] in NIX_PKG:
                    forms.append(in_nix_shell(cmd))
                for form in forms:
                    with self.subTest(agent=agent, allowed=form):
                        res = bash(form, agent=agent)
                        self.assertFalse(denied(res), f"{agent}: {form!r}: {reason(res)}")
        self.assert_denied_for(GATE_AGENTS, self.LISTING_NEIGHBOURS)
        # the probed commands, spelled exactly as in the review
        # AC23: `sed -n 1,20p x` moved to denied (sed is gone for readers)
        self.assert_allowed_for(GATE_AGENTS, ["TZ=UTC date", "docker ps -a", "docker volume ls",
                                              "docker network ls", "docker compose ls", "ss -ltn"])
        self.assert_denied_for(GATE_AGENTS, ["sed -n 1,20p x"])

    def test_reader_gate_existing_reads_stay_allowed(self):
        """Guard: the allowlist keeps the CLI reads readers already do (passes before and after the change).

        AC23 moved the sed/git/sort/awk/cat/grep-on-a-file cases of this guard to
        test_reader_gate_file_readers_are_gone_for_readers: readers read files with Read, Grep and Glob only."""
        self.assert_allowed_for(ALL_READERS, ["date", "gh run list", "gh auth status", "gh -R o/r run list",
                                              "docker logs api"])
        # compose needs -p for stand-operator and janitor (AC16), so the plain forms are for the two readers
        self.assert_allowed_for(GATE_AGENTS, ["docker compose ps", "docker compose logs api"])
        self.assert_allowed_for(["stand-operator", "janitor"], ["docker compose -p stand ps"])

    def test_reader_gate_file_readers_are_gone_for_readers(self):
        """AC23: the file-reading cases that AC20 kept allowed are denied now; the sed/git/sort/awk e/w/-c/-f
        denials of AC20 stay in test_reader_gate_runs_and_writes_nothing."""
        self.assert_denied_for(ALL_READERS, [
            "sed -n 1,20p logs/run.txt", "sed 's/a/b/' logs/run.txt", "sed -n '/error/p' logs/run.txt",
            "sed -n 's/a/b/gp' logs/run.txt", "sed -e 's/a/b/' -e 's/c/d/' logs/run.txt",
            "git log --oneline", "git diff --stat", "git show HEAD --stat", "git log -p",
            "sort logs/run.txt", "sort -u logs/run.txt", "sort -r -k2 logs/run.txt",
            "awk '{print $1}' logs/run.txt", "awk -F, '{print $2}' logs/run.txt", "cat README.md",
            "grep -rn error logs"])
        # git status is not a reader command; the janitor keeps it as part of its tracked-file gate
        self.assert_denied_for(["deploy-error-reader", "log-collector", "stand-operator"],
                               ["git status", "git status --short"])

    def test_reader_gate_runs_and_writes_nothing_does_not_limit_other_agents(self):
        """Guard: the main session and executors keep sed -f, git -c, env prefixes and sort options."""
        cmds = ["sed -f s.sed logs/run.txt", "sed -n '1e id' logs/run.txt", "git -c core.pager=cat log",
                "git --paginate log", "GIT_PAGER=cat git log", "FOO=1 echo ok",
                "sort --compress-program=gzip logs/run.txt", "awk -f p.awk logs/run.txt", "less logs/run.txt",
                "docker volume ls", "docker network ls", "docker ps -a"]
        for agent in [None, "coder", "deploy-engineer", "ci-engineer"]:
            for cmd in cmds:
                with self.subTest(agent=agent, cmd=cmd):
                    res = bash(cmd, agent=agent)
                    self.assertFalse(denied(res), f"{cmd}: {reason(res)}")


class BashWriteTargetsCoverAllForms(unittest.TestCase):
    """AC21: cp, mv, install with -t DIR, -tDIR and --target-directory=DIR check DIR; mv checks its sources;
    ln is a write; executors write outside the project only to temp dirs; unresolved ~ and $HOME are denied."""

    @classmethod
    def setUpClass(cls):
        cls.root = plan_project()

    def run_cmd(self, cmd, agent):
        return bash(cmd, agent=agent, cwd=self.root)

    def assert_allowed_cmd(self, cmd, agent):
        res = self.run_cmd(cmd, agent)
        self.assertFalse(denied(res), f"{agent}: {cmd!r}: {reason(res)}")

    def assert_denied_cmd(self, cmd, agent, names=None):
        res = self.run_cmd(cmd, agent)
        self.assertTrue(denied(res), f"{agent}: {cmd!r} was allowed")
        if names:
            self.assertIn(names, reason(res), f"{agent}: {cmd!r}: the reason does not name {names!r}")

    def test_bash_write_targets_cover_all_forms(self):
        self.check_readers_target_directory_forms()
        self.check_readers_ln_and_mv_sources()
        self.check_executors_target_directory_forms()
        self.check_executors_mv_sources()
        self.check_executors_ln()
        self.check_executors_outside_the_project()
        self.check_executors_unresolved_home_targets()
        self.check_allowed_temp_forms()

    # ---- readers
    def check_readers_target_directory_forms(self):
        cmds = ["cp --target-directory=src /tmp/x", "cp -tsrc /tmp/x", "cp -t src /tmp/x",
                "cp --target-directory src /tmp/x", "cp -a -t src /tmp/x", "cp -rt src /tmp/x",
                "mv -t src /tmp/x", "mv -tsrc /tmp/x", "mv --target-directory=src /tmp/x",
                "mv --target-directory src /tmp/x",
                "install -t src /tmp/x", "install -tsrc /tmp/x", "install --target-directory=src /tmp/x",
                "install -m 644 -t src/z /tmp/x", "install -D -t src /tmp/x",
                "cp -t src/z /tmp/x /tmp/y"]
        for agent in ALL_READERS:
            for cmd in cmds:
                with self.subTest(agent=agent, denied=cmd):
                    self.assert_denied_cmd(cmd, agent, "src")

    def check_readers_ln_and_mv_sources(self):
        denied_cmds = [("ln -s /tmp/x src/y", "src/y"), ("ln /tmp/x src/y", "src/y"), ("ln -sf /tmp/x src/y", "src/y"),
                       ("ln -s /tmp/x README.md", "README.md"), ("ln -s -t src /tmp/x", "src"),
                       ("ln -st src /tmp/x", "src"), ("ln --target-directory=src -s /tmp/x", "src"),
                       ("mv src/a/app.py /tmp/x", "src/a/app.py"), ("mv README.md /tmp/x", "README.md"),
                       ("mv -t /tmp/t1r7 src/a/app.py", "src/a/app.py"),
                       ("mv /tmp/x src/y", "src/y"), ("cp /tmp/x src/y", "src/y")]
        for agent in ALL_READERS:
            for cmd, names in denied_cmds:
                with self.subTest(agent=agent, denied=cmd):
                    self.assert_denied_cmd(cmd, agent, names)
            # AC23: cp and mv are gone for readers, so their temp forms moved from allowed to denied
            for cmd in ["mv /tmp/t1r7-a /tmp/t1r7-b",
                        "cp -t /tmp/t1r7 /tmp/t1r7-a", "cp --target-directory=/tmp/t1r7 /tmp/t1r7-a",
                        f"cp -t {SCRATCHPAD} /tmp/t1r7-a", "mv -t /tmp/t1r7 /tmp/t1r7-a"]:
                with self.subTest(agent=agent, denied=cmd):
                    self.assert_denied_cmd(cmd, agent)

    # ---- executors
    def check_executors_target_directory_forms(self):
        # DIR is outside every Writes: denied for coder and the language coders; the reason names DIR
        cmds = ["cp --target-directory=src/z /tmp/x", "cp -tsrc/z /tmp/x", "cp -t src/z /tmp/x",
                "cp --target-directory src/z /tmp/x", "cp -a -t src/z /tmp/x",
                "mv -t src/z /tmp/x", "mv -tsrc/z /tmp/x", "mv --target-directory=src/z /tmp/x",
                "install -t src/z /tmp/x", "install -tsrc/z /tmp/x", "install --target-directory=src/z /tmp/x",
                "install -m 644 -t src/z /tmp/x", "cd src/z && cp -t . /tmp/x", "cd src && cp -t z /tmp/x"]
        for agent in CODE_EXECUTORS:
            for cmd in cmds:
                with self.subTest(agent=agent, denied=cmd):
                    self.assert_denied_cmd(cmd, agent, "src/z")
        # test-writer: Tests of a red task only
        for cmd in ["cp -t src/b /tmp/x", "cp --target-directory=src/b /tmp/x", "install -t src/b /tmp/x",
                    "mv -t src/a/tests /tmp/x", "cp -tsrc/a/tests /tmp/x"]:
            with self.subTest(agent="test-writer", denied=cmd):
                self.assert_denied_cmd(cmd, "test-writer", "src/")

    def check_executors_mv_sources(self):
        # a move removes its source: the source is a write
        for agent in CODE_EXECUTORS:
            for cmd, names in [("mv src/z/other.py /tmp/t1r7/o.py", "src/z/other.py"),
                               ("mv src/z/other.py src/a/app.py", "src/z/other.py"),
                               ("mv -t /tmp/t1r7 src/z/other.py", "src/z/other.py"),
                               ("mv -t /tmp/t1r7 src/z/a.py src/z/b.py", "src/z/a.py"),
                               ("mv --target-directory=/tmp/t1r7 src/z/other.py", "src/z/other.py"),
                               ("mv src/a/app.py src/z/app.py", "src/z/app.py"),
                               ("mv README.md /tmp/t1r7/README.md", "README.md")]:
                with self.subTest(agent=agent, denied=cmd):
                    self.assert_denied_cmd(cmd, agent, names)
            for cmd in ["mv src/a/app.py /tmp/t1r7/o.py", "mv -t /tmp/t1r7 src/a/app.py",
                        "mv src/a/lib/util.py /tmp/t1r7/util.py", "mv /tmp/t1r7-a /tmp/t1r7-b"]:
                with self.subTest(agent=agent, allowed=cmd):
                    self.assert_allowed_cmd(cmd, agent)
        for cmd, names in [("mv src/a/tests/test_a.py /tmp/t1r7/t.py", "src/a/tests/test_a.py"),
                           ("mv src/b/app.py /tmp/t1r7/app.py", "src/b/app.py")]:
            with self.subTest(agent="test-writer", denied=cmd):
                self.assert_denied_cmd(cmd, "test-writer", names)
        for cmd in ["mv src/b/tests/test_b.py /tmp/t1r7/t.py", "mv src/b/tests/unit/test_rows.py /tmp/t1r7/t.py"]:
            with self.subTest(agent="test-writer", allowed=cmd):
                self.assert_allowed_cmd(cmd, "test-writer")

    def check_executors_ln(self):
        for agent in CODE_EXECUTORS:
            for cmd, names in [("ln -s /tmp/x src/z/y", "src/z/y"), ("ln /tmp/x src/z/y", "src/z/y"),
                               ("ln -sf /tmp/x src/z/y", "src/z/y"), ("ln -sfn /tmp/x README.md", "README.md"),
                               ("ln -s src/a/app.py src/z/y", "src/z/y"), ("ln -s /tmp/x src/b/app.py", "src/b/app.py"),
                               ("ln -s -t src/z /tmp/x", "src/z"), ("ln -s --target-directory=src/z /tmp/x", "src/z"),
                               ("cd src/z && ln -s /tmp/x y", "src/z/y")]:
                with self.subTest(agent=agent, denied=cmd):
                    self.assert_denied_cmd(cmd, agent, names)
            for cmd in ["ln -s /tmp/x src/a/lib/link", "ln -sf /tmp/x src/a/app.py",
                        "ln -s src/z/other.py /tmp/t1r7/link",       # the link name is the write, not the target
                        "ln -s /tmp/x /tmp/t1r7/link", f"ln -s /tmp/x {SCRATCHPAD}/link"]:
                with self.subTest(agent=agent, allowed=cmd):
                    self.assert_allowed_cmd(cmd, agent)
        for cmd, names in [("ln -s /tmp/x src/b/tests/test_other.py", "src/b/tests/test_other.py"),
                           ("ln -s /tmp/x src/b/app.py", "src/b/app.py")]:
            with self.subTest(agent="test-writer", denied=cmd):
                self.assert_denied_cmd(cmd, "test-writer", names)
        with self.subTest(agent="test-writer", allowed="ln in a red Tests path"):
            self.assert_allowed_cmd("ln -s /tmp/x src/b/tests/test_b.py", "test-writer")

    def check_executors_outside_the_project(self):
        # outside the project and not a temp dir: denied in every way of writing, like Write/Edit
        forms = {"redirect": "echo x > {p}", "append": "echo x >> {p}", "tee": "echo x | tee {p}",
                 "sed -i": "sed -i 's/a/b/' {p}", "cp": "cp /tmp/x {p}", "mv": "mv /tmp/x {p}",
                 "install": "install -m 644 /tmp/x {p}", "touch": "touch {p}", "ln": "ln -s /tmp/x {p}",
                 "cp -t": "cp -t {d} /tmp/x", "cp --target-directory": "cp --target-directory={d} /tmp/x",
                 "mv -t": "mv -t {d} /tmp/x", "install -t": "install -t {d} /tmp/x"}
        outside_dir = str(Path(OUTSIDE).parent)
        for agent in ALL_EXECUTORS:
            for form, tpl in forms.items():
                cmd = tpl.format(p=OUTSIDE, d=outside_dir)
                with self.subTest(agent=agent, form=form, denied=OUTSIDE):
                    self.assert_denied_cmd(cmd, agent, "other")
            for path in ["/etc/t1r7.conf", "/opt/t1r7/y", "/var/lib/t1r7/y", "/home/BadRabbit/.bashrc"]:
                with self.subTest(agent=agent, denied=path):
                    self.assert_denied_cmd(f"cp /tmp/x {path}", agent, path)

    def check_executors_unresolved_home_targets(self):
        cmds = ["echo x > ~/x", "echo x>~/x", "echo x >> ~/x", "echo x | tee ~/x", "cp /tmp/x ~/y", "cp /tmp/x ~",
                "mv /tmp/x ~/y", "touch ~/y", "install /tmp/x ~/y", "ln -s /tmp/x ~/y", "cp -t ~ /tmp/x",
                "cp --target-directory=~/d /tmp/x", "sed -i 's/a/b/' ~/.bashrc",
                "echo x > $HOME/x", "echo x > ${HOME}/x", "echo x > \"$HOME/x\"", "cp /tmp/x $HOME/y",
                "cp /tmp/x \"$HOME/y\"", "cp -t $HOME /tmp/x", "cp --target-directory=${HOME}/d /tmp/x",
                "mv /tmp/x $HOME/y", "touch $HOME/y", "ln -s /tmp/x $HOME/y",
                f"echo x > {HOME}/x", f"cp /tmp/x {HOME}/y"]
        for agent in ALL_EXECUTORS:
            for cmd in cmds:
                with self.subTest(agent=agent, denied=cmd):
                    self.assert_denied_cmd(cmd, agent)

    def check_allowed_temp_forms(self):
        for agent in ALL_EXECUTORS:
            for cmd in ["cp a /tmp/y", "cp /tmp/x /tmp/t1r7/y", "cp -t /tmp/t1r7 src/z/other.py",
                        "cp -t/tmp/t1r7 src/z/other.py", "cp --target-directory=/tmp/t1r7 src/z/other.py",
                        f"cp --target-directory={SCRATCHPAD} /tmp/x", "mv -t /tmp/t1r7 /tmp/t1r7-a",
                        "mv /tmp/t1r7-a /var/tmp/t1r7-b", "install -t /tmp/t1r7 /tmp/x",
                        "install -m 644 /tmp/x /var/tmp/t1r7-y", "ln -s /tmp/x /tmp/t1r7/link",
                        "echo x > /tmp/t1r7/y", f"echo x > {SCRATCHPAD}/notes.md", "cd /tmp && cp x y"]:
                with self.subTest(agent=agent, allowed=cmd):
                    self.assert_allowed_cmd(cmd, agent)

    # ---- guards: pass before and after the change
    def test_bash_write_targets_unaffected_cases(self):
        """Guard: temp targets, reading commands, the main session and projects without a plan keep today's behaviour."""
        for agent in ALL_EXECUTORS:
            for cmd in ["cp a /tmp/y", "cp src/z/other.py /tmp/t1r7/copy.py", "cat src/z/other.py",
                        "grep -rn error src", "ls -la src", "git status --short",
                        "cp /tmp/x /tmp/t1r7/y", "echo x > /tmp/t1r7/y"]:
                with self.subTest(agent=agent, allowed=cmd):
                    self.assert_allowed_cmd(cmd, agent)
        for cmd in ["cp --target-directory=src /tmp/x", "cp -tsrc /tmp/x", "mv -t src /tmp/x", "ln -s /tmp/x src/y",
                    "mv src/z/other.py /tmp/x", "install -t src/z /tmp/x", f"cp /tmp/x {OUTSIDE}",
                    f"echo x > {OUTSIDE}", "echo x > ~/x", "cp /tmp/x $HOME/y"]:
            with self.subTest(who="main session", allowed=cmd):
                self.assert_allowed_cmd(cmd, None)
        plain = plan_project(None)
        for agent in ["coder", "python-coder", "ci-engineer"]:
            for cmd in ["cp --target-directory=src /tmp/x", "cp -tsrc /tmp/x", "mv -t src /tmp/x",
                        "ln -s /tmp/x src/y", "install -t src/z /tmp/x"]:
                with self.subTest(who=agent, plan=False, allowed=cmd):
                    res = bash(cmd, agent=agent, cwd=plain)
                    self.assertFalse(denied(res), f"{agent}: {cmd!r}: {reason(res)}")


class ReadersBashIsCliOnly(unittest.TestCase):
    """AC23: readers read files with Read, Grep and Glob only; their Bash runs the R-marked CLI commands and
    stdin-only filters in pipes."""

    # the health-wait loop of agents/stand-operator.md (bounded, compose with -p, filters on a pipe)
    HEALTH_LOOP = ("timeout 120 nix shell nixpkgs#docker -c sh -c 'until out=$(docker compose -f f.yaml -p shop ps "
                   "--format json); [ \"$(printf \"%s\\n\" \"$out\" | grep -c \"\\\"Service\\\"\")\" -eq 3 ] && "
                   "! printf \"%s\\n\" \"$out\" | grep -Eq \"\\\"Health\\\":\\\"(starting|unhealthy)\\\"\"; "
                   "do sleep 2; done'")
    # no-Nix (P261110 AC3): the same loop run directly under timeout, the way the contract spells it now
    HEALTH_LOOP_DIRECT = HEALTH_LOOP.replace("nix shell nixpkgs#docker -c ", "")

    FILE_READERS = [
        "cat README.md", "cat logs/run.txt", "sed -n 1,20p x", "awk '{print}' x", "ls", "ls logs", "ls -la docs",
        "stat x", "file x", "find . -name x", "find logs -type f",
        "cd logs && tail -n 5 run.txt", "cd logs", "cd /tmp && date",
        "tail -n 50 logs/run.txt", "grep -n x src/a.py", "head x", "head -n 5 logs/run.txt", "jq . data.json",
        "wc -l logs/run.txt", "sort logs/run.txt", "uniq logs/run.txt", "cut -d, -f1 logs/run.txt", "rg -n error logs",
        "git log", "git diff", "git show HEAD",
        "tee /tmp/x", "echo x | tee /tmp/x", "cp a /tmp/b", "touch /tmp/x", "mv /tmp/a /tmp/b",
        "bash -c 'cd ~/.config && cat gh/hosts.yml'", "env -C ~/.config cat gh/hosts.yml", "env cat README.md",
        "bash -c 'cat README.md'", "echo $(cat README.md)", "nix shell nixpkgs#coreutils -c cat README.md",
        "nix develop -c cat README.md", "timeout 5 cat README.md",
        # a filter with a file operand reads that file; a filter reads only its stdin
        "docker logs api | grep error logs/run.txt", "docker logs api | head -n 5 logs/run.txt",
        "docker logs api | jq . data.json", "docker logs api | sort logs/run.txt", "docker logs api | cut -f1 logs/run.txt",
        "docker logs api | wc -l logs/run.txt", "docker logs api | tail -n 5 logs/run.txt",
        "docker logs api | uniq logs/run.txt",
    ]
    CLI_AND_FILTERS = [
        # no-Nix (P261110 AC3): R-marked CLI reads run directly and under timeout; the wrapped forms
        # (wrapper resolution) stay right after the direct forms
        "gh run view 1 --log-failed | tail -n 200",
        "docker compose -p shop logs --tail 200 api",
        "timeout 60 docker compose -p shop ps",
        "timeout 60 docker compose -p shop logs --tail 200 api | tail -n 50",
        "railway logs | head -n 50",
        "docker ps",
        "nix shell nixpkgs#gh -c gh run view 1 --log-failed | tail -n 200",
        "docker compose -p shop logs --tail 200 api | grep -i error",
        "nix shell nixpkgs#railway -c railway logs | head -n 50",
        "docker ps -a | wc -l", "ss -ltn", "docker version",
        "timeout 60 nix shell nixpkgs#docker -c docker compose -p shop ps",
        "nix develop -c docker ps",
        "docker logs api 2>&1 | grep -i error | head -n 5",
        "docker logs api | sort | uniq -c | sort -rn | head -n 10",
        "docker logs api | cut -d' ' -f1 | tr a-z A-Z",
        "gcloud logging read 'severity>=ERROR' --limit 50 | jq .textPayload",
        "docker ps -a | grep -c shop",
        "date", "echo ok", "printf 'x\\n'", "test 1 -eq 1", "true", "sleep 1",
        "docker logs api > /tmp/t1r8-api.log",
    ]

    @classmethod
    def setUpClass(cls):
        cls.root = git_repo("feature/t1r8")
        (cls.root / "src").mkdir()
        (cls.root / "src" / "a.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "src/a.py"], cwd=cls.root, check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "a"],
                       cwd=cls.root, check=True, capture_output=True)

    def run_cmd(self, cmd, agent):
        return bash(cmd, agent=agent, cwd=self.root)

    def test_readers_bash_is_cli_only(self):
        for agent in ALL_READERS:
            for cmd in self.FILE_READERS:
                with self.subTest(agent=agent, denied=cmd):
                    res = self.run_cmd(cmd, agent)
                    self.assertTrue(denied(res), f"{agent}: {cmd!r} was allowed")
                    self.assertTrue(reason(res).strip(), f"{agent}: {cmd!r}: an empty reason")
            for cmd in self.CLI_AND_FILTERS:
                with self.subTest(agent=agent, allowed=cmd):
                    res = self.run_cmd(cmd, agent)
                    self.assertFalse(denied(res), f"{agent}: {cmd!r}: {reason(res)}")
        # the stand-operator health-wait loop of its contract stays allowed (it also has a compose without -p: denied)
        with self.subTest(agent="stand-operator", allowed="health-wait loop"):
            res = self.run_cmd(self.HEALTH_LOOP, "stand-operator")
            self.assertFalse(denied(res), reason(res))
        with self.subTest(agent="stand-operator", denied="health-wait loop without -p"):
            self.assertTrue(denied(self.run_cmd(self.HEALTH_LOOP.replace("-p shop ", ""), "stand-operator")))
        # no-Nix (P261110 AC3): the direct loop (no nix wrapper) is allowed, and still denied without -p
        with self.subTest(agent="stand-operator", allowed="direct health-wait loop"):
            res = self.run_cmd(self.HEALTH_LOOP_DIRECT, "stand-operator")
            self.assertFalse(denied(res), reason(res))
        with self.subTest(agent="stand-operator", denied="direct health-wait loop without -p"):
            self.assertTrue(denied(self.run_cmd(self.HEALTH_LOOP_DIRECT.replace("-p shop ", ""), "stand-operator")))
        # the janitor keeps git for its tracked-file gate: ls-files and status, nothing else of git
        for cmd in ["git ls-files src/a.py", "git ls-files --error-unmatch src/a.py", "git status --porcelain"]:
            with self.subTest(agent="janitor", allowed=cmd):
                res = self.run_cmd(cmd, "janitor")
                self.assertFalse(denied(res), f"{cmd}: {reason(res)}")
        for cmd in ["git log", "git diff", "git show HEAD", "git ls-files src/a.py | head -n 1 src/a.py",
                    "git -c core.pager=sh ls-files src/a.py"]:
            with self.subTest(agent="janitor", denied=cmd):
                self.assertTrue(denied(self.run_cmd(cmd, "janitor")), f"{cmd!r} was allowed")
        for agent in ["deploy-error-reader", "log-collector", "stand-operator"]:
            for cmd in ["git ls-files src/a.py", "git status --porcelain"]:
                with self.subTest(agent=agent, denied=cmd):
                    self.assertTrue(denied(self.run_cmd(cmd, agent)), f"{agent}: {cmd!r} was allowed")

    def test_readers_run_cli_reads_directly_and_wrapped(self):
        """no-Nix (P261110 AC3): the R-marked CLI reads run bare and under timeout for every reader; the same
        reads hidden in `nix shell ... -c` / `nix develop -c` are resolved and judged the same way, not newly allowed."""
        direct = ["gh run view 1 --log-failed | tail -n 200", "docker compose -p shop logs --tail 200 api",
                  "timeout 60 gh run list", "timeout 60 docker compose -p shop ps"]
        for agent in ALL_READERS:
            for cmd in direct:
                with self.subTest(agent=agent, allowed=cmd):
                    res = self.run_cmd(cmd, agent)
                    self.assertFalse(denied(res), f"{agent}: {cmd!r}: {reason(res)}")
            for cmd in ["nix shell nixpkgs#gh -c gh run view 1 --log-failed | tail -n 200",
                        "nix develop -c docker compose -p shop logs --tail 200 api"]:
                with self.subTest(agent=agent, allowed_wrapped=cmd):
                    res = self.run_cmd(cmd, agent)
                    self.assertFalse(denied(res), f"{agent}: {cmd!r}: {reason(res)}")
            # nothing new is allowed through a wrapper
            for cmd in ["nix shell nixpkgs#coreutils -c cat README.md", "nix develop -c cat README.md",
                        "timeout 5 nix develop -c cat README.md"]:
                with self.subTest(agent=agent, denied_wrapped=cmd):
                    self.assertTrue(denied(self.run_cmd(cmd, agent)), f"{agent}: {cmd!r} was allowed")
            # no-Nix (P261110 AC4): a reader's deny reason does not mention nix
            with self.subTest(agent=agent, reason_has_no_nix=True):
                res = self.run_cmd("cat README.md", agent)
                self.assertNotIn("nix", reason(res).lower(), f"{agent}: {reason(res)!r}")

    def test_readers_bash_cli_only_does_not_limit_other_agents(self):
        """Guard: the main session and executors keep cat, ls, sed, find, cd, git, tee, cp and touch."""
        cmds = ["cat README.md", "ls logs", "sed -n 1,20p x", "awk '{print}' x", "stat x", "find . -name x",
                "cd logs && tail -n 5 run.txt", "grep -n x src/a.py", "git log", "git status", "tee /tmp/t1r8-x < /dev/null",
                "cp a /tmp/t1r8-b", "touch /tmp/t1r8-x", "jq . data.json"]
        for agent in [None, "coder", "python-coder", "ci-engineer", "deploy-engineer", "refactorer", "test-writer"]:
            for cmd in cmds:
                with self.subTest(agent=agent, cmd=cmd):
                    res = self.run_cmd(cmd, agent)
                    self.assertFalse(denied(res), f"{agent}: {cmd!r}: {reason(res)}")


if __name__ == "__main__":
    unittest.main()
