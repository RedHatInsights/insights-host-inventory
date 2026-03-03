#!/usr/bin/env python3
"""
HBI Development Environment Initialization Script.

Deterministic setup script that:
1. Checks prerequisites (python3, pipenv, podman, podman compose)
2. Creates required directories (~/.pg_data)
3. Initializes git submodules (e.g., librdkafka)
4. Checks /etc/hosts for kafka entry
5. Installs Python dependencies via pipenv
6. Starts Podman Compose services
7. Waits for PostgreSQL to be ready
8. Runs database migrations
9. Verifies the HBI web service health

Can be run standalone or as a Claude Code hook.
Logs output to .claude/hooks/setup.init.log

Usage:
    python3 .claude/hooks/setup_init.py              # Full setup
    python3 .claude/hooks/setup_init.py --check-only  # Pre-flight checks only
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
LOG_FILE = os.path.join(LOG_DIR, "setup.init.log")
DEV_COMPOSE_FILE = os.path.join(PROJECT_DIR, "dev.yml")

# Ensure log directory exists and configure logging to both file and stderr
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w"),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("setup_init")


def run_cmd(cmd, cwd=None, timeout=60, env=None, check=True):
    """Run a command and return (returncode, stdout, stderr).

    cmd must be a list of strings (no shell interpretation).
    """
    if not isinstance(cmd, list) or not all(isinstance(c, str) for c in cmd):
        raise TypeError(f"cmd must be a list of strings, got: {type(cmd)}")
    merged_env = {**os.environ, **(env or {})}
    merged_env.pop("PIPENV_PIPFILE", None)  # Ensure pipenv uses the project root Pipfile
    try:
        result = subprocess.run(  # noqa: S603
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


def check_prerequisites():
    """Verify required tools are installed."""
    results = {}
    checks = {
        "python3": ["python3", "--version"],
        "pipenv": ["pipenv", "--version"],
        "podman": ["podman", "--version"],
        "podman_compose": ["podman", "compose", "version"],
    }
    all_ok = True
    for name, cmd in checks.items():
        rc, stdout, stderr = run_cmd(cmd, check=False)
        ok = rc == 0
        version = stdout or stderr
        results[name] = {"ok": ok, "version": version}
        status = "OK" if ok else "MISSING"
        log.info("  %-16s %s  %s", name, status, version if ok else "")
        if not ok:
            all_ok = False

    # Check Python version >= 3.9
    if results["python3"]["ok"]:
        rc, stdout, _ = run_cmd(
            ["python3", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            check=False,
        )
        if rc == 0:
            major, minor = stdout.split(".")
            if int(major) < 3 or (int(major) == 3 and int(minor) < 9):
                log.warning("  Python 3.9+ required, found %s", stdout)
                results["python3"]["ok"] = False
                all_ok = False

    return all_ok, results


def check_hosts_file():
    """Check if 'kafka' is in /etc/hosts."""
    try:
        with open("/etc/hosts") as f:
            content = f.read()
        has_kafka = "kafka" in content
        if not has_kafka:
            log.warning(
                "  'kafka' not found in /etc/hosts. "
                "Some services may not connect properly. "
                "Add '127.0.0.1 kafka' to /etc/hosts if needed."
            )
        else:
            log.info("  /etc/hosts contains kafka entry")
        return has_kafka
    except PermissionError:
        log.warning("  Cannot read /etc/hosts")
        return False


def setup_directories():
    """Create required directories."""
    pg_data = Path.home() / ".pg_data"
    if not pg_data.exists():
        pg_data.mkdir(parents=True, exist_ok=True)
        log.info("  Created %s", pg_data)
    else:
        log.info("  %s already exists", pg_data)
    return True


def init_submodules():
    """Initialize and update git submodules."""
    log.info("  Initializing git submodules ...")
    rc, _, stderr = run_cmd(["git", "submodule", "update", "--init", "--recursive"])
    if rc == 0:
        log.info("  Git submodules initialized successfully")
    else:
        log.error("  Git submodule init failed: %s", stderr)
    return rc == 0


def install_dependencies():
    """Install Python dependencies via pipenv."""
    log.info("  Running pipenv install --dev ...")
    rc, _, stderr = run_cmd(["pipenv", "install", "--dev"], timeout=300)
    if rc == 0:
        log.info("  Dependencies installed successfully")
    else:
        log.error("  pipenv install failed: %s", stderr)
    return rc == 0


def start_podman_services():
    """Start Podman Compose services."""
    log.info("  Starting Podman Compose services ...")
    rc, _, stderr = run_cmd(
        ["podman", "compose", "-f", DEV_COMPOSE_FILE, "up", "-d"],
        timeout=120,
    )
    if rc == 0:
        log.info("  Podman services started")
    else:
        log.error("  Podman Compose failed: %s", stderr)
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
    status = results["overall"] if isinstance(results.get("overall"), str) else "success"
    parts = [f"Setup {status}."]
    failed = results.get("failed_steps", [])
    if failed:
        parts.append(f"Failed steps: {', '.join(failed)}.")
    passed = [
        k for k, v in results.items() if isinstance(v, dict) and v.get("ok") and k not in ("overall", "failed_steps")
    ]
    if passed:
        parts.append(f"Passed: {', '.join(passed)}.")
    return " ".join(parts)


def run_check_only():
    """Run pre-flight checks only (for hook --check-only mode)."""
    log.info("=== HBI Pre-flight Check ===")
    prereqs_ok, _ = check_prerequisites()
    hosts_ok = check_hosts_file()

    # Check if Podman services are running
    rc, stdout, _ = run_cmd(
        ["podman", "compose", "-f", DEV_COMPOSE_FILE, "ps", "--format", "json"],
        check=False,
        timeout=10,
    )
    podman_running = rc == 0 and bool(stdout.strip())

    issues = []
    if not prereqs_ok:
        issues.append("missing prerequisites")
    if not hosts_ok:
        issues.append("kafka not in /etc/hosts")
    if not podman_running:
        issues.append("Podman services not running")

    context = "Pre-flight OK." if not issues else f"Pre-flight issues: {', '.join(issues)}."

    summary = {
        "hookSpecificOutput": {
            "hookEventName": "Setup",
            "additionalContext": context,
            "check_only": "true",
            "prerequisites": str(prereqs_ok),
            "hosts_file": str(hosts_ok),
            "podman_running": str(podman_running),
        }
    }
    ok = not issues
    log.info("=== Pre-flight check complete ===")
    return summary, ok


def run_full_setup():
    """Run the full setup process."""
    log.info("=== HBI Development Environment Setup ===")
    results = {}

    log.info("[1/8] Checking prerequisites ...")
    prereqs_ok, prereq_results = check_prerequisites()
    results["prerequisites"] = {"ok": prereqs_ok, "details": prereq_results}
    if not prereqs_ok:
        log.error("Prerequisites check failed. Install missing tools and retry.")
        results["overall"] = "failed"
        results["failed_steps"] = ["prerequisites"]
        return (
            {
                "hookSpecificOutput": {
                    "hookEventName": "Setup",
                    "additionalContext": build_summary_text(results),
                }
            },
            False,
        )

    log.info("[2/8] Setting up directories ...")
    results["directories"] = {"ok": setup_directories()}

    log.info("[3/8] Initializing git submodules ...")
    results["submodules"] = {"ok": init_submodules()}

    log.info("[4/8] Checking /etc/hosts ...")
    results["hosts_file"] = {"ok": check_hosts_file()}

    log.info("[5/8] Installing Python dependencies ...")
    results["dependencies"] = {"ok": install_dependencies()}

    log.info("[6/8] Starting Podman Compose services ...")
    results["podman"] = {"ok": start_podman_services()}

    log.info("[7/8] Waiting for PostgreSQL ...")
    results["postgres"] = {"ok": wait_for_postgres()}

    if results["postgres"]["ok"]:
        log.info("[8/8] Running database migrations ...")
        results["migrations"] = {"ok": run_migrations()}
    else:
        log.warning("[8/8] Skipping migrations (PostgreSQL not ready)")
        results["migrations"] = {"ok": False, "skipped": True}

    # Health check (non-blocking)
    results["health"] = {"ok": verify_health()}

    # Summary
    failed = [k for k, v in results.items() if isinstance(v, dict) and not v.get("ok")]
    results["overall"] = "failed" if failed else "success"
    results["failed_steps"] = failed

    ok = results["overall"] == "success"
    if ok:
        log.info("=== Setup completed successfully ===")
    else:
        log.warning("=== Setup completed with failures: %s ===", ", ".join(failed))

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
    check_only = "--check-only" in sys.argv

    # Consume stdin (hook input) if available
    if not sys.stdin.isatty():
        with contextlib.suppress(OSError):
            sys.stdin.read()

    summary, ok = run_check_only() if check_only else run_full_setup()

    # Output hookSpecificOutput JSON to stdout for Claude to read
    print(json.dumps(summary, indent=2))

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
