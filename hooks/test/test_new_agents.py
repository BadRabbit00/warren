"""P261110-4 T1: write scopes of metrics-writer, observability-engineer and the temp-only agents."""
import unittest

from helpers import call, denied, reason
from test_guard_write import project, write

METRICS_PLAN = """# Plan

### T1 — order metrics
- **Status:** metrics
- **Writes (exclusive):** `src/app/metrics.py`
- **Tests (test-writer):** `tests/test_metrics.py`, `src/app/metrics_test.go`

### T2 — user service
- **Status:** green
- **Writes (exclusive):** `src/app/user_service.py`
- **Tests (test-writer):** `tests/test_user.py`
"""

METRICS_ONLY_PLAN = """# Plan

### T1 — order metrics
- **Status:** `metrics`
- **Writes (exclusive):** `src/app/metrics.py`
- **Tests (test-writer):** `tests/test_metrics.py`
"""

NO_METRICS_PLAN = """# Plan

### T1 — order service
- **Status:** green
- **Writes (exclusive):** `src/app/order_service.py`
- **Tests (test-writer):** `tests/test_order.py`

### T2 — user service
- **Status:** red
- **Writes (exclusive):** `src/app/user_service.py`
- **Tests (test-writer):** `tests/test_user.py`
"""

OBS_PLAN = """# Plan

### T1 — observability stack
- **Status:** green
- **Writes (exclusive):** `deploy/prometheus/prometheus.yml`, `deploy/grafana/**`
- **Tests (test-writer):** `tests/test_obs.py`

### T2 — order service
- **Status:** red
- **Writes (exclusive):** `src/app/order_service.py`
- **Tests (test-writer):** `tests/test_order.py`
"""

TEMP_ONLY_AGENTS = ["bug-reproducer", "repro-runner", "root-cause-analyst", "optimizer"]


def bash(cmd, agent, root):
    return call("guard_bash", "Bash", {"command": cmd}, agent=agent, cwd=root, project=root)


class TestMetricsWriter(unittest.TestCase):
    def test_metrics_writer_scope(self):
        r = project(METRICS_PLAN)
        for tool in ("Write", "Edit"):
            with self.subTest(tool=tool):
                res = write(r / "src/app/metrics.py", "metrics-writer", r, tool=tool)   # T1 is in `metrics`
                self.assertFalse(denied(res), reason(res))
        res = write(r / "src/app/user_service.py", "metrics-writer", r)                 # T2 is green, not metrics
        self.assertTrue(denied(res))
        self.assertIn("outside the write set", reason(res))
        self.assertIn("T1", reason(res))
        self.assertTrue(denied(write(r / "src/app/other.py", "metrics-writer", r)))     # in no write set
        # Bash redirection follows the same write set
        self.assertFalse(denied(bash("echo x > src/app/metrics.py", "metrics-writer", r)))
        self.assertTrue(denied(bash("echo x > src/app/user_service.py", "metrics-writer", r)))

    def test_metrics_writer_without_metrics_task(self):
        r = project(NO_METRICS_PLAN)
        res = write(r / "src/app/order_service.py", "metrics-writer", r)
        self.assertTrue(denied(res))
        self.assertIn("No task in .plan/PLAN.md has status", reason(res))

    def test_metrics_writer_never_writes_tests(self):
        r = project(METRICS_PLAN)
        for p in ["tests/test_metrics.py", "src/app/metrics_test.go"]:                  # listed in Tests of the `metrics` task
            with self.subTest(denied=p):
                res = write(r / p, "metrics-writer", r)
                self.assertTrue(denied(res), p)
                self.assertIn("never change them", reason(res))
        self.assertTrue(denied(write(r / "tests/test_other.py", "metrics-writer", r)))
        self.assertFalse(denied(write(r / "src/app/metrics.py", "metrics-writer", r)))  # guard: its own Writes stay open

    def test_metrics_status_is_metrics_writer_only(self):
        r = project(METRICS_ONLY_PLAN)
        for agent in ["coder", "refactorer", "log-writer", "deploy-engineer", "ci-engineer"]:
            with self.subTest(agent=agent):
                res = write(r / "src/app/metrics.py", agent, r)
                self.assertTrue(denied(res), agent)
                self.assertIn("No task in .plan/PLAN.md has status", reason(res))
        # the file is not unwritable for everyone: only the metrics-writer gets it, and only that file
        self.assertFalse(denied(write(r / "src/app/metrics.py", "metrics-writer", r)))
        self.assertTrue(denied(write(r / "src/app/other.py", "metrics-writer", r)))

    def test_metrics_task_does_not_widen_coder_scope_next_to_a_green_task(self):
        r = project(METRICS_PLAN)
        self.assertFalse(denied(write(r / "src/app/user_service.py", "coder", r)))      # T2 green
        res = write(r / "src/app/metrics.py", "coder", r)                               # T1 metrics
        self.assertTrue(denied(res))
        self.assertIn("outside the write set of T2", reason(res))


class TestObservabilityEngineer(unittest.TestCase):
    def test_observability_engineer_scope(self):
        r = project(OBS_PLAN)
        for p in ["deploy/prometheus/prometheus.yml", "deploy/grafana/dashboards/orders.json",
                  "deploy/grafana/provisioning/datasources/prom.yml"]:
            with self.subTest(allowed=p):
                res = write(r / p, "observability-engineer", r)
                self.assertFalse(denied(res), f"{p}: {reason(res)}")
        res = write(r / "src/app/x.py", "observability-engineer", r)
        self.assertTrue(denied(res))
        self.assertIn("outside the write set", reason(res))
        self.assertIn("T1", reason(res))
        self.assertTrue(denied(write(r / "deploy/alertmanager/alertmanager.yml", "observability-engineer", r)))  # not listed
        self.assertTrue(denied(write(r / "src/app/order_service.py", "observability-engineer", r)))              # red task
        # Bash redirection follows the same write set
        self.assertFalse(denied(bash("echo x > deploy/prometheus/prometheus.yml", "observability-engineer", r)))
        self.assertTrue(denied(bash("echo x > src/app/x.py", "observability-engineer", r)))

    def test_observability_engineer_never_writes_tests(self):
        r = project(OBS_PLAN)
        res = write(r / "tests/test_obs.py", "observability-engineer", r)               # listed in Tests of the green task
        self.assertTrue(denied(res))
        self.assertIn("never change them", reason(res))
        self.assertTrue(denied(write(r / "tests/test_other.py", "observability-engineer", r)))

    def test_observability_engineer_without_green_task(self):
        r = project(METRICS_ONLY_PLAN)
        res = write(r / "deploy/prometheus/prometheus.yml", "observability-engineer", r)
        self.assertTrue(denied(res))
        self.assertIn("No task in .plan/PLAN.md has status", reason(res))


class TestTempOnlyAgents(unittest.TestCase):
    def test_temp_only_agents(self):
        r = project(NO_METRICS_PLAN)
        for agent in TEMP_ONLY_AGENTS:
            with self.subTest(agent=agent, tool="Write", allowed="/tmp/repro/run.sh"):
                res = write("/tmp/repro/run.sh", agent, r)
                self.assertFalse(denied(res), f"{agent}: {reason(res)}")
            for p in ["src/app/order_service.py", "docs/temp/x.md", "src/app/user_service.py"]:   # even a Writes file of a green task
                with self.subTest(agent=agent, tool="Write", denied=p):
                    res = write(r / p, agent, r)
                    self.assertTrue(denied(res), f"{agent}: {p} was allowed")
                    self.assertIn("temp files", reason(res))
            with self.subTest(agent=agent, tool="Edit", denied="src/app/order_service.py"):
                self.assertTrue(denied(write(r / "src/app/order_service.py", agent, r, tool="Edit")))
            with self.subTest(agent=agent, tool="Bash", denied="src/app/x.py"):
                res = bash("echo x > src/app/x.py", agent, r)
                self.assertTrue(denied(res), f"{agent}: Bash write into the project was allowed")
                self.assertIn("src/app/x.py", reason(res))
            with self.subTest(agent=agent, tool="Bash", allowed="/tmp/repro/out.txt"):
                res = bash("echo x > /tmp/repro/out.txt", agent, r)
                self.assertFalse(denied(res), f"{agent}: {reason(res)}")

    def test_temp_only_agents_are_not_widened_by_any_task_status(self):
        for plan in (METRICS_PLAN, OBS_PLAN):
            r = project(plan)
            for agent in TEMP_ONLY_AGENTS:
                for p in ["src/app/metrics.py", "deploy/prometheus/prometheus.yml"]:
                    with self.subTest(agent=agent, p=p):
                        self.assertTrue(denied(write(r / p, agent, r)), f"{agent}: {p}")


class TestLanguageReviewer(unittest.TestCase):
    """T8 AC1: language-reviewer reads and reports; it writes no project file, through any tool or Bash."""
    AGENT = "language-reviewer"
    PATHS = ["src/app/user_service.py",      # Writes of a green task: still closed
             "src/app/new_module.py", "tests/test_user.py", "docs/API.md", "README.md", ".plan/PLAN.md",
             "flake.nix", "notes.md"]
    BASH_FORMS = {
        "redirect": "echo x > {p}",
        "append": "echo x >> {p}",
        "tee": "tee {p} < /tmp/src.txt",
        "touch": "touch {p}",
        "cp": "cp /tmp/src.txt {p}",
        "sed -i": "sed -i 's/a/b/' {p}",
        "heredoc": "cat > {p} <<'EOF'\nx\nEOF",
    }

    def test_language_reviewer_is_read_only(self):
        for plan in (METRICS_PLAN, None):
            r = project(plan)
            for p in self.PATHS:
                for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
                    with self.subTest(plan=plan is not None, p=p, tool=tool):
                        res = write(r / p, self.AGENT, r, tool=tool)
                        self.assertTrue(denied(res), f"{self.AGENT} {tool} {p} was allowed")
                for form, tpl in self.BASH_FORMS.items():
                    with self.subTest(plan=plan is not None, p=p, bash=form):
                        cmd = tpl.format(p=p)
                        res = bash(cmd, self.AGENT, r)
                        self.assertTrue(denied(res), f"{self.AGENT} Bash {cmd!r} was allowed")
                        self.assertIn(p, reason(res))
            # a path outside the project and outside the temp dirs is refused as well
            with self.subTest(plan=plan is not None, outside="/etc/hosts"):
                self.assertTrue(denied(write("/etc/hosts", self.AGENT, r)))
                self.assertTrue(denied(bash("echo x > /etc/hosts", self.AGENT, r)))
            # temp dirs stay free for scratch output
            with self.subTest(plan=plan is not None, allowed="/tmp via Bash"):
                res = bash("echo x > /tmp/language-review/out.txt", self.AGENT, r)
                self.assertFalse(denied(res), reason(res))

    UNRESOLVED_BASH_FORMS = {
        "variable, quoted": 'F={p}; echo x > "$F"',
        "variable, bare": "F={p}; echo x > $F",
        "command substitution": "echo x > $(printf {p})",
    }

    def test_language_reviewer_unresolved_bash_targets_are_refused(self):
        for plan in (METRICS_PLAN, None):
            r = project(plan)
            for p in self.PATHS:
                for form, tpl in self.UNRESOLVED_BASH_FORMS.items():
                    with self.subTest(plan=plan is not None, p=p, bash=form):
                        cmd = tpl.format(p=p)
                        res = bash(cmd, self.AGENT, r)
                        self.assertTrue(denied(res), f"{self.AGENT} Bash {cmd!r} was allowed")
            with self.subTest(plan=plan is not None, bash="cd into a variable directory"):
                cmd = 'cd "$D" && echo x > a.py'
                res = bash(cmd, self.AGENT, r)
                self.assertTrue(denied(res), f"{self.AGENT} Bash {cmd!r} was allowed")
            # a literal path under /tmp stays free for scratch output
            with self.subTest(plan=plan is not None, allowed="/tmp via Bash"):
                res = bash("echo x > /tmp/language-review/out.txt", self.AGENT, r)
                self.assertFalse(denied(res), reason(res))


if __name__ == "__main__":
    unittest.main()
