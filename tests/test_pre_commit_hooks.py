"""
Tests for pre-commit hook configuration and the invariants they enforce.

RHINENG-25608: Ensure scripts with shebang lines are executable, enforced
by the `check-shebang-scripts-are-executable` pre-commit hook.
"""

import os
import stat
from pathlib import Path

import pytest
from yaml import safe_load

# Repo root is two levels up from this test file (tests/test_pre_commit_hooks.py)
REPO_ROOT = Path(__file__).parent.parent

# Directories to exclude when scanning for shebang scripts
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
    "iqe-host-inventory-plugin",
}

# File extensions to scan for shebang lines
SCRIPT_EXTENSIONS = {".py", ".sh", ".bash", ".zsh", ".ksh"}


def _iter_repo_scripts():
    """Yield Path objects for all script files in the repo, excluding irrelevant dirs."""
    for path in REPO_ROOT.rglob("*"):
        # Skip excluded directories
        if any(excluded in path.parts for excluded in EXCLUDED_DIRS):
            continue
        if not path.is_file():
            continue
        if path.suffix not in SCRIPT_EXTENSIONS:
            continue
        yield path


def _has_shebang(path: Path) -> bool:
    """Return True if the file starts with a shebang (#!) line."""
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"#!"
    except (OSError, PermissionError):
        return False


def _is_executable(path: Path) -> bool:
    """Return True if the file has at least one executable bit set."""
    file_stat = os.stat(path)
    return bool(file_stat.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))


def _find_shebang_scripts():
    """Return a list of repo scripts that contain a shebang line."""
    return [p for p in _iter_repo_scripts() if _has_shebang(p)]


class TestPreCommitConfig:
    """Tests verifying the pre-commit configuration."""

    def test_pre_commit_config_exists(self):
        """The .pre-commit-config.yaml file must exist at the repo root."""
        config_path = REPO_ROOT / ".pre-commit-config.yaml"
        assert config_path.exists(), ".pre-commit-config.yaml not found at repo root"

    def test_check_shebang_scripts_are_executable_hook_present(self):
        """
        The `check-shebang-scripts-are-executable` hook must be present
        in .pre-commit-config.yaml (RHINENG-25608).
        """
        config_path = REPO_ROOT / ".pre-commit-config.yaml"
        with open(config_path) as f:
            config = safe_load(f)

        hook_ids = []
        for repo in config.get("repos", []):
            for hook in repo.get("hooks", []):
                hook_ids.append(hook.get("id", ""))

        assert "check-shebang-scripts-are-executable" in hook_ids, (
            "The 'check-shebang-scripts-are-executable' hook is missing from "
            ".pre-commit-config.yaml. This hook ensures scripts with shebang lines "
            "have their executable bit set (see RHINENG-25608)."
        )

    def test_check_shebang_hook_is_in_pre_commit_hooks_repo(self):
        """
        The `check-shebang-scripts-are-executable` hook must be in the
        pre-commit/pre-commit-hooks repo section.
        """
        config_path = REPO_ROOT / ".pre-commit-config.yaml"
        with open(config_path) as f:
            config = safe_load(f)

        for repo in config.get("repos", []):
            repo_url = repo.get("repo", "")
            if "pre-commit/pre-commit-hooks" in repo_url:
                hook_ids = [h.get("id", "") for h in repo.get("hooks", [])]
                assert "check-shebang-scripts-are-executable" in hook_ids, (
                    "The 'check-shebang-scripts-are-executable' hook must be listed "
                    "under the pre-commit/pre-commit-hooks repo entry."
                )
                return

        pytest.fail("pre-commit/pre-commit-hooks repo not found in .pre-commit-config.yaml")


class TestShebangScriptsAreExecutable:
    """
    Tests verifying that all scripts with shebang lines have their executable
    bit set. This mirrors what the `check-shebang-scripts-are-executable`
    pre-commit hook enforces.
    """

    def test_jobs_scripts_with_shebangs_are_executable(self):
        """
        All Python scripts in the jobs/ directory that have a shebang line
        must have the executable bit set (RHINENG-25608).
        """
        jobs_dir = REPO_ROOT / "jobs"
        assert jobs_dir.exists(), "jobs/ directory not found at repo root"

        non_executable = []
        for path in jobs_dir.glob("*.py"):
            if _has_shebang(path) and not _is_executable(path):
                non_executable.append(str(path.relative_to(REPO_ROOT)))

        assert not non_executable, (
            "The following jobs/ scripts have a shebang line but are NOT executable "
            "(fix with `chmod +x <file>`):\n" + "\n".join(f"  {p}" for p in non_executable)
        )

    def test_root_entrypoint_scripts_with_shebangs_are_executable(self):
        """
        Root-level Python entrypoint scripts with shebang lines must be executable.
        """
        non_executable = []
        for path in REPO_ROOT.glob("*.py"):
            if _has_shebang(path) and not _is_executable(path):
                non_executable.append(str(path.relative_to(REPO_ROOT)))

        assert not non_executable, (
            "The following root-level scripts have a shebang line but are NOT executable "
            "(fix with `chmod +x <file>`):\n" + "\n".join(f"  {p}" for p in non_executable)
        )

    def test_all_repo_shebang_scripts_are_executable(self):
        """
        Every script file in the repo (excluding .venv, .git, etc.) that
        contains a shebang line must have its executable bit set.
        This directly mirrors the invariant enforced by the
        `check-shebang-scripts-are-executable` pre-commit hook (RHINENG-25608).
        """
        non_executable = []
        for path in _find_shebang_scripts():
            if not _is_executable(path):
                non_executable.append(str(path.relative_to(REPO_ROOT)))

        assert not non_executable, (
            "The following scripts have a shebang line but are NOT executable. "
            "Run `chmod +x <file>` to fix, or remove the shebang if the file "
            "is not meant to be executed directly:\n" + "\n".join(f"  {p}" for p in sorted(non_executable))
        )

    @pytest.mark.parametrize(
        "script_name",
        [
            "host_reaper.py",
            "delete_hosts_s3.py",
            "host_synchronizer.py",
            "update_staleness.py",
            "generate_stale_host_notifications.py",
            "delete_empty_org_groups.py",
        ],
    )
    def test_key_job_scripts_are_executable(self, script_name):
        """
        Key job scripts explicitly mentioned in RHINENG-25608 must be executable.
        """
        path = REPO_ROOT / "jobs" / script_name
        assert path.exists(), f"jobs/{script_name} not found"
        assert _has_shebang(path), f"jobs/{script_name} does not have a shebang line"
        assert _is_executable(path), (
            f"jobs/{script_name} has a shebang line but is not executable. Run `chmod +x jobs/{{script_name}}` to fix."
        )
