# Spec: RHINENG-25608

## Summary
Add a pre-commit (or CI pipeline) check to verify that job files in the `jobs/` directory have executable permissions, preventing the need for follow-up PRs to fix missing execute bits.

## Root Cause
The `jobs/` directory contains Python scripts (e.g., `host_reaper.py`, `delete_hosts_s3.py`, etc.) that all start with a `#!/usr/bin/env python3` shebang and must be executable to run correctly. There is currently no automated check enforcing this — neither in the `.pre-commit-config.yaml` nor in the GitHub Actions workflows — so developers occasionally commit files without the execute bit set, requiring a separate fix PR. The `pre-commit/pre-commit-hooks` package (already present in the config at v6.0.0) provides a `check-shebang-scripts-are-executable` hook that would catch exactly this class of mistake, but it has not been added to the configuration.

## Plan

> **Note:** This spec describes the planned implementation. The actual `.pre-commit-config.yaml` modification will be made in the implementation phase following spec approval.

- `.pre-commit-config.yaml` (modify): Add the `check-shebang-scripts-are-executable` hook to the existing `pre-commit/pre-commit-hooks` block (already pinned at v6.0.0, alongside `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-json`, and `debug-statements`). No version bump or new repo block is needed.

### Scope of the hook
The `check-shebang-scripts-are-executable` hook applies to **all files in the repo** that contain a shebang line, not just those in `jobs/`. This broader scope is intentional and acceptable — it provides a useful safeguard for any executable script (e.g., `pr_check.sh`, `build_deploy.sh`, `run.py`, `manage.py`). An audit confirmed all shebang-bearing files in the repo already have the execute bit set, so no false positives are expected upon merging.

## Notes
- Developers with pre-commit installed locally will need to run `pre-commit install` or `pre-commit autoupdate` to pick up the new hook in their local environment.
- Any shebang-bearing file anywhere in the repo that lacks the execute bit would cause an immediate CI failure; a quick audit (`find . -name '*.py' -o -name '*.sh' | xargs grep -l '^#!'`) was run and confirmed all such files are already executable.
- The `check-shebang-scripts-are-executable` hook is only available from `pre-commit/pre-commit-hooks` v4.4.0+; the repo already uses v6.0.0, so compatibility is not an issue.
- The hook checks all files in the repo with shebang lines, not just those in `jobs/`. Other executable scripts (e.g., `pr_check.sh`, `build_deploy.sh`, `run.py`, `manage.py`) also have shebangs and are already executable, so no false positives are expected.
- The `pr_check_common.sh` script is NOT executable (`-rw-r--r--`) but also does not have a shebang, so it would not be flagged by this hook. If it were to gain a shebang, it would need to be made executable too.
- This change will affect developers' local pre-commit setup; they will need to run `pre-commit install` or `pre-commit autoupdate` to pick up the new hook if they have pre-commit installed locally.
