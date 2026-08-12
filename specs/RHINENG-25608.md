# Spec: RHINENG-25608

## Summary
Add a PR check to verify that job files in the `jobs/` directory have executable permissions, preventing broken deployments caused by missing executable bits.

## Root Cause
The `jobs/` directory contains Python scripts (e.g., `host_reaper.py`, `pendo_syncher.py`, etc.) with `#!/usr/bin/env python3` shebangs that must be executable to run. Developers occasionally add new job files without setting the executable bit (`chmod +x`), requiring a follow-up PR to fix it. There is currently no automated check in the pre-commit hooks or CI pipeline to catch this omission. The `.pre-commit-config.yaml` already uses `pre-commit/pre-commit-hooks` v6.0.0, which ships the `check-shebang-scripts-are-executable` hook — but that hook is not yet enabled. The GitHub Actions `checks.yaml` workflow already runs the full pre-commit suite via `pre-commit/action@v3.0.1`, so enabling the hook in `.pre-commit-config.yaml` is sufficient to add the check both locally and in CI.

## Plan

- `.pre-commit-config.yaml` (modify): Add `check-shebang-scripts-are-executable` as an additional hook entry under the existing `pre-commit/pre-commit-hooks` block (already at v6.0.0, alongside `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-json`, and `debug-statements`). No other configuration is needed — the hook will automatically detect any file with a shebang line that lacks the executable bit.

## Notes
- All current job files already have the executable bit set (`-rwxr-xr-x`), so adding this hook will not break the existing codebase or CI.
- The hook inspects git-tracked file metadata, so the executable bit must be committed (via `chmod +x` before staging, or `git update-index --chmod=+x`) to be detected correctly. On Windows, git may not track executable bits unless `core.fileMode=true` is set; contributors on Windows should use `git update-index --chmod=+x` explicitly.
- The `check-shebang-scripts-are-executable` hook only flags files that contain a shebang line AND are NOT marked executable — it won't flag `jobs/common.py` or `jobs/__init__.py` (which have no shebangs), so no false positives are expected.
- No `stages` configuration is needed for this hook; the default `pre-commit` stage is correct and matches the existing hooks in the config.
