# Spec: RHINENG-25608

## Summary
Add a PR check to verify that job files in the `jobs/` directory have executable permissions set, preventing forgotten `chmod +x` from causing follow-up fix PRs.

## Root Cause
The `jobs/` directory contains Python scripts (e.g., `host_reaper.py`, `pendo_syncher.py`, etc.) that must have the executable bit set (`-rwxr-xr-x`) so they can be executed directly by the runtime environment. When developers add new job files via PRs, they sometimes forget to run `chmod +x` on them. There is no automated check to catch this before merge. The project already has a pre-commit infrastructure (`.pre-commit-config.yaml`) and a GitHub Actions `lints` job (`.github/workflows/checks.yaml`) that runs `pre-commit/action@v3.0.1`, making it straightforward to add a new hook that validates file permissions on any `jobs/*.py` file.

## Plan

- `.pre-commit-config.yaml` (modify): Add the `check-shebang-scripts-are-executable` hook to the existing `pre-commit/pre-commit-hooks` repo section (which is already pinned at `rev: v6.0.0`). Scope it with `files: '^jobs/.*\.py$'` so the check targets all Python files under the `jobs/` directory. This hook ships with `pre-commit/pre-commit-hooks` v6.0.0, so no version bump is required.

## Notes
- The `check-shebang-scripts-are-executable` hook is provided by `pre-commit/pre-commit-hooks` and verifies that files containing a shebang (`#!`) have the executable bit set. This is exactly the check needed for `jobs/*.py` files.
- All existing `jobs/*.py` files (including `__init__.py` and `common.py`) currently have executable permissions, so the hook will pass on the current codebase without any remediation needed.
- The `files` pattern in the hook should target `^jobs/.*\.py$` to match all Python files in the jobs directory.
- Care should be taken to handle the `jobs/__init__.py` file: it currently also has executable permissions, so including or excluding it from the check should be a deliberate decision.
- The check must work both locally (when developers run pre-commit) and in CI (GitHub Actions `lints` job runs `pre-commit/action@v3.0.1`).
- Only one file is touched (`.pre-commit-config.yaml`); no custom script is needed.
