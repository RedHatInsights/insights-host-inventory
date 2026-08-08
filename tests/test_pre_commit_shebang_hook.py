"""
Tests for RHINENG-25608: Verify that the check-shebang-scripts-are-executable pre-commit hook
is correctly configured in .pre-commit-config.yaml, scoped to '^jobs/' only.

The hook ensures that any jobs/ script containing a shebang line (#!) must have
the executable bit set. Non-jobs/ files (e.g., dev_server.py) are excluded from
this check via the 'files: ^jobs/' scope, even if they have a shebang.
"""

import os
import re
import stat
from pathlib import Path

from yaml import safe_load

REPO_ROOT = Path(__file__).parent.parent
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
JOBS_DIR = REPO_ROOT / "jobs"


def _load_pre_commit_config():
    """Load and parse .pre-commit-config.yaml."""
    with open(PRE_COMMIT_CONFIG) as f:
        return safe_load(f)


def _get_shebang_hook_config():
    """Find the check-shebang-scripts-are-executable hook config."""
    config = _load_pre_commit_config()
    for repo in config.get("repos", []):
        for hook in repo.get("hooks", []):
            if hook.get("id") == "check-shebang-scripts-are-executable":
                return hook
    return None


def _has_shebang(filepath: Path) -> bool:
    """Return True if the file starts with a shebang (#!)."""
    try:
        with open(filepath, "rb") as f:
            return f.read(2) == b"#!"
    except OSError:
        return False


def _is_executable(filepath: Path) -> bool:
    """Return True if the file has at least one executable bit set."""
    file_stat = os.stat(filepath)
    return bool(file_stat.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))


class TestShebangHookConfiguration:
    """Tests verifying the pre-commit hook is configured correctly."""

    def test_hook_exists_in_pre_commit_config(self):
        """The check-shebang-scripts-are-executable hook must be present in the config."""
        hook = _get_shebang_hook_config()
        assert hook is not None, "check-shebang-scripts-are-executable hook not found in .pre-commit-config.yaml"

    def test_hook_scoped_to_jobs_directory(self):
        """The hook must be scoped to '^jobs/' to avoid flagging non-jobs/ files."""
        hook = _get_shebang_hook_config()
        assert hook is not None, "Hook not found in .pre-commit-config.yaml"
        files_pattern = hook.get("files", "")
        assert files_pattern == "^jobs/", (
            f"Hook 'files' scope must be '^jobs/' but got: {files_pattern!r}. "
            "Without this scope, dev_server.py (shebang but not executable) would be incorrectly flagged."
        )

    def test_hook_is_in_pre_commit_hooks_repo(self):
        """The hook must come from the pre-commit/pre-commit-hooks repository."""
        config = _load_pre_commit_config()
        for repo in config.get("repos", []):
            for hook in repo.get("hooks", []):
                if hook.get("id") == "check-shebang-scripts-are-executable":
                    repo_url = repo.get("repo", "")
                    assert "pre-commit/pre-commit-hooks" in repo_url, (
                        f"Expected hook from 'pre-commit/pre-commit-hooks', got: {repo_url!r}"
                    )
                    return
        raise AssertionError("check-shebang-scripts-are-executable hook not found")

    def test_hook_files_pattern_matches_jobs_scripts(self):
        """The '^jobs/' pattern must match jobs/*.py script paths."""
        hook = _get_shebang_hook_config()
        assert hook is not None, "Hook not found in .pre-commit-config.yaml"
        pattern = hook.get("files", "")
        # Test that the pattern matches expected jobs/ paths
        assert re.search(pattern, "jobs/host_reaper.py"), f"Pattern {pattern!r} should match 'jobs/host_reaper.py'"
        assert re.search(pattern, "jobs/update_staleness.py"), (
            f"Pattern {pattern!r} should match 'jobs/update_staleness.py'"
        )

    def test_hook_files_pattern_does_not_match_dev_server(self):
        """The '^jobs/' pattern must NOT match dev_server.py."""
        hook = _get_shebang_hook_config()
        assert hook is not None, "Hook not found in .pre-commit-config.yaml"
        pattern = hook.get("files", "")
        assert not re.search(pattern, "dev_server.py"), (
            f"Pattern {pattern!r} should NOT match 'dev_server.py' — "
            "dev_server.py has a shebang but is intentionally non-executable"
        )

    def test_hook_files_pattern_does_not_match_root_level_py(self):
        """The '^jobs/' pattern must NOT match root-level Python files."""
        hook = _get_shebang_hook_config()
        assert hook is not None, "Hook not found in .pre-commit-config.yaml"
        pattern = hook.get("files", "")
        for root_file in ["manage.py", "app.py", "conftest.py", "dev_server.py"]:
            assert not re.search(pattern, root_file), (
                f"Pattern {pattern!r} should NOT match root-level file {root_file!r}"
            )


class TestJobsScriptsAreExecutableWhenTheyHaveShebang:
    """
    Tests verifying that all jobs/ scripts with shebangs have the executable bit set.
    This is the core invariant enforced by the pre-commit hook.
    """

    def test_jobs_scripts_with_shebang_are_executable(self):
        """
        Every jobs/*.py file that contains a shebang line must have executable bit set.
        The hook enforces this, and this test verifies the current state is compliant.
        """
        violations = []
        for py_file in sorted(JOBS_DIR.glob("*.py")):
            if _has_shebang(py_file) and not _is_executable(py_file):
                violations.append(str(py_file.relative_to(REPO_ROOT)))

        assert not violations, (
            "The following jobs/ scripts have shebangs but are NOT executable "
            "(would fail check-shebang-scripts-are-executable hook):\n" + "\n".join(f"  - {v}" for v in violations)
        )

    def test_known_jobs_scripts_have_shebang_and_executable(self):
        """
        Spot-check known jobs/ scripts that are expected to have shebangs and be executable.
        """
        expected_executable_scripts = [
            "host_reaper.py",
            "update_staleness.py",
            "delete_hosts_s3.py",
            "host_delete_duplicates.py",
            "host_synchronizer.py",
            "pendo_syncher.py",
            "generate_stale_host_notifications.py",
            "delete_empty_org_groups.py",
            "delete_host_namespace_access_tags.py",
        ]
        for script_name in expected_executable_scripts:
            script_path = JOBS_DIR / script_name
            if not script_path.exists():
                continue  # Skip if file doesn't exist
            assert _has_shebang(script_path), f"Expected {script_name} to have a shebang line"
            assert _is_executable(script_path), (
                f"{script_name} has a shebang but is not executable — "
                "the check-shebang-scripts-are-executable hook would fail"
            )

    def test_jobs_init_has_no_shebang(self):
        """
        jobs/__init__.py has no shebang so is not flagged by the hook,
        regardless of its executable bit.
        """
        init_file = JOBS_DIR / "__init__.py"
        assert init_file.exists(), "jobs/__init__.py must exist"
        assert not _has_shebang(init_file), (
            "jobs/__init__.py should not have a shebang — it is a module init file, not a standalone script"
        )

    def test_jobs_common_has_no_shebang(self):
        """
        jobs/common.py has no shebang so is not flagged by the hook,
        regardless of its executable bit.
        """
        common_file = JOBS_DIR / "common.py"
        assert common_file.exists(), "jobs/common.py must exist"
        assert not _has_shebang(common_file), (
            "jobs/common.py should not have a shebang — it is a shared library module, not a standalone script"
        )


class TestDevServerNotFlaggedByHook:
    """
    Tests verifying that dev_server.py is NOT scoped by the hook.
    dev_server.py has a shebang (#!) but is not executable by design.
    The '^jobs/' scope prevents it from being checked.
    """

    def test_dev_server_has_shebang(self):
        """Confirm dev_server.py has a shebang — this is what makes scoping important."""
        dev_server = REPO_ROOT / "dev_server.py"
        assert dev_server.exists(), "dev_server.py must exist in repo root"
        assert _has_shebang(dev_server), (
            "dev_server.py is expected to have a shebang (#!). "
            "If it no longer has one, the scoping concern may be moot."
        )

    def test_dev_server_is_not_executable(self):
        """
        dev_server.py is intentionally non-executable. Without the '^jobs/' scope,
        the hook would incorrectly flag it. Verify it is not executable.
        """
        dev_server = REPO_ROOT / "dev_server.py"
        assert dev_server.exists(), "dev_server.py must exist in repo root"
        assert not _is_executable(dev_server), (
            "dev_server.py has a shebang but should NOT be executable. "
            "The hook is scoped to '^jobs/' so it correctly excludes this file."
        )

    def test_dev_server_not_in_jobs_directory(self):
        """dev_server.py is in the repo root, not in jobs/, so '^jobs/' scope excludes it."""
        dev_server = REPO_ROOT / "dev_server.py"
        assert dev_server.exists(), "dev_server.py must exist"
        assert not str(dev_server.relative_to(REPO_ROOT)).startswith("jobs/"), (
            "dev_server.py must not be in the jobs/ directory"
        )


class TestHookSimulation:
    """
    Simulate the check-shebang-scripts-are-executable hook logic to verify
    it correctly identifies violations and non-violations.
    """

    def _check_shebang_executable(self, filepath: Path) -> bool:
        """
        Simulate what check-shebang-scripts-are-executable does:
        Returns True (passes) if the file either has no shebang OR is executable.
        Returns False (fails) if the file has a shebang but is NOT executable.
        """
        if _has_shebang(filepath):
            return _is_executable(filepath)
        return True  # No shebang → not relevant to this hook

    def test_hook_logic_passes_shebang_with_executable(self, tmp_path):
        """A file with a shebang AND executable bit should pass the hook check."""
        script = tmp_path / "jobs" / "test_script.py"
        script.parent.mkdir(parents=True)
        script.write_text("#!/usr/bin/env python3\nprint('hello')\n")
        script.chmod(0o755)

        assert self._check_shebang_executable(script), (
            "A script with shebang + executable bit should pass the hook check"
        )

    def test_hook_logic_fails_shebang_without_executable(self, tmp_path):
        """A file with a shebang but WITHOUT executable bit should fail the hook check."""
        script = tmp_path / "jobs" / "test_script.py"
        script.parent.mkdir(parents=True)
        script.write_text("#!/usr/bin/env python3\nprint('hello')\n")
        script.chmod(0o644)  # No executable bit

        assert not self._check_shebang_executable(script), (
            "A script with shebang but no executable bit should fail the hook check"
        )

    def test_hook_logic_passes_no_shebang_not_executable(self, tmp_path):
        """A file WITHOUT a shebang and without executable bit should pass (not relevant)."""
        module = tmp_path / "jobs" / "common.py"
        module.parent.mkdir(parents=True)
        module.write_text("from functools import partial\n")
        module.chmod(0o644)

        assert self._check_shebang_executable(module), "A file without a shebang should always pass the hook check"

    def test_hook_logic_passes_no_shebang_with_executable(self, tmp_path):
        """A file WITHOUT a shebang but WITH executable bit should pass (only shebang matters)."""
        module = tmp_path / "jobs" / "__init__.py"
        module.parent.mkdir(parents=True)
        module.write_text("")
        module.chmod(0o755)

        assert self._check_shebang_executable(module), (
            "A file without a shebang should pass even if it has the executable bit"
        )
