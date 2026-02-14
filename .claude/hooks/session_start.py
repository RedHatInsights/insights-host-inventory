#!/usr/bin/env python3
"""
HBI SessionStart Hook.

Loads environment variables from .env into the Claude session via CLAUDE_ENV_FILE.
This ensures that .env values are available across all Bash tool invocations.

Logs output to .claude/hooks/session_start.log
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = os.environ.get("CLAUDE_PROJECT_DIR", str(Path(__file__).resolve().parents[2]))
LOG_DIR = os.path.join(PROJECT_DIR, ".claude", "hooks")
LOG_FILE = os.path.join(LOG_DIR, "session_start.log")
ENV_FILE = os.path.join(PROJECT_DIR, ".env")

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w"),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("session_start")


def parse_env_file(env_path):
    """Parse a .env file into a dict of key=value pairs.

    Handles comments, blank lines, quoted values, and export prefixes.
    """
    env_vars = {}
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                # Strip optional 'export ' prefix
                if line.startswith("export "):
                    line = line[7:]
                # Split on first '='
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                # Remove surrounding quotes
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                env_vars[key] = value
    except FileNotFoundError:
        log.info("No .env file found at %s", env_path)
    except PermissionError:
        log.warning("Cannot read .env file at %s", env_path)
    return env_vars


def write_claude_env(env_vars):
    """Write environment variables to CLAUDE_ENV_FILE if available."""
    claude_env_file = os.environ.get("CLAUDE_ENV_FILE")
    if not claude_env_file:
        log.info("CLAUDE_ENV_FILE not set; skipping env injection")
        return False

    try:
        with open(claude_env_file, "a") as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")
        log.info("Wrote %d variables to CLAUDE_ENV_FILE", len(env_vars))
        return True
    except OSError as e:
        log.warning("Failed to write to CLAUDE_ENV_FILE: %s", e)
        return False


def check_branch_status():
    """Check if the local branch is up to date with its remote tracking branch.

    Returns a list of warnings (empty if everything is up to date).
    """
    warnings = []
    try:
        # Fetch latest remote refs silently
        subprocess.run(  # noqa: S603
            ["git", "fetch", "--quiet"],
            cwd=PROJECT_DIR,
            capture_output=True,
            timeout=15,
        )

        # Get current branch name
        result = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return warnings
        branch = result.stdout.strip()

        # Get ahead/behind counts relative to upstream
        result = subprocess.run(  # noqa: S603
            ["git", "rev-list", "--left-right", "--count", f"{branch}...@{{u}}"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            # No upstream tracking branch
            log.info("  Branch '%s' has no upstream tracking branch", branch)
            return warnings

        ahead, behind = result.stdout.strip().split()
        ahead, behind = int(ahead), int(behind)

        if behind > 0:
            msg = f"Branch '{branch}' is {behind} commit(s) behind remote"
            if ahead > 0:
                msg += f" and {ahead} commit(s) ahead"
            msg += ". Consider pulling latest changes."
            warnings.append(msg)
            log.warning("  %s", msg)
        elif ahead > 0:
            log.info("  Branch '%s' is %d commit(s) ahead of remote", branch, ahead)
        else:
            log.info("  Branch '%s' is up to date with remote", branch)

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        log.info("  Could not check branch status: %s", e)
    return warnings


def main():
    log.info("=== HBI Session Start ===")

    env_vars = parse_env_file(ENV_FILE)
    if env_vars:
        log.info("Loaded %d variables from .env", len(env_vars))
        written = write_claude_env(env_vars)
    else:
        log.info("No .env variables to load")
        written = False

    branch_warnings = check_branch_status()

    # Build context message
    context_parts = []
    if env_vars:
        context_parts.append(f"Loaded {len(env_vars)} environment variables from .env.")
    else:
        context_parts.append("No .env file found or file is empty.")
    for warning in branch_warnings:
        context_parts.append(f"WARNING: {warning}")

    summary = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": " ".join(context_parts),
        }
    }

    if env_vars:
        summary["hookSpecificOutput"]["envVarsLoaded"] = str(len(env_vars))
        summary["hookSpecificOutput"]["envVarsWritten"] = str(written)

    log.info("=== Session start complete ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
