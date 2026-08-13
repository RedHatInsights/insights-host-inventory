#!/usr/bin/env python3
"""
Development server with automatic reloading using only standard library.
This script polls for file changes and restarts the Flask application.

Used by dev.yml file - Local DEV Only
"""

import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


class SimpleFileWatcher:
    # Constants
    DEBOUNCE_SECONDS = 2
    PROCESS_TIMEOUT = 5
    POLL_INTERVAL = 1
    IGNORE_PATTERNS = ["__pycache__", ".git", ".pytest_cache"]

    def __init__(self, watch_dir, extensions=(".py", ".yaml", ".yml", ".json")):
        self.watch_dir = Path(watch_dir)
        self.extensions = extensions
        self.file_times = {}
        self.process = None
        self.running = True
        self.restart_count = 0
        self.last_restart = 0
        self.scan_files()

    def _should_watch_file(self, file_path: Path) -> bool:
        """Check if a file should be watched for changes."""
        return (
            file_path.is_file()
            and file_path.suffix in self.extensions
            and not any(ignore == part for part in file_path.parts for ignore in self.IGNORE_PATTERNS)
        )

    def scan_files(self):
        """Scan directory and record file modification times."""
        skipped_files = []
        for file_path in self.watch_dir.rglob("*"):
            if self._should_watch_file(file_path):
                try:
                    self.file_times[str(file_path)] = file_path.stat().st_mtime
                except (OSError, PermissionError):
                    skipped_files.append(str(file_path))
        if skipped_files:
            print(
                f"[dev_server] Skipped {len(skipped_files)} files due to permission errors: "
                f"{', '.join(skipped_files[:5])}{'...' if len(skipped_files) > 5 else ''}"
            )

    def check_changes(self):
        """Check for file changes by comparing modification times."""
        changed_files = []
        current_files = {}

        # Check existing files for changes
        for file_path in self.watch_dir.rglob("*"):
            if self._should_watch_file(file_path):
                with contextlib.suppress(OSError, PermissionError):
                    file_str = str(file_path)
                    current_mtime = file_path.stat().st_mtime
                    current_files[file_str] = current_mtime

                    # Check if file is new or modified
                    if file_str not in self.file_times or current_mtime != self.file_times[file_str]:
                        changed_files.append(file_str)

        # Check for deleted files
        for file_str in self.file_times:
            if file_str not in current_files:
                changed_files.append(file_str)

        self.file_times = current_files
        return changed_files

    def restart_server(self, changed_file=None):
        """Restart the Flask server."""
        current_time = time.time()

        # Debounce rapid changes
        if current_time - self.last_restart < self.DEBOUNCE_SECONDS:
            return

        self.last_restart = current_time
        self.restart_count += 1

        if self.process:
            print("Stopping Flask server...")
            self.process.terminate()
            try:
                self.process.wait(timeout=self.PROCESS_TIMEOUT)
            except subprocess.TimeoutExpired:
                print("Force killing Flask server...")
                self.process.kill()
                self.process.wait()

        if changed_file:
            print(f"File changed: {changed_file}")

        print(f"Starting Flask server (restart #{self.restart_count})...")
        env = os.environ.copy()
        env["FLASK_ENV"] = "development"
        env["FLASK_DEBUG"] = "1"

        self.process = subprocess.Popen(
            ["python3", "run.py"],
            env=env,
            cwd="/opt/app-root/src",
            shell=False,  # Explicitly disable shell for security
        )

    def watch(self):
        """Main watching loop."""
        self.restart_server()  # Initial start

        while self.running:
            try:
                changed_files = self.check_changes()
                if changed_files:
                    # Only restart once even if multiple files changed
                    self.restart_server(changed_files[0])
                time.sleep(self.POLL_INTERVAL)
            except KeyboardInterrupt:
                break
            except (OSError, PermissionError, FileNotFoundError) as e:
                print(f"File system error during watching: {e}")
                time.sleep(self.POLL_INTERVAL)
            except Exception as e:
                print(f"Unexpected error during file watching: {e}")
                time.sleep(self.POLL_INTERVAL)

    def stop(self):
        """Stop the watcher and Flask server."""
        self.running = False
        if self.process:
            print("Shutting down Flask server...")
            self.process.terminate()
            try:
                self.process.wait(timeout=self.PROCESS_TIMEOUT)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


# Global instance for signal handling
_watcher_instance = None


def signal_handler(_signum, _frame):
    """Handle shutdown signals gracefully."""
    print("\n Received shutdown signal...")
    if _watcher_instance:
        _watcher_instance.stop()
    sys.exit(0)


if __name__ == "__main__":
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    watch_dir = "/opt/app-root/src"
    print(f"Starting simple file watcher for {watch_dir}")
    print("Polling for changes every second...")
    print("Press Ctrl+C to stop")

    # Set global instance for signal handler
    _watcher_instance = SimpleFileWatcher(watch_dir)

    try:
        _watcher_instance.watch()
    except KeyboardInterrupt:
        pass
    finally:
        if _watcher_instance:
            _watcher_instance.stop()
        print("Development server stopped")
