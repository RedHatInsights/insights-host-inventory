#!/usr/bin/env python3
"""
HBI Development Environment Maintenance Script.

Deterministic maintenance script that:
1. Updates Python dependencies via pipenv
2. Pulls latest Podman images
3. Restarts Podman Compose services
4. Runs database migrations
5. Runs style checks
6. Verifies service health

Can be run standalone or triggered via the /maintenance slash command.
Logs output to .claude/hooks/setup.maintenance.log
"""

import contextlib
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_DIR = os.environ.get("CLAUDE_PROJECT_DIR", str(Path(__file__).resolve().parents[2]))
LOG_DIR = os.path.join(PROJECT_DIR, ".claude", "hooks")
LOG_FILE = os.path.join(LOG_DIR, "setup.maintenance.log")
DEV_COMPOSE_FILE = os.path.join(PROJECT_DIR, "dev.yml")

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w"),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("setup_maintenance")


def run_cmd(cmd, cwd=None, timeout=60, env=None, check=True):
    """Run a command and return (returncode, stdout, stderr).

    cmd must be a list of strings (no shell interpretation).
    """
    merged_env = {**os.environ, **(env or {})}
    merged_env.pop("PIPENV_PIPFILE", None)  # Ensure pipenv uses the project root Pipfile
    try:
        result = subprocess.run(
            cmd,
            shell=False,
            cwd=cwd or PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged_env,
        )
        if check and result.returncode != 0:
            log.warning("Command failed: %s\nstderr: %s", cmd, result.stderr.strip())
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        log.error("Command timed out after %ds: %s", timeout, cmd)
        return 1, "", f"Timeout after {timeout}s"
    except FileNotFoundError:
        return 127, "", f"Command not found: {cmd}"


def update_dependencies():
    """Update Python dependencies."""
    log.info("  Running pipenv update --dev ...")
    rc, _, stderr = run_cmd(["pipenv", "update", "--dev"], timeout=300)
    if rc == 0:
        log.info("  Dependencies updated successfully")
    else:
        log.error("  pipenv update failed: %s", stderr)
    return rc == 0


def pull_podman_images():
    """Pull latest Podman images."""
    log.info("  Pulling latest Podman images ...")
    rc, _, stderr = run_cmd(
        ["podman", "compose", "-f", DEV_COMPOSE_FILE, "pull"],
        timeout=180,
    )
    if rc == 0:
        log.info("  Podman images pulled successfully")
    else:
        log.error("  Podman pull failed: %s", stderr)
    return rc == 0


def restart_services():
    """Restart Podman Compose services."""
    log.info("  Restarting Podman Compose services ...")
    rc, _, stderr = run_cmd(
        ["podman", "compose", "-f", DEV_COMPOSE_FILE, "up", "-d"],
        timeout=120,
    )
    if rc == 0:
        log.info("  Services restarted successfully")
    else:
        log.error("  Service restart failed: %s", stderr)
    return rc == 0


def wait_for_postgres(max_wait=30):
    """Poll PostgreSQL until ready."""
    log.info("  Waiting for PostgreSQL (max %ds) ...", max_wait)
    start = time.time()
    while time.time() - start < max_wait:
        rc, _, _ = run_cmd(
            ["podman", "compose", "-f", DEV_COMPOSE_FILE, "exec", "-T", "db", "pg_isready", "-h", "db"],
            check=False,
            timeout=5,
        )
        if rc == 0:
            elapsed = time.time() - start
            log.info("  PostgreSQL ready after %.1fs", elapsed)
            return True
        time.sleep(2)
    log.error("  PostgreSQL not ready after %ds", max_wait)
    return False


def run_migrations():
    """Run database migrations."""
    log.info("  Running database migrations ...")
    env = {
        "INVENTORY_DB_HOST": "localhost",
        "INVENTORY_DB_NAME": "insights",
        "INVENTORY_DB_USER": "insights",
        "INVENTORY_DB_PASS": "insights",
    }
    rc, _, stderr = run_cmd(
        ["pipenv", "run", "make", "upgrade_db"],
        timeout=60,
        env=env,
    )
    if rc == 0:
        log.info("  Migrations completed successfully")
    else:
        log.error("  Migration failed: %s", stderr)
    return rc == 0


def run_style_checks():
    """Run code style checks."""
    log.info("  Running style checks ...")
    rc, _, stderr = run_cmd(
        ["pipenv", "run", "make", "style"],
        timeout=120,
    )
    if rc == 0:
        log.info("  Style checks passed")
    else:
        log.warning("  Style checks had issues: %s", stderr)
    return rc == 0


def verify_health(max_retries=5, delay=3):
    """Verify the HBI web service is responding."""
    url = "http://localhost:8080/health"
    log.info("  Checking HBI web service at %s ...", url)
    for attempt in range(1, max_retries + 1):
        rc, stdout, _ = run_cmd(
            ["curl", "-sf", url],
            check=False,
            timeout=10,
        )
        if rc == 0:
            log.info("  HBI web service is healthy (attempt %d): %s", attempt, stdout)
            return True
        log.info("  Attempt %d/%d failed, retrying in %ds ...", attempt, max_retries, delay)
        time.sleep(delay)
    log.warning("  HBI web service not responding after %d attempts", max_retries)
    return False


def build_summary_text(results):
    """Build a human-readable summary from results dict."""
    status = results.get("overall", "success")
    parts = [f"Maintenance {status}."]
    failed = results.get("failed_steps", [])
    if failed:
        parts.append(f"Failed steps: {', '.join(failed)}.")
    passed = [
        k for k, v in results.items() if isinstance(v, dict) and v.get("ok") and k not in ("overall", "failed_steps")
    ]
    if passed:
        parts.append(f"Passed: {', '.join(passed)}.")
    return " ".join(parts)


def run_maintenance():
    """Run the full maintenance process."""
    log.info("=== HBI Development Environment Maintenance ===")
    results = {}

    log.info("[1/6] Updating Python dependencies ...")
    results["dependencies"] = {"ok": update_dependencies()}

    log.info("[2/6] Pulling latest Podman images ...")
    results["podman_pull"] = {"ok": pull_podman_images()}

    log.info("[3/6] Restarting services ...")
    results["podman_restart"] = {"ok": restart_services()}

    log.info("[4/6] Waiting for PostgreSQL ...")
    results["postgres"] = {"ok": wait_for_postgres()}

    if results["postgres"]["ok"]:
        log.info("[5/6] Running database migrations ...")
        results["migrations"] = {"ok": run_migrations()}
    else:
        log.warning("[5/6] Skipping migrations (PostgreSQL not ready)")
        results["migrations"] = {"ok": False, "skipped": True}

    log.info("[6/6] Running style checks ...")
    results["style"] = {"ok": run_style_checks()}

    # Health check (non-blocking)
    results["health"] = {"ok": verify_health()}

    # Summary
    failed = [k for k, v in results.items() if isinstance(v, dict) and not v.get("ok")]
    results["overall"] = "failed" if failed else "success"
    results["failed_steps"] = failed

    ok = results["overall"] == "success"
    if ok:
        log.info("=== Maintenance completed successfully ===")
    else:
        log.warning("=== Maintenance completed with failures: %s ===", ", ".join(failed))

    return (
        {
            "hookSpecificOutput": {
                "hookEventName": "Setup",
                "additionalContext": build_summary_text(results),
            }
        },
        ok,
    )


def main():
    # Consume stdin if available
    if not sys.stdin.isatty():
        with contextlib.suppress(OSError):
            sys.stdin.read()

    summary, ok = run_maintenance()

    # Output hookSpecificOutput JSON to stdout
    print(json.dumps(summary, indent=2))

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
