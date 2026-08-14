"""
Tests to verify that .pre-commit-config.yaml is correctly configured and that
scripts in the jobs/ directory with shebang lines have the executable bit set.

Related issue: RHINENG-25608
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
PRECOMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
JOBS_DIR = REPO_ROOT / "jobs"


# ---------------------------------------------------------------------------
# Helper: parse the pre-commit config once per session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def precommit_config() -> dict:
    with PRECOMMIT_CONFIG.open() as fh:
        return yaml.safe_load(fh)


def _all_hook_ids(config: dict) -> list[tuple[str, dict]]:
    """Return a flat list of (hook_id, hook_dict) from all repos in the config."""
    hooks = []
    for repo in config.get("repos", []):
        for hook in repo.get("hooks", []):
            hooks.append((hook.get("id", ""), hook))
    return hooks


# ---------------------------------------------------------------------------
# Tests for .pre-commit-config.yaml content
# ---------------------------------------------------------------------------


def test_check_shebang_scripts_are_executable_hook_present(precommit_config: dict) -> None:
    """The check-shebang-scripts-are-executable hook must be present in .pre-commit-config.yaml."""
    hook_ids = [hid for hid, _ in _all_hook_ids(precommit_config)]
    assert "check-shebang-scripts-are-executable" in hook_ids, (
        "Expected 'check-shebang-scripts-are-executable' hook in .pre-commit-config.yaml, "
        "but it was not found. Add it under the pre-commit/pre-commit-hooks repo entry."
    )


def test_check_shebang_hook_scoped_to_jobs_dir(precommit_config: dict) -> None:
    """The check-shebang-scripts-are-executable hook must be scoped to the jobs/ directory."""
    for hook_id, hook in _all_hook_ids(precommit_config):
        if hook_id == "check-shebang-scripts-are-executable":
            files_pattern = hook.get("files", "")
            assert files_pattern, (
                "The 'check-shebang-scripts-are-executable' hook must have a 'files:' "
                "restriction scoping it to the jobs/ directory (e.g. files: ^jobs/)."
            )
            assert "jobs" in files_pattern, (
                f"Expected the 'files:' pattern of 'check-shebang-scripts-are-executable' "
                f"to reference the jobs/ directory, but got: '{files_pattern}'"
            )
            return
    pytest.fail("Hook 'check-shebang-scripts-are-executable' not found in .pre-commit-config.yaml")


def test_check_shebang_hook_in_precommit_hooks_repo(precommit_config: dict) -> None:
    """check-shebang-scripts-are-executable must live inside the pre-commit/pre-commit-hooks repo."""
    for repo in precommit_config.get("repos", []):
        repo_url = repo.get("repo", "")
        if "pre-commit/pre-commit-hooks" in repo_url:
            hook_ids = [h.get("id", "") for h in repo.get("hooks", [])]
            assert "check-shebang-scripts-are-executable" in hook_ids, (
                "Expected 'check-shebang-scripts-are-executable' to be listed under "
                "the 'pre-commit/pre-commit-hooks' repo entry."
            )
            return
    pytest.fail("Could not find a 'pre-commit/pre-commit-hooks' repo entry in .pre-commit-config.yaml")


# ---------------------------------------------------------------------------
# Tests for file permissions in jobs/
# ---------------------------------------------------------------------------


def _jobs_scripts_with_shebang() -> list[Path]:
    """Return all files in jobs/ whose first line starts with '#!'."""
    scripts = []
    for path in sorted(JOBS_DIR.rglob("*.py")):
        try:
            with path.open("rb") as fh:
                first_bytes = fh.read(2)
            if first_bytes == b"#!":
                scripts.append(path)
        except (OSError, PermissionError):
            pass
    return scripts


def _is_executable(path: Path) -> bool:
    """Return True if the file has at least one executable bit set (user, group, or other)."""
    mode = path.stat().st_mode
    return bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))


@pytest.mark.parametrize("script", _jobs_scripts_with_shebang(), ids=lambda p: p.name)
def test_jobs_shebang_scripts_are_executable(script: Path) -> None:
    """Every script in jobs/ that contains a shebang line must have the executable bit set."""
    assert _is_executable(script), (
        f"{script.relative_to(REPO_ROOT)} has a shebang line but is NOT executable. Run: chmod +x <file>  to fix this."
    )


def test_at_least_one_jobs_shebang_script_detected() -> None:
    """Ensure the shebang-detection logic finds scripts in jobs/ (guards against misconfiguration)."""
    scripts = _jobs_scripts_with_shebang()
    assert scripts, (
        "No scripts with shebang lines were found in the jobs/ directory. "
        "This may indicate that the detection logic is broken or the jobs/ directory is missing."
    )
