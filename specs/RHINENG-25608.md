# Spec: RHINENG-25608

## Summary
Add a PR check to verify that job files in the `jobs/` directory have executable permissions set, preventing forgotten `chmod +x` from causing follow-up fix PRs.

## Root Cause
The `jobs/` directory contains Python scripts (e.g., `host_reaper.py`, `pendo_syncher.py`, etc.) that must have the executable bit set (`-rwxr-xr-x`) so they can be executed directly by the runtime environment. When developers add new job files via PRs, they sometimes forget to run `chmod +x` on them. There is no automated check to catch this before merge. The project already has a pre-commit infrastructure (`.pre-commit-config.yaml`) and a GitHub Actions `lints` job (`.github/workflows/checks.yaml`) that runs `pre-commit/action@v3.0.1`, making it straightforward to add a new hook that validates file permissions on any `jobs/*.py` file.

## Plan

- `scripts/check_job_permissions.sh` (create): Create a new bash script that accepts filenames as arguments (as pre-commit passes them) and verifies each has the executable bit set using `test -x`. It should print a clear error message for any non-executable file and exit non-zero if any violations are found. The script must itself be marked executable (`chmod +x`) before committing, modelled after the shebang/`set -euo pipefail` style already used in `scripts/worktree.sh`.

- `.pre-commit-config.yaml` (modify): Add a new hook entry to the existing `local` repo section (after the `redocly-validate` hook) with `language: script`, `entry: scripts/check_job_permissions.sh`, and `files: '^jobs/.*\.py$'`. This scopes the check to all Python files under the `jobs/` directory.

## Notes
- The script file itself must be committed with executable permissions; if the Coder agent writes the file without running `chmod +x scripts/check_job_permissions.sh`, the `language: script` hook will fail to execute.
- All existing `jobs/*.py` files (including `__init__.py` and `common.py`) currently have executable permissions, so the hook will pass on the current codebase without any remediation needed.
- Pre-commit's `language: script` runs the entry path directly as an executable — ensure the shebang line (`#!/usr/bin/env bash`) is present and correct.
- The pre-commit hook must use `language: script` (pointing to the shell script) or `language: system` (using a bash/python inline command) — both are supported in pre-commit local hooks.
- The `files` pattern in the hook should target `^jobs/.*\.py$` to match all Python files in the jobs directory.
- Care should be taken to handle the `jobs/__init__.py` file: it currently also has executable permissions, so including or excluding it from the check should be a deliberate decision.
- The check must work both locally (when developers run pre-commit) and in CI (GitHub Actions `lints` job runs `pre-commit/action@v3.0.1`).
- Any new script file (e.g., `scripts/check_job_permissions.sh`) must itself be executable, otherwise the hook will fail to run.
