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


def main():
    log.info("=== HBI Session Start ===")

    env_vars = parse_env_file(ENV_FILE)
    if env_vars:
        log.info("Loaded %d variables from .env", len(env_vars))
        written = write_claude_env(env_vars)
    else:
        log.info("No .env variables to load")
        written = False

    summary = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                f"Loaded {len(env_vars)} environment variables from .env."
                if env_vars
                else "No .env file found or file is empty."
            ),
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
