#!/usr/bin/env python3
"""
run_gabi.py

This script allows you to send SQL queries to an GABI endpoint.

Usage:
    ./run_gabi.py --url <API_ENDPOINT_URL> [--file <SQL_QUERY_FILE>] [--auth <AUTH_TOKEN>]

Examples:
1. Send a query without authentication and url, using `oc whoami`:
    oc login --token=my_auth_token --server=https://api.example.com
    ./run_gabi.py --app my_app
    Enter your SQL query (Ctrl+D to submit):
    SELECT COUNT(*) FROM hbi.hosts;

2. Send a query from a file:
    ./run_gabi.py --url https://gabi-host-inventory-stage.example.com/query --file query.sql --auth my_auth_token

3. Send a query from stdin:
    ./run_gabi.py --url https://gabi-host-inventory-stage.example.com/query --auth my_auth_token
    Enter your SQL query (Ctrl+D to submit):
    SELECT COUNT(*) FROM hbi.hosts;

Arguments:
    --app   (Optional) Name of the application. Defaults to "host-inventory-prod".
    --url   (Optional) The API endpoint URL to send the query to. Defaults to `oc whoami --show-server`.
    --file  (Optional) Path to a file containing the SQL query. If not provided, the query will be read from stdin.
    --auth  (Optional) Bearer token for API authentication. Defaults to `oc whoami -t`.
"""

import argparse
import json
import subprocess
import sys

import requests

DEFAULT_APP = "host-inventory-prod"


def get_oc_token():
    """Retrieve the OpenShift token using `oc whoami -t`."""
    try:
        return subprocess.check_output(["oc", "whoami", "-t"], text=True).strip()
    except subprocess.CalledProcessError:
        print("Failed to retrieve token using `oc whoami -t`. Please provide the --auth argument.")
        sys.exit(1)


def get_oc_server():
    """Retrieve the OpenShift server URL using `oc whoami --show-server`."""
    try:
        return subprocess.check_output(["oc", "whoami", "--show-server"], text=True).strip()
    except subprocess.CalledProcessError:
        print("Failed to retrieve server URL using `oc whoami --show-server`. Please provide the --url argument.")
        sys.exit(1)


def get_url_from_oc_server(app_name=DEFAULT_APP):
    """Get the API URL from the OpenShift server URL."""
    server_url = get_oc_server()
    if not server_url:
        print("No server URL found. Please provide the --url argument.")
        sys.exit(1)

    server_url = server_url.replace("https://api.", f"https://gabi-{app_name}.apps.", 1)

    api_url = f"{server_url}/query"
    return api_url


def main():
    parser = argparse.ArgumentParser(description="Send SQL queries to an API")
    parser.add_argument("--app", help="Name of the application (if not provided, uses DEFAULT_APP)")
    parser.add_argument(
        "--url",
        help=(
            "API endpoint URL (if not provided, uses `oc whoami --show-server` "
            "and assumes default app, or you can provide --app)"
        ),
    )
    parser.add_argument("--file", help="File containing the SQL query (if not provided, reads from stdin)")
    parser.add_argument("--auth", help="Token to authenticate with the API (if not provided, uses `oc whoami -t`)")
    args = parser.parse_args()

    # Use `oc whoami --show-server` if --url is not provided
    api_url = args.url if args.url else get_url_from_oc_server()

    # Use `oc whoami -t` if --auth is not provided
    auth_token = args.auth if args.auth else get_oc_token()

    # Read query from file or stdin
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            query = f.read().strip()
    else:
        print("Enter your SQL query (Ctrl+D to submit):")
        query = sys.stdin.read().strip()

    # Prepare headers
    headers = {"Content-Type": "application/json"}
    headers["Authorization"] = f"Bearer {auth_token}"

    # Send query to API
    payload = {"query": query}
    try:
        response = requests.post(api_url, json=payload, headers=headers)
        if response.status_code == 200:
            print(json.dumps(response.json(), indent=2))
        else:
            print(f"Error {response.status_code}: {response.text}")
            sys.exit(response.status_code)
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
