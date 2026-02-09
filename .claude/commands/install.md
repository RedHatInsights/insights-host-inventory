---
description: Run setup_init hook and report installation results
argument-hint: [hil]
---

# /install - Automated HBI Development Setup

Run the deterministic setup script to initialize the HBI development environment.

## Variables

MODE: $1 (optional - if "true", run interactive mode)

## Instructions

1. First, orient yourself to the codebase by running the `/prime` command:
   ```
   Skill(/prime)
   ```

2. Check for interactive mode: if MODE is "true", run `Skill(/install-hil)` and ignore the remainder of this prompt
3. Run the setup init script:
   ```
   python3 .claude/hooks/setup_init.py
   ```

4. Read the log file at `.claude/hooks/setup.init.log` to see detailed output.

5. Analyze the JSON output from the script. Report to the user:
   - Which prerequisites were found (python3, pipenv, podman, podman compose)
   - Whether directories were created
   - Whether Podman services started successfully
   - Whether PostgreSQL became ready
   - Whether database migrations ran
   - Whether the HBI web service health check passed
   - Any failures or warnings

6. If any steps failed, provide actionable guidance on how to fix them:
   - Missing prerequisites: suggest installation commands (or `make hbi-deps` for Python deps)
   - Podman issues: suggest checking Podman is running (or `make hbi-up` to start services)
   - Database issues: suggest checking `~/.pg_data` permissions
   - Service health: suggest `make hbi-logs SERVICE=<service>` to check container logs

7. End with a summary table showing each step's status.
