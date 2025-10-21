#!/usr/bin/env python3

"""
run_gabi.py

This script allows you to send SQL queries to a GABI endpoint interactively
and displays the results in a formatted table with text wrapping for long lines.

Usage:
    # Auto-derive URL from oc server and env (default prod)
    ./run_gabi_interactive.py [--env {prod,stage}] [--auth <AUTH_TOKEN>] \
        [--interactive] [--format {table,json,both}]

    # Explicit URL override
    ./run_gabi_interactive.py --url <API_ENDPOINT_URL> [--auth <AUTH_TOKEN>] \
        [--interactive] [--format {table,json,both}]

    # Non-interactive modes
    #  - from file
    ./run_gabi_interactive.py [--env {prod,stage}] --file query.sql [--auth <AUTH_TOKEN>] \
        [--format {table,json,both}]
    #  - from stdin
    cat query.sql | ./run_gabi_interactive.py [--env {prod,stage}] [--auth <AUTH_TOKEN>] \
        [--format {table,json,both}]

The script runs in a loop. To submit a query, press Enter on an empty line.
To exit, type 'exit' or 'quit' and press Enter.
"""

import argparse
import json
import re
import subprocess
import sys
import textwrap

import requests
from tabulate import tabulate


def get_oc_token():
    """Retrieve the OpenShift token using `oc whoami -t`."""
    try:
        return subprocess.check_output(["oc", "whoami", "-t"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Failed to retrieve token using `oc`. Please provide the --auth argument.")
        sys.exit(1)


def get_oc_server():
    """Retrieve the OpenShift server URL using `oc whoami --show-server`."""
    try:
        regex = r":[^:]*$"
        return re.sub(
            regex,
            "",
            subprocess.check_output(["oc", "whoami", "--show-server"], text=True).strip(),
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Failed to retrieve server URL using `oc`. Please provide the --url argument.")
        sys.exit(1)


def get_url_from_oc_server(app_name):
    """Get the API URL from the OpenShift server URL."""
    server_url = get_oc_server()
    if not server_url:
        print("No server URL found. Please provide the --url argument.")
        sys.exit(1)

    server_url = server_url.replace("https://api.", f"https://gabi-{app_name}.apps.", 1)
    return f"{server_url}/query"


def display_results_as_table(data):
    """Formats and prints the JSON response as a pretty table with text wrapping."""
    try:
        if not isinstance(data, list) or len(data) < 2 or not isinstance(data[0], list):
            print("Response data is not in the expected format for table display.")
            print(json.dumps(data, indent=2))
            return

        headers = data[0]
        rows = data[1:]

        # --- Text Wrapping Logic ---
        MAX_COL_WIDTH = 45  # Max width for a column before wrapping
        wrapped_rows = []
        for row in rows:
            wrapped_row = [
                textwrap.fill(str(cell), width=MAX_COL_WIDTH) if isinstance(cell, str) else cell for cell in row
            ]
            wrapped_rows.append(wrapped_row)

        print(tabulate(wrapped_rows, headers=headers, tablefmt="psql"))

    except (IndexError, TypeError) as e:
        print(f"Failed to parse the response into a table: {e}")
        print("Raw data:")
        print(json.dumps(data, indent=2))


def get_multiline_query():
    """Reads multiple lines of input until an empty line is entered."""
    print("\nEnter your SQL query (press Enter on an empty line to submit):")
    lines = []
    while True:
        try:
            line = input()
            if not line:
                break
            lines.append(line)
        except EOFError:
            break
    return " ".join(lines).strip()


def main():
    parser = argparse.ArgumentParser(description="Send SQL queries to an API and display results as a table.")
    parser.add_argument(
        "--env",
        choices=["prod", "stage"],
        help="Environment to target ('prod' -> host-inventory-prod, 'stage' -> host-inventory-stage)",
    )
    parser.add_argument(
        "--url",
        help=(
            "API endpoint URL (if not provided, uses `oc whoami --show-server` and assumes default app based on --env)"
        ),
    )
    parser.add_argument("--file", help="File containing the SQL query (non-interactive mode)")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive REPL mode for entering multiple queries",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json", "both"],
        default="table",
        help="Output format: pretty table, raw JSON, or both (default: table)",
    )
    parser.add_argument("--auth", help="Token to authenticate with the API (if not provided, uses `oc whoami -t`)")
    args = parser.parse_args()

    selected_app = "host-inventory-stage" if args.env == "stage" else "host-inventory-prod"

    api_url = args.url or get_url_from_oc_server(selected_app)
    auth_token = args.auth or get_oc_token()
    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}

    def send_query_once(query: str) -> bool:
        print(f"\nSending query to {api_url}...")
        payload = {"query": query}
        try:
            response = requests.post(api_url, json=payload, headers=headers)
            response.raise_for_status()

            response_json = response.json()

            api_error = response_json.get("error")

            success = True
            if api_error:
                success = False
                # For JSON output, still show the full payload
                if args.format != "json":
                    print(f"\nAPI Error: {api_error}")

            # Decide output per requested format
            if args.format in ("table", "both"):
                if "result" in response_json:
                    print("\nQuery successful. Result:\n")
                    display_results_as_table(response_json["result"])
                else:
                    print("\nResponse received, but 'result' key was not found for table output.")

            if args.format in ("json", "both"):
                print("\nFull JSON response:\n")
                print(json.dumps(response_json, indent=2))

            return success
        except requests.exceptions.HTTPError as e:
            print(f"\nHTTP Error {e.response.status_code}: {e.response.text}")
            return False
        except requests.exceptions.RequestException as e:
            print(f"\nRequest failed: {e}")
            return False
        except json.JSONDecodeError:
            print("\nFailed to decode JSON from response.")
            print(f"Raw response text: {response.text}")
            return False

    if args.interactive:
        print(f"Connected to {api_url}")
        print("Type 'exit' or 'quit' to end the session.")

        while True:
            query = get_multiline_query()

            if not query:
                continue

            if query.lower() in ["exit", "quit"]:
                break

            send_query_once(query)

        print("Goodbye!")
        return

    # Non-interactive path
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            query = f.read().strip()
    else:
        if sys.stdin.isatty():
            print("Enter your SQL query (Ctrl+D to submit):")
        query = sys.stdin.read().strip()

    if not query:
        print("No query provided. Use --file, pipe a query via stdin, or use --interactive.")
        sys.exit(1)

    ok = send_query_once(query)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(130)
