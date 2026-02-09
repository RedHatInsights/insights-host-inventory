# /maintenance - HBI Development Environment Maintenance

Run the deterministic maintenance script to update dependencies, images, and verify health.

## Instructions

1. First, orient yourself by running the `/prime` command:
   ```
   Skill(/prime)
   ```

2. Run the maintenance script:
   ```
   python3 .claude/hooks/setup_maintenance.py
   ```

3. Read the log file at `.claude/hooks/setup.maintenance.log` for detailed output.

4. Analyze the JSON output and report to the user:
   - Whether Python dependencies were updated
   - Whether Docker images were pulled
   - Whether services restarted successfully
   - Whether database migrations ran
   - Whether style checks passed
   - Whether the health check passed
   - Any failures or warnings

5. If style checks failed, show the specific issues and offer to fix them.

6. If any steps failed, provide actionable remediation steps:
   - Dependency issues: suggest `make hbi-deps` to reinstall
   - Docker issues: suggest `make hbi-up` or `make hbi-reset` if services are in a bad state
   - Style issues: suggest `make hbi-style` to re-run checks

7. End with a summary table showing each step's status.
