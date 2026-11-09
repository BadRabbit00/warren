import tempfile
import unittest
from pathlib import Path

from helpers import call, denied, reason

PLAN = """# Plan

### T1 — order status filter
- **Status:** green
- **Writes (exclusive):** `src/orders/app/services/order_service.py`, `src/orders/app/repositories/order_repo.py`
- **Tests (test-writer):** `src/orders/test/services/test_order_service.py`

### T2 — order export
- **Status:** red
- **Writes (exclusive):** `src/orders/app/services/export_service.py`
- **Tests (test-writer):** `src/orders/test/services/test_export_*.py`

### T3 — notifications
- **Status:** todo
- **Writes (exclusive):** `src/notify/**`
- **Tests (test-writer):** `src/notify/test/**`
"""


def project(plan: str | None = PLAN) -> Path:
    d = Path(tempfile.mkdtemp(prefix="brhook-proj-"))
    if plan is not None:
        (d / ".plan").mkdir()
        (d / ".plan" / "PLAN.md").write_text(plan)
    return d


def write(path, agent=None, root=None, tool="Write"):
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    return call("guard_write", tool, {key: str(path), "content": "x"}, agent=agent, cwd=root, project=root)


class TestBoundaryWithoutPlan(unittest.TestCase):
    def setUp(self):
        self.root = project(None)

    def test_coder_never_writes_tests(self):
        for agent in ["coder", "refactorer", "build-fixer"]:
            for p in ["test/test_a.py", "src/api/test/conftest.py", "web/test/App.test.tsx"]:
                with self.subTest(agent=agent, p=p):
                    self.assertTrue(denied(write(self.root / p, agent, self.root)))

    def test_native_test_locations_are_tests(self):
        for p in ["crates/core/tests/api.rs", "app/integration_test/login_test.dart", "internal/order/order_service_test.go",
                  "web/src/OrderTable.test.tsx", "web/src/__tests__/x.ts", "pkg/test_utils_x.py", "src/orders/app/conftest.py",
                  "web/e2e/login.spec.ts", "internal/parse/testdata/in.json"]:
            with self.subTest(p=p):
                self.assertTrue(denied(write(self.root / p, "coder", self.root)), p)
                self.assertFalse(denied(write(self.root / p, "test-writer", self.root)), p)

    def test_coder_writes_code(self):
        self.assertFalse(denied(write(self.root / "src/api/app/main.py", "coder", self.root)))
        self.assertFalse(denied(write(self.root / "src/api/testing_utils.py", "coder", self.root)))

    def test_test_writer_only_tests(self):
        self.assertFalse(denied(write(self.root / "src/api/test/test_x.py", "test-writer", self.root)))
        self.assertTrue(denied(write(self.root / "src/api/app/x.py", "test-writer", self.root)))

    def test_main_thread_free_without_plan(self):
        self.assertFalse(denied(write(self.root / "src/app.py", None, self.root)))

    def test_subagent_outside_project(self):
        self.assertTrue(denied(write("/etc/hosts", "coder", self.root)))
        self.assertTrue(denied(write(Path.home() / ".claude/settings.json", "coder", self.root)))
        self.assertFalse(denied(write("/tmp/scratch.txt", "coder", self.root)))

    def test_quality_configs_protected(self):
        for p in [".eslintrc.json", "eslint.config.js", "ruff.toml", ".golangci.yml", "web/biome.json",
                  "mypy.ini", ".coveragerc", "rustfmt.toml", ".pre-commit-config.yaml"]:
            for agent in ["coder", "build-fixer", "test-writer"]:
                with self.subTest(p=p, agent=agent):
                    self.assertTrue(denied(write(self.root / p, agent, self.root)))
        self.assertFalse(denied(write(self.root / "ruff.toml", None, self.root)))      # the human session may
        self.assertFalse(denied(write(self.root / "tsconfig.json", "coder", self.root)))

    def test_notebook(self):
        self.assertTrue(denied(write(self.root / "test/nb.ipynb", "coder", self.root, tool="NotebookEdit")))


class TestPlanScopes(unittest.TestCase):
    def setUp(self):
        self.root = project()

    def test_coder_limited_to_green_tasks(self):
        r = self.root
        self.assertFalse(denied(write(r / "src/orders/app/services/order_service.py", "coder", r)))
        self.assertFalse(denied(write(r / "src/orders/app/repositories/order_repo.py", "coder", r, tool="Edit")))
        res = write(r / "src/orders/app/services/export_service.py", "coder", r)   # T2 is red, not green
        self.assertTrue(denied(res))
        self.assertIn("T1", reason(res))
        self.assertTrue(denied(write(r / "src/notify/x.py", "coder", r)))          # T3 todo

    def test_test_writer_limited_to_red_tasks(self):
        r = self.root
        self.assertFalse(denied(write(r / "src/orders/test/services/test_export_csv.py", "test-writer", r)))
        self.assertTrue(denied(write(r / "src/orders/test/services/test_order_service.py", "test-writer", r)))

    def test_refactorer_without_refactor_task(self):
        res = write(self.root / "src/orders/app/services/order_service.py", "refactorer", self.root)
        self.assertTrue(denied(res))
        self.assertIn("No task", reason(res))

    def test_build_fixer_not_limited_by_plan(self):
        self.assertFalse(denied(write(self.root / "flake.nix", "build-fixer", self.root)))

    def test_main_thread_docs_and_plan_only(self):
        r = self.root
        for p in ["docs/GENERAL.md", "docs/slides/arch.html", ".plan/PLAN.md", "README.md", "CLAUDE.md"]:
            with self.subTest(p=p):
                self.assertFalse(denied(write(r / p, None, r)))
        res = write(r / "src/orders/app/services/order_service.py", None, r)
        self.assertTrue(denied(res))
        self.assertIn("/output-style default", reason(res))

    def test_presenter_scope(self):
        self.assertFalse(denied(write(self.root / "docs/slides/a.html", "presenter", self.root)))
        self.assertTrue(denied(write(self.root / "docs/API.md", "presenter", self.root)))

    def test_ui_verifier_writes_only_tmp(self):
        self.assertTrue(denied(write(self.root / "src/web/check.mjs", "ui-verifier", self.root)))
        self.assertFalse(denied(write("/tmp/ui-verifier/T7/check.mjs", "ui-verifier", self.root)))

    def test_relative_path(self):
        self.assertTrue(denied(write("src/notify/x.py", "coder", self.root)))


NEW_EXECUTORS = ["python-coder", "go-coder", "ts-coder", "rust-coder", "deploy-engineer", "ci-engineer"]
LANGUAGE_CODERS = ["python-coder", "go-coder", "ts-coder", "rust-coder"]
SCRATCHPAD = "/tmp/claude-1000/-home-user-project/0a1b2c3d-0000-4000-8000-000000000000/scratchpad"

STATUS_PLAN = """# Plan

### T1 — backticked status
- **Status:** `red`
- **Writes (exclusive):** `src/a/app.py`
- **Tests (test-writer):** `src/a/tests/test_a.py`

### T2 — status with a note
- **Status:** red (round 2)
- **Writes (exclusive):** `src/b/app.py`
- **Tests (test-writer):** `src/b/tests/test_b.py`

### T3 — backticks and a note
- **Status:** `green` — second pass
- **Writes (exclusive):** `src/c/app.py`
- **Tests (test-writer):** `src/c/tests/test_c.py`

### T4 — not started
- **Status:** `todo`
- **Writes (exclusive):** `src/d/app.py`
- **Tests (test-writer):** `src/d/tests/test_d.py`
"""

UNION_PLAN = """# Plan

### T1 — orders
- **Status:** red
- **Writes (exclusive):** `src/orders/app/service.py`
- **Tests (test-writer):** `src/orders/tests/test_service.py`, `src/orders/tests/test_repo.py`

### T2 — export, status in backticks
- **Status:** `red`
- **Writes (exclusive):** `src/export/app/csv.py`
- **Tests (test-writer):** `src/export/tests/**`

### T3 — notifications, second round
- **Status:** red (round 2)
- **Writes (exclusive):** `src/notify/app/mail.py`
- **Tests (test-writer):** `src/notify/tests/test_mail.py`

### T4 — already green
- **Status:** green
- **Writes (exclusive):** `src/billing/app/pay.py`
- **Tests (test-writer):** `src/billing/tests/test_pay.py`

### T5 — not started
- **Status:** todo
- **Writes (exclusive):** `src/audit/app/log.py`
- **Tests (test-writer):** `src/audit/tests/test_log.py`
"""

EXPLICIT_PLAN = """# Plan

### T1 — dev stand
- **Status:** green
- **Writes (exclusive):** `src/stand/run.py`, `e2e/dev-stand.yml`, `scripts/seed/tests/x.py`
- **Tests (test-writer):** `src/stand/tests/test_run.py`

### T2 — export
- **Status:** red
- **Writes (exclusive):** `e2e/export-stand.yml`
- **Tests (test-writer):** `src/export/tests/test_export.py`
"""

CONFIG_PLAN = """# Plan

### T1 — CI and quality gates
- **Status:** green
- **Writes (exclusive):** `.github/**`, `ruff.toml`, `.golangci.yml`, `eslint.config.js`, `mypy.ini`, `.pre-commit-config.yaml`, `.coveragerc`, `web/biome.json`, `src/app/main.py`
- **Tests (test-writer):** `src/app/tests/test_main.py`
"""

ALL_STEPS_PLAN = """# Plan

### T1 — code
- **Status:** green
- **Writes (exclusive):** `src/a/app.py`
- **Tests (test-writer):** `src/a/tests/test_a.py`

### T2 — tests
- **Status:** red
- **Writes (exclusive):** `src/b/app.py`
- **Tests (test-writer):** `src/b/tests/test_b.py`

### T3 — cleanup
- **Status:** refactor
- **Writes (exclusive):** `src/c/app.py`
- **Tests (test-writer):** `src/c/tests/test_c.py`
"""

NO_ACTIVE_PLAN = """# Plan

### T1 — later
- **Status:** todo
- **Writes (exclusive):** `src/a/app.py`
- **Tests (test-writer):** `src/a/tests/test_a.py`
"""


class TestPlanStatusAndUnion(unittest.TestCase):
    def test_status_tolerates_backticks_and_notes(self):
        r = project(STATUS_PLAN)
        # `red` and red (round 2) both mean red: test-writer gets both Tests, not the Writes
        self.assertFalse(denied(write(r / "src/a/tests/test_a.py", "test-writer", r)))
        self.assertFalse(denied(write(r / "src/b/tests/test_b.py", "test-writer", r)))
        self.assertTrue(denied(write(r / "src/a/app.py", "test-writer", r)))
        self.assertTrue(denied(write(r / "src/c/tests/test_c.py", "test-writer", r)))    # T3 is green, not red
        self.assertTrue(denied(write(r / "src/d/tests/test_d.py", "test-writer", r)))    # T4 todo
        # `green` — second pass means green: coder gets T3 Writes only
        self.assertFalse(denied(write(r / "src/c/app.py", "coder", r)))
        self.assertTrue(denied(write(r / "src/a/app.py", "coder", r)))                   # T1 is red
        self.assertTrue(denied(write(r / "src/d/app.py", "coder", r)))

    def test_multiple_red_tasks_union(self):
        r = project(UNION_PLAN)
        for p in ["src/orders/tests/test_service.py", "src/orders/tests/test_repo.py",
                  "src/export/tests/test_csv.py", "src/export/tests/unit/test_rows.py",
                  "src/notify/tests/test_mail.py"]:
            with self.subTest(allowed=p):
                res = write(r / p, "test-writer", r)
                self.assertFalse(denied(res), f"{p}: {reason(res)}")
        for p in ["src/billing/tests/test_pay.py", "src/audit/tests/test_log.py",    # green and todo tasks
                  "src/orders/tests/test_other.py", "src/notify/tests/test_sms.py",   # not listed in any red task
                  "src/orders/app/service.py", "src/export/app/csv.py", "src/notify/app/mail.py"]:   # production code
            with self.subTest(denied=p):
                self.assertTrue(denied(write(r / p, "test-writer", r)), p)


class TestExplicitWriteBeatsTestPattern(unittest.TestCase):
    def setUp(self):
        self.root = project(EXPLICIT_PLAN)

    def test_explicit_write_beats_test_pattern(self):
        r = self.root
        for agent in ["coder", "deploy-engineer", "python-coder"]:
            for p in ["e2e/dev-stand.yml", "scripts/seed/tests/x.py", "src/stand/run.py"]:
                with self.subTest(agent=agent, allowed=p):
                    res = write(r / p, agent, r)
                    self.assertFalse(denied(res), f"{p}: {reason(res)}")
            for p in ["scripts/seed/tests/y.py",        # same directory, not listed
                      "e2e/other.yml",                  # same e2e/ folder, not listed
                      "src/stand/tests/test_run.py",    # a test file of the task, not in its Writes
                      "e2e/export-stand.yml",           # listed only in the Writes of a red task
                      "src/stand/test_run.py", "conftest.py"]:
                with self.subTest(agent=agent, denied=p):
                    self.assertTrue(denied(write(r / p, agent, r)), p)

    def test_explicit_write_does_not_open_tests_to_test_writer(self):
        r = self.root
        self.assertTrue(denied(write(r / "e2e/dev-stand.yml", "test-writer", r)))         # not in its Tests of a red task
        self.assertFalse(denied(write(r / "src/export/tests/test_export.py", "test-writer", r)))


class TestExecutorsTemp(unittest.TestCase):
    def test_executors_may_write_temp(self):
        targets = ["/tmp/scratch/out.txt", "/var/tmp/scratch/out.txt", f"{SCRATCHPAD}/notes.md", f"{SCRATCHPAD}/gen.py"]
        agents = ["coder", "refactorer", "test-writer", *LANGUAGE_CODERS]
        for plan in (ALL_STEPS_PLAN, NO_ACTIVE_PLAN, None):
            r = project(plan)
            for agent in agents:
                for p in targets:
                    for tool in ("Write", "Edit"):
                        with self.subTest(plan=plan is not None, agent=agent, p=p, tool=tool):
                            res = write(p, agent, r, tool=tool)
                            self.assertFalse(denied(res), f"{agent} {p}: {reason(res)}")

    def test_executors_still_cannot_write_elsewhere_outside_the_project(self):
        r = project(ALL_STEPS_PLAN)
        for agent in ["coder", "refactorer", "test-writer", "python-coder"]:
            for p in ["/etc/hosts", str(Path.home() / ".claude/settings.json"), "/usr/local/bin/x"]:
                with self.subTest(agent=agent, p=p):
                    self.assertTrue(denied(write(p, agent, r)), p)


class TestNewCodeExecutors(unittest.TestCase):
    def test_new_code_executors(self):
        r = project()   # T1 green: order_service.py, order_repo.py; T2 red: export_service.py; T3 todo
        for agent in NEW_EXECUTORS:
            for p in ["src/orders/app/services/order_service.py", "src/orders/app/repositories/order_repo.py"]:
                with self.subTest(agent=agent, allowed=p):
                    res = write(r / p, agent, r)
                    self.assertFalse(denied(res), f"{agent} {p}: {reason(res)}")
            for p in ["src/orders/app/services/export_service.py",     # Writes of a red task
                      "src/notify/x.py",                                # todo task
                      "src/orders/app/other.py"]:                       # in no write set
                with self.subTest(agent=agent, denied=p):
                    res = write(r / p, agent, r)
                    self.assertTrue(denied(res), p)
                    self.assertIn("T1", reason(res))
            with self.subTest(agent=agent, denied="test file in the Tests of a task"):
                self.assertTrue(denied(write(r / "src/orders/test/services/test_order_service.py", agent, r)))

    def test_new_code_executors_need_a_green_task(self):
        r = project(NO_ACTIVE_PLAN)
        for agent in NEW_EXECUTORS:
            with self.subTest(agent=agent):
                res = write(r / "src/a/app.py", agent, r)
                self.assertTrue(denied(res))
                self.assertIn("green", reason(res))

    def test_new_code_executors_never_write_tests_without_a_plan(self):
        r = project(None)
        for agent in NEW_EXECUTORS:
            for p in ["test/test_a.py", "src/api/tests/conftest.py", "web/src/App.test.tsx", "internal/order_test.go",
                      "crates/core/tests/api.rs"]:
                with self.subTest(agent=agent, p=p):
                    self.assertTrue(denied(write(r / p, agent, r)), p)
            with self.subTest(agent=agent, p="code"):
                self.assertFalse(denied(write(r / "src/api/app/main.py", agent, r)))


QUALITY_CONFIGS = ["ruff.toml", ".golangci.yml", "eslint.config.js", "mypy.ini", ".pre-commit-config.yaml",
                   ".coveragerc", "web/biome.json"]


class TestQualityConfigs(unittest.TestCase):
    def test_ci_engineer_may_edit_quality_configs(self):
        r = project(CONFIG_PLAN)
        for p in QUALITY_CONFIGS + [".github/workflows/ci.yml", "src/app/main.py"]:
            for tool in ("Write", "Edit"):
                with self.subTest(p=p, tool=tool):
                    res = write(r / p, "ci-engineer", r, tool=tool)
                    self.assertFalse(denied(res), f"{p}: {reason(res)}")
        # inside its write set only
        for p in ["pyproject.toml", "rustfmt.toml", ".prettierrc", "src/other/main.py"]:
            with self.subTest(outside=p):
                self.assertTrue(denied(write(r / p, "ci-engineer", r)), p)
        # no plan: configs are not closed to it
        free = project(None)
        for p in QUALITY_CONFIGS:
            with self.subTest(no_plan=p):
                self.assertFalse(denied(write(free / p, "ci-engineer", free)), p)
        # the test boundary still holds for it
        self.assertTrue(denied(write(r / "src/app/tests/test_main.py", "ci-engineer", r)))

    def test_coders_may_not_edit_quality_configs_even_when_listed(self):
        r = project(CONFIG_PLAN)
        free = project(None)
        for agent in ["coder", "refactorer", "build-fixer", *LANGUAGE_CODERS]:
            for p in QUALITY_CONFIGS:
                with self.subTest(agent=agent, p=p):
                    res = write(r / p, agent, r)
                    self.assertTrue(denied(res), p)
                    self.assertIn("config", reason(res))
                with self.subTest(agent=agent, p=p, plan=False):
                    self.assertTrue(denied(write(free / p, agent, free)), p)


class TestReaders(unittest.TestCase):
    def test_readers_cannot_write(self):
        for plan in (PLAN, None):
            r = project(plan)
            for agent in ["deploy-error-reader", "web-researcher"]:
                for p in ["src/orders/app/services/order_service.py", "src/orders/test/services/test_order_service.py",
                          "docs/API.md", ".plan/PLAN.md", "README.md", "flake.nix", ".github/workflows/ci.yml",
                          "notes.md"]:
                    for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
                        with self.subTest(plan=plan is not None, agent=agent, p=p, tool=tool):
                            self.assertTrue(denied(write(r / p, agent, r, tool=tool)), f"{agent} {p} {tool}")

    def test_readers_are_denied_outside_the_project_too(self):
        r = project()
        for agent in ["deploy-error-reader", "web-researcher"]:
            with self.subTest(agent=agent):
                self.assertTrue(denied(write("/etc/hosts", agent, r)))


if __name__ == "__main__":
    unittest.main()
