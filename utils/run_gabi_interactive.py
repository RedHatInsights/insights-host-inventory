#!/usr/bin/env python3

"""
run_gabi.py

This script allows you to send SQL queries to a GABI endpoint interactively
and displays the results in a formatted table with text wrapping for long lines.

Usage:
    ./run_gabi.py --url <API_ENDPOINT_URL> [--auth <AUTH_TOKEN>]

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

DEFAULT_APP = "host-inventory-prod"


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
        return re.sub(regex, "", subprocess.check_output(["oc", "whoami", "--show-server"], text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Failed to retrieve server URL using `oc`. Please provide the --url argument.")
        sys.exit(1)


def get_url_from_oc_server(app_name=DEFAULT_APP):
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
    parser.add_argument("--app", help="Name of the application (if not provided, uses DEFAULT_APP)")
    parser.add_argument(
        "--url",
        help=(
            "API endpoint URL (if not provided, uses `oc whoami --show-server` "
            "and assumes default app, or you can provide --app)"
        ),
    )
    parser.add_argument("--auth", help="Token to authenticate with the API (if not provided, uses `oc whoami -t`)")
    args = parser.parse_args()

    api_url = args.url or get_url_from_oc_server(args.app or DEFAULT_APP)
    auth_token = args.auth or get_oc_token()
    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}

    print(f"Connected to {api_url}")
    print("Type 'exit' or 'quit' to end the session.")

    while True:
        query = get_multiline_query()

        if not query:
            continue

        if query.lower() in ["exit", "quit"]:
            break

        print(f"\nSending query to {api_url}...")

        payload = {"query": query}
        try:
            response = requests.post(api_url, json=payload, headers=headers)
            response.raise_for_status()

            response_json = response.json()

            api_error = response_json.get("error")
            if api_error:
                print(f"\nAPI Error: {api_error}")
                continue

            if "result" in response_json:
                print("\nQuery successful. Result:\n")
                display_results_as_table(response_json["result"])
            else:
                print("\nResponse received, but 'result' key was not found.")
                print(json.dumps(response_json, indent=2))

        except requests.exceptions.HTTPError as e:
            print(f"\nHTTP Error {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            print(f"\nRequest failed: {e}")
        except json.JSONDecodeError:
            print("\nFailed to decode JSON from response.")
            print(f"Raw response text: {response.text}")

    print("Goodbye!")


if __name__ == "__main__":
    try:
        from tabulate import tabulate
    except ImportError:
        print("The 'tabulate' library is not installed. Please install it with: pip install tabulate")
        sys.exit(1)
    try:
        import requests
    except ImportError:
        print("The 'requests' library is not installed. Please install it with: pip install requests")
        sys.exit(1)

    main()
