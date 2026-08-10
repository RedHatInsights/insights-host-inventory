# Spec: RHINENG-25608

## Summary
Add a PR check (pre-commit hook) that verifies job files in the `jobs/` directory have the executable permission bit set, preventing the common mistake of merging non-executable job files and needing a follow-up PR to fix permissions.

## Root Cause
The `jobs/` directory contains Python scripts (e.g., `host_reaper.py`, `delete_hosts_s3.py`, etc.) that must be executable so the runtime/scheduler can invoke them directly. These scripts all have `#!/usr/bin/env python3` shebangs. There is currently no automated check to enforce that newly added or modified job files have the executable permission bit (`chmod +x`) set. When developers forget to set it, a second PR is required to correct permissions. The existing `.pre-commit-config.yaml` already uses `pre-commit/pre-commit-hooks` v6.0.0 but does not include the `check-shebang-scripts-are-executable` hook, which would catch this problem automatically.

## Affected Files
- `.pre-commit-config.yaml`: This is the pre-commit configuration file that already includes `pre-commit/pre-commit-hooks` hooks (trailing-whitespace, end-of-file-fixer, check-yaml, check-json, debug-statements). Adding the `check-shebang-scripts-are-executable` hook here will: (1) run locally for developers on every commit, and (2) automatically run in the CI pipeline because `.github/workflows/checks.yaml` already executes all pre-commit hooks via `uses: pre-commit/action@v3.0.1`. The hook verifies that any file containing a shebang line (like `#!/usr/bin/env python3`) also has the executable bit set — exactly the enforcement needed for the `jobs/` directory scripts.

## Implementation Plan

### Step 1: Add a new hook entry for `check-shebang-scripts-are-executable` under the existing `pre-commit/pre-commit-hooks` repo section (currently at v6.0.0, lines 4–12), scoped to the `jobs/` directory using the `files: ^jobs/` key.
- File: `.pre-commit-config.yaml`
- Change type: modify
- Rationale: The `pre-commit/pre-commit-hooks` repo is already present at v6.0.0, which includes this hook. Adding it here — scoped to `jobs/` — means both local pre-commit runs and the existing CI `pre-commit/action@v3.0.1` step in `.github/workflows/checks.yaml` will enforce that any file with a shebang line in `jobs/` also has the executable bit set. All current `jobs/` files are already executable, so no existing files will fail.

## Test Strategy
- No tests are needed. This change is a single hook addition to `.pre-commit-config.yaml` and purely adds a validation check — it does not alter application logic.

## Risk Notes
- The hook checks ALL files in `jobs/` with shebang lines. Files like `common.py` and `__init__.py` have no shebang and are unaffected.
- If the `files: ^jobs/` scope is omitted, the hook will run repo-wide and could flag shebang-bearing scripts outside of `jobs/` that are not executable — scoping is recommended.
- Developers need pre-commit installed locally for the hook to run at commit time; CI is the guaranteed enforcement gate.
- The `check-shebang-scripts-are-executable` hook is only meaningful on Linux/macOS filesystems; Windows checkouts may not preserve executable bits, potentially causing false failures if developers commit from Windows. This is an existing limitation of the pre-commit setup.

## Constraints
- The `check-shebang-scripts-are-executable` hook checks ALL files with shebangs in the repository, not just `jobs/`. Files like `common.py` and `__init__.py` in `jobs/` that have no shebang will not be affected by this hook (they also happen to be executable currently).
- The hook can be scoped to only the `jobs/` directory using the `files` key in the hook config if a broader repo-wide check is undesirable.
- The `pre-commit/pre-commit-hooks` repo is already pinned to `v6.0.0`, which includes the `check-shebang-scripts-are-executable` hook, so no version bump is needed.
- All current job files in `jobs/` already have the executable bit set (`-rwxr-xr-x`), so adding this hook will not break the existing codebase.
- Developers must have pre-commit installed and configured locally for the hook to run as a pre-commit check; the CI pipeline (`checks.yaml`) enforces it for all PRs regardless.
