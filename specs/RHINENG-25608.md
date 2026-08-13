# Spec: RHINENG-25608

## Summary
Add a PR check to verify that job files in the `jobs/` directory have executable permissions set correctly

## Root Cause
The `jobs/` directory contains Python scripts with shebang lines (`#!/usr/bin/env python3`) that must be executable to run correctly. There is currently no automated check that enforces executable permissions on these files, so developers frequently forget to set the bit when adding new job files, requiring follow-up fix PRs. The repository already uses `pre-commit` (including the `pre-commit/pre-commit-hooks` package at v6.0.0) and runs it in the GitHub Actions `lints` job via `pre-commit/action`. The `check-shebang-scripts-are-executable` hook — which verifies that any file containing a shebang line is also marked executable — is available in `pre-commit/pre-commit-hooks` but is not currently enabled.

## Plan

- `.pre-commit-config.yaml` (modify): Add a new hook entry for `check-shebang-scripts-are-executable` to the existing `pre-commit/pre-commit-hooks` block (rev v6.0.0), scoped to the `jobs/` directory via a `files` pattern anchored to the start of the path (e.g., `^jobs/`). The `^` anchor ensures the pattern only matches files rooted in the `jobs/` directory and does not accidentally match paths that merely contain `jobs/` as a subdirectory elsewhere. Place it immediately after the existing `debug-statements` hook entry, following the same YAML style as the other hook entries in that block.

## Constraints
- Do not add `check-executables-have-shebangs` (the *reverse* hook that verifies files with the executable bit also contain a shebang) — it solves a different problem and is out of scope for this issue.
- Do not modify the GitHub Actions workflow — the existing `lints` job already runs `pre-commit/action` and will pick up the new hook automatically.
- The hook must be added inside the existing `pre-commit/pre-commit-hooks` block at rev v6.0.0, not as a new repo entry.
