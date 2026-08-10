# Spec: RHINENG-25608

## Summary
Add an automated check to verify that all Python files in the `jobs/` directory have executable permissions (git mode 100755), preventing developers from accidentally committing non-executable job files and needing follow-up PRs.

## Root Cause
The `jobs/` directory contains Python job scripts (e.g., `host_reaper.py`, `host_delete_duplicates.py`, etc.) that must be executable (git mode `100755`) to run correctly. When a developer adds a new job file without explicitly setting the executable bit (`chmod +x`), git stores it as mode `100644` (non-executable). There is currently no automated check in either the pre-commit config (`.pre-commit-config.yaml`) or the CI workflow (`.github/workflows/checks.yaml`) to catch this mistake before it lands in `master`. As confirmed by `git ls-files --stage jobs/`, all existing job files are correctly set to `100755`, but new files could easily be committed without this permission, requiring a separate PR to fix.

## Affected Files
- `.pre-commit-config.yaml`: This is where the permission check should be added as a new local pre-commit hook. The file already has a `local` hooks section with custom hooks (e.g., `redocly-merge`, `redocly-validate`). A new hook using `git ls-files --stage jobs/` can verify all job files have mode `100755` and fail if any are `100644`. Since the GitHub Actions `checks.yaml` workflow already runs `pre-commit/action@v3.0.1`, any hook added here is automatically enforced in CI without further changes.
- `scripts/check_job_permissions.sh`: A new helper shell script (to be created) that the pre-commit hook entry can reference. It should use `git ls-files --stage jobs/` to list all tracked job files and their git modes, then fail with a helpful error message if any file does not have mode `100755`. Using a dedicated script (rather than an inline bash one-liner) makes the hook more readable and maintainable. The `scripts/` directory already exists and contains similar utility scripts (e.g., `worktree.sh`).

## Implementation Plan

### Step 1: Create a new shell script that runs `git ls-files --stage jobs/` and scans the output for any file whose git mode is not `100755`. If any such files are found, print their names alongside a clear error message and exit with a non-zero status. If all files are correctly permissioned, exit 0. Model the shebang/`set -euo pipefail` style after `scripts/worktree.sh`. This file must be committed with executable permissions (git mode `100755`).
- File: `scripts/check_job_permissions.sh`
- Change type: create
- Rationale: Using a dedicated script rather than an inline command makes the hook readable and testable. Checking `git ls-files --stage` is authoritative in CI environments where filesystem bits may not be preserved.

### Step 2: Add a new hook entry to the existing `local` repo section (after the `redocly-validate` hook). The hook should have `id: check-job-file-permissions`, `name: Check job file permissions`, `language: script`, `entry: scripts/check_job_permissions.sh`, `pass_filenames: false`, and `always_run: true` so that it runs on every commit regardless of which files were staged.
- File: `.pre-commit-config.yaml`
- Change type: modify
- Rationale: The `local` repo section already exists for custom hooks. Using `language: script` and pointing to the new shell script integrates with the existing pre-commit infrastructure, and is automatically enforced in CI via the `pre-commit/action@v3.0.1` step already present in `.github/workflows/checks.yaml`.

## Test Strategy
- Approach: Verify the script's two code paths manually or via a lightweight shell test: (1) run it against the current repo state (all `jobs/` files at `100755`) and confirm it exits 0; (2) mock a `git ls-files --stage` output containing a `100644`-mode file and confirm the script exits 1 and prints the offending filename. Since the project has no existing shell test harness, these verifications can be done by running `pre-commit run check-job-file-permissions --all-files` in the local checkout and confirming it passes, then manually staging a test file without executable permission to confirm the hook catches it.
- Test files: scripts/check_job_permissions.sh
- Coverage targets: Script exits 0 when all files in jobs/ have git mode 100755, Script exits 1 and prints offending filenames when any file in jobs/ has a non-100755 git mode, Pre-commit hook runs on every commit (always_run: true) regardless of staged files

## Risk Notes
- The new script itself must be committed with mode `100755`; if it is accidentally committed as `100644`, pre-commit will fail to execute it with `language: script`.
- If the `jobs/` directory ever gains subdirectories or non-Python files (e.g., config files that legitimately should not be executable), the script's filtering logic may need updating to scope to `*.py` files only.
- The `always_run: true` setting means the hook runs on every commit even if no `jobs/` files were changed, which adds a small overhead but ensures coverage.

## Constraints
- The check must use `git ls-files --stage jobs/` (git-tracked mode) rather than filesystem `stat` or `ls -la`, because CI checkouts may not preserve filesystem executable bits — only the git-stored mode is authoritative.
- The hook should be in the `local` section of `.pre-commit-config.yaml` (no external dependency) since it relies on a repo-specific path pattern (`jobs/`).
- The new script `scripts/check_job_permissions.sh` must itself be committed with executable permissions, otherwise pre-commit cannot run it.
- The `checks.yaml` workflow already runs `pre-commit/action@v3.0.1` in the `lints` job, so no changes to the GitHub Actions workflow are needed — adding the hook to `.pre-commit-config.yaml` is sufficient to enforce it in CI.
- If the project ever adds subdirectories or non-Python files to `jobs/`, the script's file pattern may need updating.
