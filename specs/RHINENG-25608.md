# Spec: RHINENG-25608

## Summary
Add a PR check to verify that job files in the `jobs/` directory have executable permissions, preventing broken deployments caused by missing executable bits.

## Root Cause
The `jobs/` directory contains Python scripts (e.g., `host_reaper.py`, `pendo_syncher.py`, etc.) with `#!/usr/bin/env python3` shebangs that must be executable to run. Developers occasionally add new job files without setting the executable bit (`chmod +x`), requiring a follow-up PR to fix it. There is currently no automated check in the pre-commit hooks or CI pipeline to catch this omission. The `.pre-commit-config.yaml` already uses `pre-commit/pre-commit-hooks` v6.0.0, which ships the `check-shebang-scripts-are-executable` hook — but that hook is not yet enabled. The GitHub Actions `checks.yaml` workflow already runs the full pre-commit suite via `pre-commit/action@v3.0.1`, so enabling the hook in `.pre-commit-config.yaml` is sufficient to add the check both locally and in CI.

## Plan

- `.pre-commit-config.yaml` (modify): Add `check-shebang-scripts-are-executable` as an additional hook entry under the existing `pre-commit/pre-commit-hooks` block (already at v6.0.0, alongside `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-json`, and `debug-statements`). No other configuration is needed — the hook will automatically detect any file with a shebang line that lacks the executable bit.

## Notes
- On Windows, git may not track executable bits correctly unless core.fileMode=true is set; contributors on Windows may need to use `git update-index --chmod=+x` to set the bit.
- All current job files already have the executable bit set, so adding this hook will not break the existing codebase or CI.
- The hook inspects git-tracked metadata, so the executable bit must be committed (not just set on disk) to be detected correctly.
- The `check-shebang-scripts-are-executable` hook only flags files that contain a shebang line AND are NOT marked executable — it won't flag `jobs/common.py` or `jobs/__init__.py` (which have no shebangs), so no false positives are expected.
- All current job files already have the executable bit set (`-rwxr-xr-x`), so adding the hook will not break the existing codebase or CI.
- The hook relies on git-tracked file metadata for the executable bit; the executable bit must be committed via `git update-index --chmod=+x` or `chmod +x` before staging.
- On Windows, git may not track executable bits correctly unless `core.fileMode=true` is set; developers on Windows may need to use `git update-index --chmod=+x` explicitly.
- If a local pre-commit hook approach is chosen, the `stages` configuration in `.pre-commit-config.yaml` should be reviewed to ensure the hook runs on the correct stage (default `pre-commit` stage is appropriate here).
