#!/usr/bin/env python3
"""
HBI Development Environment Initialization Script.

Deterministic setup script that:
1. Checks prerequisites (python3, pipenv, podman, podman compose)
2. Creates required directories (~/.pg_data)
3. Initializes git submodules (e.g., librdkafka)
4. Checks /etc/hosts for kafka entry
5. Bootstraps .env file with sensible defaults
6. Installs Python dependencies via pipenv
7. Checks for port conflicts before starting services
8. Starts Podman Compose services
9. Waits for PostgreSQL to be ready
10. Runs database migrations
11. Verifies the HBI web service health

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
import socket
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


def bootstrap_env_file():
    """Create .env with sensible defaults if missing, or validate critical variables."""
    env_file = Path(PROJECT_DIR) / ".env"
    defaults = {
        "PROMETHEUS_MULTIPROC_DIR": "/tmp",
        "FLASK_ENV": "development",
        "BYPASS_RBAC": "true",
        "BYPASS_UNLEASH": "true",
        "BYPASS_KESSEL": "true",
        "CLOWDER_ENABLED": "false",
        "PDB_DEBUG_MODE": "true",
        "APP_NAME": "inventory",
        "INVENTORY_LOG_LEVEL": "DEBUG",
        "INVENTORY_DB_USER": "insights",
        "INVENTORY_DB_PASS": "insights",
        "INVENTORY_DB_HOST": "localhost",
        "INVENTORY_DB_NAME": "insights",
        "INVENTORY_DB_POOL_TIMEOUT": "5",
        "INVENTORY_DB_POOL_SIZE": "5",
        "INVENTORY_DB_SSL_MODE": "",
        "INVENTORY_DB_SSL_CERT": "",
        "UNLEASH_TOKEN": "*:*.dbffffc83b1f92eeaf133a7eb878d4c58231acc159b5e1478ce53cfc",  # notsecret
        "UNLEASH_CACHE_DIR": "./.unleash",
        "UNLEASH_URL": "http://unleash:4242/api",
        "KAFKA_EXPORT_SERVICE_TOPIC": "platform.export.requests",
    }

    if not env_file.exists():
        log.info("  .env not found, creating with defaults ...")
        lines = ["# HBI local development environment\n"]
        for key, value in defaults.items():
            lines.append(f"{key}={value}\n")
        env_file.write_text("".join(lines))
        log.info("  Created .env with %d variables", len(defaults))
        return True

    # File exists — validate critical variables
    log.info("  .env exists, validating critical variables ...")
    content = env_file.read_text()
    missing = []
    critical_vars = ["UNLEASH_TOKEN", "INVENTORY_DB_USER", "INVENTORY_DB_PASS"]
    for var in critical_vars:
        # Check for non-commented, non-empty assignment
        found = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith(f"{var}=") and len(stripped) > len(f"{var}="):
                found = True
                break
        if not found:
            missing.append(var)

    if missing:
        log.warning("  .env is missing critical variables: %s", ", ".join(missing))
        # Append missing variables with defaults
        with open(env_file, "a") as f:
            f.write("\n# Auto-added by setup_init.py\n")
            for var in missing:
                if var in defaults:
                    f.write(f"{var}={defaults[var]}\n")
                    log.info("  Added %s to .env", var)
        return True

    log.info("  .env validated: all critical variables present")
    return True


def parse_compose_ports(compose_file=None):
    """Parse host port mappings from the Podman Compose file.

    Reads dev.yml and extracts the host port from each service's ``ports`` list.
    Handles standard Compose port formats: "host:container", "ip:host:container".

    Returns a dict of {host_port (int): service_name (str)}.
    Falls back to a hardcoded map if YAML parsing is unavailable or fails.
    """
    compose_file = compose_file or DEV_COMPOSE_FILE

    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        log.warning("  PyYAML not installed, using hardcoded port map")
        return _fallback_port_map()

    try:
        with open(compose_file) as f:
            config = yaml.safe_load(f)
    except Exception as exc:
        log.warning("  Failed to parse %s: %s — using hardcoded port map", compose_file, exc)
        return _fallback_port_map()

    port_map = {}
    services = config.get("services", {})
    for service_name, service_config in services.items():
        if not isinstance(service_config, dict):
            continue
        for port_entry in service_config.get("ports", []):
            host_port = _extract_host_port(str(port_entry))
            if host_port is not None:
                port_map[host_port] = service_name

    if not port_map:
        log.warning("  No ports found in %s, using hardcoded port map", compose_file)
        return _fallback_port_map()

    return port_map


def _extract_host_port(port_str):
    """Extract the host port from a Compose port string.

    Supported formats:
      "8080:8080"                → 8080
      "127.0.0.1:8080:8080"     → 8080
      "8080"                     → None (container-only, no host binding to check)
      "${VAR:-8080}:8080"        → 8080 (resolves env var default)
    """
    import re  # noqa: PLC0415

    parts = port_str.strip().strip('"').strip("'").split(":")
    if len(parts) >= 2:
        # "host:container" or "ip:host:container" — host port is parts[-2]
        host_part = parts[-2]
    else:
        # Container-only port, no host mapping to check
        return None

    # Resolve ${VAR:-default} or ${VAR-default} patterns
    match = re.match(r"\$\{[^:}]+(?::?-)([^}]*)\}", host_part)
    if match:
        host_part = match.group(1)

    try:
        return int(host_part)
    except ValueError:
        return None


def _fallback_port_map():
    """Hardcoded port map used when YAML parsing is unavailable."""
    return {
        5432: "db",
        8080: "hbi-web",
        9092: "kafka",
        29092: "kafka",
        4242: "unleash",
        9091: "prometheus-gateway",
        8001: "export-service",
        9099: "minio",
        9991: "minio",
    }


def check_port_conflicts():
    """Check if required ports are free before starting Podman services.

    Parses port mappings dynamically from dev.yml so changes to the Compose
    file are automatically reflected.  Skips the check if Podman services
    are already running (those ports are ours).

    Returns (ok, conflicts_list). ok is False only if there are conflicts
    AND Podman services are not already running.
    """
    port_map = parse_compose_ports()

    # Check if our Podman services are already running
    rc, stdout, _ = run_cmd(
        ["podman", "compose", "-f", DEV_COMPOSE_FILE, "ps", "-q"],
        check=False,
        timeout=10,
    )
    if rc == 0 and stdout.strip():
        running_count = len(stdout.strip().splitlines())
        log.info("  %d Podman containers already running, skipping port check", running_count)
        return True, []

    log.info("  Checking %d ports from dev.yml ...", len(port_map))

    # Services not running — check if ports are free
    conflicts = []
    for port, service in sorted(port_map.items()):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                conflicts.append((port, service))

    if conflicts:
        for port, service in conflicts:
            log.warning("  Port %d in use — needed by %s", port, service)
        log.warning(
            "  %d port conflict(s) detected. Services on these ports may fail to start. "
            "Stop the conflicting processes or use different ports.",
            len(conflicts),
        )
    else:
        log.info("  All %d required ports are free", len(port_map))

    return len(conflicts) == 0, conflicts


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

    # Check .env file
    env_file = Path(PROJECT_DIR) / ".env"
    env_ok = env_file.exists()
    if not env_ok:
        log.warning("  .env file not found (will be created during full setup)")

    # Check for port conflicts
    ports_ok, port_conflicts = check_port_conflicts()

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
    if not env_ok:
        issues.append(".env file missing")
    if not ports_ok:
        conflict_ports = ", ".join(str(p) for p, _ in port_conflicts)
        issues.append(f"port conflicts on {conflict_ports}")
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
            "env_file": str(env_ok),
            "port_conflicts": str(not ports_ok),
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

    log.info("[1/10] Checking prerequisites ...")
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

    log.info("[2/10] Setting up directories ...")
    results["directories"] = {"ok": setup_directories()}

    log.info("[3/10] Initializing git submodules ...")
    results["submodules"] = {"ok": init_submodules()}

    log.info("[4/10] Checking /etc/hosts ...")
    results["hosts_file"] = {"ok": check_hosts_file()}

    log.info("[5/10] Bootstrapping .env file ...")
    results["env_file"] = {"ok": bootstrap_env_file()}

    log.info("[6/10] Installing Python dependencies ...")
    results["dependencies"] = {"ok": install_dependencies()}

    log.info("[7/10] Checking for port conflicts ...")
    ports_ok, port_conflicts = check_port_conflicts()
    results["port_check"] = {"ok": ports_ok, "conflicts": port_conflicts}

    log.info("[8/10] Starting Podman Compose services ...")
    results["podman"] = {"ok": start_podman_services()}

    log.info("[9/10] Waiting for PostgreSQL ...")
    results["postgres"] = {"ok": wait_for_postgres()}

    if results["postgres"]["ok"]:
        log.info("[10/10] Running database migrations ...")
        results["migrations"] = {"ok": run_migrations()}
    else:
        log.warning("[10/10] Skipping migrations (PostgreSQL not ready)")
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
