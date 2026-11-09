import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import call, denied


def read(path, tool="Read"):
    key = "path" if tool == "Grep" else "file_path"
    return call("guard_read", tool, {key: path, "pattern": "x"})


class TestRead(unittest.TestCase):
    def test_denied(self):
        for p in [".env", "/repo/api/.env.local", ".env.production", "certs/tls.key", "ca.pem",
                  "/home/a/.ssh/id_ed25519", "/home/a/.config/sops/age/keys.txt", "client.p12"]:
            with self.subTest(p=p):
                self.assertTrue(denied(read(p)), p)
        self.assertTrue(denied(read(".env", tool="Grep")))

    def test_allowed(self):
        for p in [".env.example", ".env.sample", "/home/a/.ssh/id_ed25519.pub", "public.pem", "jwt-public.pem",
                  "src/keys.py", "src/app/config.py", ".envrc", "docs/keys.md"]:
            with self.subTest(p=p):
                self.assertFalse(denied(read(p)), p)


READERS = ["deploy-error-reader", "log-collector", "stand-operator", "janitor"]
SCRATCHPAD = "/tmp/claude-1000/-home-user-project/0a1b2c3d-0000-4000-8000-000000000000/scratchpad"


def _non_tmp_base() -> Path:
    """A base directory that is not a temp dir, so project and HOME paths never look like /tmp."""
    for cand in (Path("/dev/shm"), Path.home(), Path(__file__).resolve().parent):
        if cand.is_dir() and not str(cand).startswith(("/tmp", "/var/tmp")):
            try:
                tempfile.TemporaryFile(dir=cand).close()
            except OSError:
                continue
            return cand
    raise RuntimeError("no writable directory outside /tmp for the project and HOME")


class TestReaderRoots(unittest.TestCase):
    def setUp(self):
        base = Path(tempfile.mkdtemp(prefix="t1r8read-", dir=_non_tmp_base()))
        self.addCleanup(shutil.rmtree, base, True)
        self.project = base / "project"
        self.home = base / "home"
        self.project.mkdir()
        self.home.mkdir()
        self.env = {"HOME": str(self.home)}

    def run_tool(self, agent, tool, path=None):
        key = "path" if tool in ("Grep", "Glob") else "file_path"
        ti = {"pattern": "x"}
        if path is not None:
            ti[key] = path
        return call("guard_read", tool, ti, agent=agent, cwd=self.project, project=self.project, env=self.env)

    # AC23: readers reach only the project, temp dirs and /nix/store with Read, Grep and Glob
    def test_reader_read_tools_stay_inside_allowed_roots(self):
        home = str(self.home)
        outside = {
            "Read": ["~/.config/gh/hosts.yml", "~/.docker/config.json", "/etc/passwd",
                     f"{self.project}/../outside.txt", f"{home}/.config/gh/hosts.yml",
                     f"{home}/.docker/config.json", "../outside.txt"],
            "Grep": ["~", "/home", home],
            "Glob": ["/etc", "~", home],
        }
        inside = {
            "Read": [f"{self.project}/README.md", "README.md", "/tmp/x.log", "/var/tmp/x.log",
                     f"{SCRATCHPAD}/notes.md", "/nix/store/abc-x/log"],
            "Grep": [str(self.project), f"{self.project}/src", "/tmp", SCRATCHPAD, "/nix/store/abc-x"],
            "Glob": [str(self.project), f"{self.project}/src", "/tmp", SCRATCHPAD, "/nix/store/abc-x"],
        }
        for agent in READERS:
            for tool, paths in outside.items():
                for path in paths:
                    with self.subTest(agent=agent, tool=tool, path=path, expect="denied"):
                        res = self.run_tool(agent, tool, path)
                        self.assertTrue(denied(res), f"{agent} {tool} {path}: {res}")
            for tool, paths in inside.items():
                for path in paths:
                    with self.subTest(agent=agent, tool=tool, path=path, expect="allowed"):
                        res = self.run_tool(agent, tool, path)
                        self.assertFalse(denied(res), f"{agent} {tool} {path}: {res}")
            for tool in ("Grep", "Glob"):
                with self.subTest(agent=agent, tool=tool, path=None, expect="allowed"):
                    res = self.run_tool(agent, tool)
                    self.assertFalse(denied(res), f"{agent} {tool} without path: {res}")

    # AC23: the roots limit readers only; the main session and executors read as before
    def test_reader_roots_do_not_limit_main_session_and_coder(self):
        for agent in (None, "coder"):
            for tool in ("Read", "Grep", "Glob"):
                for path in (f"{self.project}/../outside.txt", "/etc/passwd", "/etc"):
                    with self.subTest(agent=agent, tool=tool, path=path):
                        self.assertFalse(denied(self.run_tool(agent, tool, path)))


if __name__ == "__main__":
    unittest.main()
