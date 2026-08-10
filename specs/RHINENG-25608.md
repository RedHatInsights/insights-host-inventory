# Spec: RHINENG-25608

## Summary
Add an automated check to verify that all Python files in the `jobs/` directory have executable permissions (git mode 100755), preventing developers from accidentally committing non-executable job files and needing follow-up PRs.

## Root Cause
The `jobs/` directory contains Python job scripts (e.g., `host_reaper.py`, `host_delete_duplicates.py`, etc.) that must be executable (git mode `100755`) to run correctly. When a developer adds a new job file without explicitly setting the executable bit (`chmod +x`), git stores it as mode `100644` (non-executable). There is currently no automated check in either the pre-commit config (`.pre-commit-config.yaml`) or the CI workflow (`.github/workflows/checks.yaml`) to catch this mistake before it lands in `master`. As confirmed by `git ls-files --stage jobs/`, all existing job files are correctly set to `100755`, but new files could easily be committed without this permission, requiring a separate PR to fix.

## Affected Files
- `.pre-commit-config.yaml`: This is where the permission check should be added as a new local pre-commit hook. The file already has a `local` hooks section with custom hooks (e.g., `redocly-merge`, `redocly-validate`). A new hook using `git ls-files --stage 'jobs/*.py'` can verify all Python job files have mode `100755` and fail if any are `100644`. The hook uses `files: ^jobs/.*\.py$` to trigger only when Python files under `jobs/` are staged, avoiding unnecessary runs on unrelated commits. Since the GitHub Actions `checks.yaml` workflow already runs `pre-commit/action@v3.0.1`, any hook added here is automatically enforced in CI without further changes.
- `scripts/check_job_permissions.sh`: A new helper shell script (to be created) that the pre-commit hook entry can reference. It should use `git ls-files --stage 'jobs/*.py'` to list all tracked Python job files and their git modes, then fail with a helpful error message if any file does not have mode `100755`. The script must handle edge cases gracefully (e.g., empty `jobs/` directory or no tracked Python files should exit 0 silently). Using a dedicated script (rather than an inline bash one-liner) makes the hook more readable and maintainable. The `scripts/` directory already exists and contains similar utility scripts (e.g., `worktree.sh`).

## Implementation Plan

### Step 1: Create a new shell script that runs `git ls-files --stage 'jobs/*.py'` and scans the output for any Python file whose git mode is not `100755`. The pattern is restricted to `*.py` files so that future non-Python files in `jobs/` (e.g., config files, READMEs) are not incorrectly required to be executable. The script must also handle edge cases gracefully: if the `jobs/` directory is empty or contains no tracked Python files, the script should exit 0 silently (no confusing output). If any Python files are found with incorrect permissions, print their names alongside a clear error message and exit with a non-zero status. If all Python files are correctly permissioned, exit 0. Model the shebang/`set -euo pipefail` style after `scripts/worktree.sh`. This file must be committed with executable permissions (git mode `100755`).
- File: `scripts/check_job_permissions.sh`
- Change type: create
- Rationale: Using a dedicated script rather than an inline command makes the hook readable and testable. Checking `git ls-files --stage` is authoritative in CI environments where filesystem bits may not be preserved. Restricting to `*.py` avoids false positives on non-Python files that may be added to `jobs/` in the future.

### Step 2: Add a new hook entry to the existing `local` repo section (after the `redocly-validate` hook). The hook should have `id: check-job-file-permissions`, `name: Check job file permissions`, `language: script`, `entry: scripts/check_job_permissions.sh`, `pass_filenames: false`, and `files: ^jobs/.*\.py$` so that the hook only triggers when Python files under `jobs/` are staged. This avoids running the check on every commit (as `always_run: true` would) and reduces unnecessary overhead as the repo grows, while still ensuring coverage in CI via `--all-files`.
- File: `.pre-commit-config.yaml`
- Change type: modify
- Rationale: The `local` repo section already exists for custom hooks. Using `language: script` and pointing to the new shell script integrates with the existing pre-commit infrastructure, and is automatically enforced in CI via the `pre-commit/action@v3.0.1` step already present in `.github/workflows/checks.yaml`. Using `files` instead of `always_run: true` scopes the hook to only trigger when relevant files are changed, reducing overhead for unrelated commits.

## Test Strategy
- Approach: Verify the script's two code paths manually or via a lightweight shell test: (1) run it against the current repo state (all `jobs/` files at `100755`) and confirm it exits 0; (2) mock a `git ls-files --stage` output containing a `100644`-mode file and confirm the script exits 1 and prints the offending filename. Since the project has no existing shell test harness, these verifications can be done by running `pre-commit run check-job-file-permissions --all-files` in the local checkout and confirming it passes, then manually staging a test file without executable permission to confirm the hook catches it.
- Test files: scripts/check_job_permissions.sh
- Coverage targets: Script exits 0 when all Python files in jobs/ have git mode 100755, Script exits 1 and prints offending filenames when any Python file in jobs/ has a non-100755 git mode, Script exits 0 silently when jobs/ contains no tracked Python files (empty directory edge case), Pre-commit hook triggers when Python files under jobs/ are staged

## Risk Notes
- The new script itself must be committed with mode `100755`; if it is accidentally committed as `100644`, pre-commit will fail to execute it with `language: script`.
- The script scopes its check to `jobs/*.py` files only. If non-Python executable scripts are added to `jobs/` in the future, the glob pattern should be expanded accordingly.
- The hook uses `files: ^jobs/.*\.py$` to trigger only when relevant files are staged. CI runs with `--all-files` which ensures full coverage regardless.

## Constraints
- The check must use `git ls-files --stage jobs/` (git-tracked mode) rather than filesystem `stat` or `ls -la`, because CI checkouts may not preserve filesystem executable bits — only the git-stored mode is authoritative.
- The hook should be in the `local` section of `.pre-commit-config.yaml` (no external dependency) since it relies on a repo-specific path pattern (`jobs/`).
- The new script `scripts/check_job_permissions.sh` must itself be committed with executable permissions, otherwise pre-commit cannot run it.
- The `checks.yaml` workflow already runs `pre-commit/action@v3.0.1` in the `lints` job, so no changes to the GitHub Actions workflow are needed — adding the hook to `.pre-commit-config.yaml` is sufficient to enforce it in CI.
- If the project ever adds non-Python executable scripts to `jobs/`, the script's file pattern (`jobs/*.py`) may need expanding to cover additional extensions.
