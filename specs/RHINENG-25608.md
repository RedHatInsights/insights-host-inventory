# Spec: RHINENG-25608

> **Note:** This is a specification document that describes the planned implementation. The actual code change to `.pre-commit-config.yaml` will be made in the implementation phase based on this spec.

## Summary
Add a PR check that verifies job files in the `jobs/` directory have the executable permission bit set, preventing the recurring issue of missing execute permissions being caught only after merging.

## Root Cause
The `jobs/` directory contains Python scripts (all with `#!/usr/bin/env python3` shebangs) that must be executable to run as job entrypoints. Developers occasionally forget to `chmod +x` these files when adding or modifying them, which is only discovered after merging. There is currently no automated check in either the pre-commit hooks (`.pre-commit-config.yaml`) or the CI pipeline (`.github/workflows/checks.yaml`) to enforce executable permissions on these files.

## Affected Files
- `.pre-commit-config.yaml`: This is the primary file to change. The repository already uses `pre-commit/pre-commit-hooks` at v6.0.0, which includes the `check-shebang-scripts-are-executable` hook. Adding this hook will ensure that any file with a shebang line (like the `#!/usr/bin/env python3` scripts in `jobs/`) is required to have the executable bit set. Pre-commit is already wired into the CI pipeline via `.github/workflows/checks.yaml` (using `pre-commit/action@v3.0.1`), so this hook will automatically run on every PR without any additional CI changes.
- `.github/workflows/checks.yaml`: Optionally, a dedicated 'check-permissions' step could be added to the `lints` job as a fallback or supplementary check using a shell command (e.g., `find jobs/ -name '*.py' ! -executable -print | grep . && exit 1 || exit 0`). However, since the pre-commit approach already covers this via `.pre-commit-config.yaml`, this file may not need modification.

## Implementation Plan

### Step 1: Add the `check-shebang-scripts-are-executable` hook to the existing `pre-commit/pre-commit-hooks` (rev: v6.0.0) block. Scope it to the `jobs/` directory using `files: '^jobs/'` to avoid flagging other intentionally non-executable files with shebangs (e.g., `dev_server.py`). The new hook entry to add under the `pre-commit/pre-commit-hooks` hooks list is:

```yaml
  - id: check-shebang-scripts-are-executable
    files: '^jobs/'
```

Place it alongside the existing hooks (`trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-json`, `debug-statements`).
- File: `.pre-commit-config.yaml`
- Change type: modify
- Rationale: The `pre-commit/pre-commit-hooks` repo at v6.0.0 already includes this hook (available since v4.0.0), so no version bump is needed. Scoping to `^jobs/` is required because `dev_server.py` has a `#!/usr/bin/env python3` shebang but is intentionally not executable; without scoping, that file would incorrectly fail the check. The CI pipeline already runs pre-commit via `pre-commit/action@v3.0.1` in `.github/workflows/checks.yaml`, so no CI changes are needed — the hook will automatically run on every PR.

## Test Strategy
- Approach: Verify the hook works correctly by checking two scenarios: (1) a jobs/ file with a shebang and executable bit passes, and (2) a jobs/ file with a shebang but without the executable bit fails. Since all existing `jobs/*.py` files with shebangs are already executable, the hook should pass on the current codebase. To test the failure case, one can temporarily create a jobs/ test file with a shebang but without `+x` and confirm the hook catches it. Also verify `dev_server.py` (shebang but not executable) is NOT flagged due to the `files: '^jobs/'` scope.
- Test files: .pre-commit-config.yaml
- Coverage targets: jobs/ scripts with shebangs must have the executable bit set, Non-jobs/ files with shebangs (e.g., dev_server.py) are not flagged by this hook, jobs/__init__.py and jobs/common.py (no shebang) are not flagged by this hook

## Risk Notes
- All existing jobs/*.py files with shebangs are already executable (verified via ls -la), so adding this hook will not break the current CI state.
- The `files: '^jobs/'` scope is essential — without it, `dev_server.py` (which has a shebang but is intentionally non-executable) would fail the check.
- jobs/__init__.py and jobs/common.py have no shebangs, so they are unaffected by this hook even though they are in jobs/ and are executable.
- This hook is a no-op on Windows (it skips the check), but CI runs on ubuntu-latest so this is not a concern.

## Constraints
- The `check-shebang-scripts-are-executable` hook from `pre-commit/pre-commit-hooks` is already available at the pinned version v6.0.0 (available since v4.0.0), so no version bump is needed.
- The hook checks files with shebangs — `jobs/common.py` and `jobs/__init__.py` do NOT have shebangs (they are helper modules, not entrypoints), so they will not be affected by this check.
- Care should be taken not to apply the check too broadly across all Python files in the repo (e.g., `dev_server.py`, `gunicorn.conf.py` are intentionally not executable), so a `files` pattern scoped to `jobs/` may be needed if the hook's default behavior is too broad.
- The `check-shebang-scripts-are-executable` hook ignores files on Windows, but since CI runs on `ubuntu-latest`, this is not a concern.
