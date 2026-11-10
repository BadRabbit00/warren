"""P261110-2 T1: the janitor's Bash gate lists the project (ls, find, stat, readlink, du) and runs
`docker volume inspect NAME`; everything else stays refused (decisions D1, D2)."""
import unittest
from pathlib import Path

from helpers import call, denied, git_repo, reason


def bash(cmd, **kw):
    return call("guard_bash", "Bash", {"command": cmd}, **kw)


def listing_project() -> Path:
    """A git repo shaped like a real project: docs/temp with leftovers and a `result` symlink."""
    d = git_repo("feature/p261110-2-listing")
    (d / "docs" / "temp").mkdir(parents=True)
    (d / "docs" / "temp" / "trace-1.log").write_text("x\n")
    (d / "docs" / "temp" / "curl-out.json").write_text("{}\n")
    (d / "notes.md").write_text("notes\n")
    (d / "result").symlink_to("docs/temp")
    (d / "result-doc").symlink_to("notes.md")
    return d


class JanitorListing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = listing_project()

    def run_as(self, agent, cmd):
        return bash(cmd, agent=agent, cwd=self.root)

    def assertAllowed(self, agent, cmds):
        for cmd in cmds:
            with self.subTest(agent=agent, cmd=cmd):
                res = self.run_as(agent, cmd)
                self.assertFalse(denied(res), f"{cmd}: {reason(res)}")

    def assertRefused(self, agent, cmds):
        for cmd in cmds:
            with self.subTest(agent=agent, cmd=cmd):
                self.assertTrue(denied(self.run_as(agent, cmd)), f"{cmd!r} was allowed")

    # AC1 (D1): read-only listing with paths inside the project root
    def test_janitor_lists_inside_project(self):
        self.assertAllowed("janitor", [
            "ls -la docs/temp",
            "ls",
            "find . -maxdepth 2 -type l -name 'result*'",
            "find docs/temp -type f",
            "stat docs/temp",
            "readlink result",
            "du -sh docs/temp",
        ])

    # AC2 (D1): any path outside the project root, or built from ~, variables or substitutions, is refused
    def test_janitor_listing_outside_project_refused(self):
        self.assertRefused("janitor", [
            "ls /etc",
            "ls ..",
            "find / -name x",
            "du -sh ~",
            "ls $HOME",
            'stat "$(pwd)/.."',
        ])

    # AC3 (D1): find actions that run commands or write files are refused
    def test_janitor_find_actions_refused(self):
        self.assertRefused("janitor", [
            "find . -exec rm {} \\;",
            "find . -delete",
            "find . -execdir ls \\;",
            "find . -ok rm {} \\;",
            "find . -fprint out.txt",
        ])

    # AC4 (D2): `docker volume inspect NAME` yes; container inspect (prints Env) and variable names no
    def test_janitor_docker_inspect(self):
        self.assertAllowed("janitor", ["docker volume inspect shop_pg"])
        self.assertRefused("janitor", [
            "docker inspect p261109-test-pg",
            "docker container inspect p261109-test-pg",
            "docker volume inspect $V",
        ])

    # AC5 (D1): listing is the janitor's alone; the other read-only agents stay as they were
    def test_listing_stays_janitor_only(self):
        for agent in ["log-collector", "deploy-error-reader", "stand-operator"]:
            self.assertRefused(agent, ["ls docs/temp"])

    # AC7 (D1): leading find options do not hide a path; du cannot read paths from a file
    def test_janitor_listing_option_tricks(self):
        self.assertRefused("janitor", [
            "find -L /etc -name x",
            "find -P / -type f",
            "find -H -D tree /etc",
            "find -O3 /etc",
            "du --files0-from=/etc/hosts",
            "du --files0-from /etc/hosts",
        ])
        self.assertAllowed("janitor", ["find -L . -name x"])


if __name__ == "__main__":
    unittest.main()
