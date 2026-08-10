# mypy: disallow-untyped-defs

"""Tests verifying that all scripts in the jobs/ directory with shebang lines
are marked as executable. This enforces the condition checked by the
`check-shebang-scripts-are-executable` pre-commit hook added in RHINENG-25608.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

JOBS_DIR = Path(__file__).parent.parent / "jobs"


def _is_executable(path: Path) -> bool:
    """Return True if the file has at least one executable bit set (u/g/o)."""
    mode = path.stat().st_mode
    return bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))


def _has_shebang(path: Path) -> bool:
    """Return True if the file starts with a shebang (#!) line."""
    try:
        with path.open("rb") as fh:
            return fh.read(2) == b"#!"
    except OSError:
        return False


def _shebang_scripts_in_jobs() -> list[Path]:
    """Return all regular files in jobs/ that contain a shebang line."""
    results: list[Path] = []
    for entry in sorted(JOBS_DIR.iterdir()):
        if entry.is_file() and _has_shebang(entry):
            results.append(entry)
    return results


# Build the parametrize list at collection time so each file becomes its own
# test case and failures are reported individually.
_SHEBANG_SCRIPTS = _shebang_scripts_in_jobs()


@pytest.mark.parametrize("script", _SHEBANG_SCRIPTS, ids=[p.name for p in _SHEBANG_SCRIPTS])
def test_jobs_shebang_scripts_are_executable(script: Path) -> None:
    """Each file in jobs/ that contains a shebang line must have the executable
    bit set. This mirrors the check performed by the pre-commit hook
    `check-shebang-scripts-are-executable` scoped to `files: ^jobs/`.
    """
    assert _is_executable(script), (
        f"{script.relative_to(JOBS_DIR.parent)} has a shebang line but is NOT executable. "
        "Run `chmod +x <file>` and commit the permission change."
    )


def test_jobs_directory_contains_shebang_scripts() -> None:
    """Sanity-check: the jobs/ directory must contain at least one script with a
    shebang line so the parametrized suite above is not silently vacuous.
    """
    assert len(_SHEBANG_SCRIPTS) > 0, (
        "No shebang scripts found in jobs/. Either the directory is empty or the helper functions are broken."
    )
