#!/usr/bin/env python3

"""
extract_table_sizes.py

This script extracts size information for HBI database tables using the GABI endpoint
and exports the results to a CSV file using pandas.

The script queries the following tables:
- hbi.hosts
- hbi.system_profiles_static
- hbi.system_profiles_dynamic

By default, results are APPENDED to the output file for tracking changes over time.
Use --overwrite to replace the file instead.

Usage:
    ./extract_table_sizes.py [--env {prod,stage}] [--auth <AUTH_TOKEN>] [--output <CSV_FILE>] [--overwrite]
    ./extract_table_sizes.py --url <API_ENDPOINT_URL> [--auth <AUTH_TOKEN>] [--output <CSV_FILE>] [--overwrite]
"""

import argparse
import contextlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd


def run_gabi_query(table_name, env=None, url=None, auth=None):
    """
    Execute a size query for a specific table using run_gabi_interactive.py

    Args:
        table_name (str): The fully qualified table name (e.g., 'hbi.hosts')
        env (str): Environment ('prod' or 'stage')
        url (str): API URL (if provided, overrides env)
        auth (str): Auth token (if not provided, uses oc)

    Returns:
        dict: Parsed JSON response from GABI API
    """

    # SQL query template - all sizes returned in GB as numeric values
    query = f"""
SELECT
    ROUND(SUM(pg_relation_size(relid))::numeric / 1073741824, 3) AS heap_size_gb,
    ROUND(SUM(pg_table_size(relid) - pg_relation_size(relid))::numeric / 1073741824, 3) AS toast_size_gb,
    ROUND(SUM(pg_indexes_size(relid))::numeric / 1073741824, 3) AS indexes_size_gb,
    ROUND(SUM(pg_total_relation_size(relid))::numeric / 1073741824, 3) AS total_size_gb
FROM
    pg_partition_tree('{table_name}');
"""

    # Create temporary file with query
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as temp_file:
        temp_file.write(query.strip())
        temp_file_path = temp_file.name

    try:
        # Build command to run gabi script
        script_path = Path(__file__).parent / "run_gabi_interactive.py"
        cmd = [sys.executable, str(script_path), "--file", temp_file_path, "--format", "json"]

        if url:
            cmd.extend(["--url", url])
        elif env:
            cmd.extend(["--env", env])

        if auth:
            cmd.extend(["--auth", auth])

        print(f"Querying {table_name}...")

        # Execute the command
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Parse JSON output
        # The script prints other text, so we need to extract just the JSON part
        output_lines = result.stdout.strip().split("\n")
        json_started = False
        json_lines = []

        for line in output_lines:
            if line.strip().startswith("{"):
                json_started = True
            if json_started:
                json_lines.append(line)

        if not json_lines:
            raise ValueError(f"No JSON response found for {table_name}")

        json_text = "\n".join(json_lines)
        response_data = json.loads(json_text)

        # Check for API errors
        if response_data.get("error"):
            raise RuntimeError(f"API Error for {table_name}: {response_data['error']}")

        return response_data

    except subprocess.CalledProcessError as e:
        print(f"Error running GABI query for {table_name}:")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        raise

    except (json.JSONDecodeError, ValueError) as e:
        print(f"Error parsing JSON response for {table_name}: {e}")
        print(f"Raw output: {result.stdout}")
        raise

    finally:
        # Clean up temporary file
        with contextlib.suppress(OSError):
            os.unlink(temp_file_path)


def parse_size_result(response_data, table_name):
    """
    Parse the GABI response into a structured format

    Args:
        response_data (dict): JSON response from GABI
        table_name (str): Table name for reference

    Returns:
        dict: Structured size data
    """
    result_data = response_data.get("result", [])

    if not result_data or len(result_data) < 2:
        raise ValueError(f"Unexpected result format for {table_name}")

    headers = result_data[0]
    values = result_data[1] if len(result_data) > 1 else [None] * len(headers)

    # Create a dictionary mapping headers to values
    size_data = dict(zip(headers, values, strict=True))
    size_data["table_name"] = table_name
    size_data["query_timestamp"] = datetime.now().isoformat()

    return size_data


def main():
    parser = argparse.ArgumentParser(description="Extract size information for HBI tables and export to CSV")
    parser.add_argument("--env", choices=["prod", "stage"], help="Environment to target ('prod' or 'stage')")
    parser.add_argument("--url", help="API endpoint URL (overrides --env)")
    parser.add_argument("--auth", help="Auth token (if not provided, uses `oc whoami -t`)")
    parser.add_argument(
        "--output", default="hbi_table_sizes.csv", help="Output CSV file name (default: hbi_table_sizes.csv)"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output file instead of appending to it (default: append)",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.url and not args.env:
        parser.error("Either --url or --env must be provided")

    # Define tables to query
    tables = ["hbi.hosts", "hbi.system_profiles_static", "hbi.system_profiles_dynamic"]

    all_data = []

    try:
        # Query each table
        for table in tables:
            try:
                response = run_gabi_query(table_name=table, env=args.env, url=args.url, auth=args.auth)

                size_data = parse_size_result(response, table)
                all_data.append(size_data)

                print(f"✓ Successfully queried {table}")

            except Exception as e:
                print(f"✗ Failed to query {table}: {e}")
                # Continue with other tables
                continue

        if not all_data:
            print("No data collected. Exiting.")
            sys.exit(1)

        # Create DataFrame with new data
        new_df = pd.DataFrame(all_data)

        # Reorder columns for better readability
        column_order = [
            "table_name",
            "heap_size_gb",
            "toast_size_gb",
            "indexes_size_gb",
            "total_size_gb",
            "query_timestamp",
        ]

        # Only include columns that exist in the data
        available_columns = [col for col in column_order if col in new_df.columns]
        new_df = new_df[available_columns]

        # Handle CSV output (append vs overwrite)
        output_path = Path(args.output)

        if output_path.exists() and not args.overwrite:
            print(f"\nAppending to existing file: {args.output}")
            try:
                # Read existing data
                existing_df = pd.read_csv(args.output)

                # Ensure column compatibility
                if list(existing_df.columns) != list(new_df.columns):
                    print("Warning: Column structure has changed. Aligning columns...")
                    # Get union of all columns, preserving order
                    all_columns = list(existing_df.columns)
                    for col in new_df.columns:
                        if col not in all_columns:
                            all_columns.append(col)

                    # Reindex both dataframes to have same columns
                    existing_df = existing_df.reindex(columns=all_columns)
                    new_df = new_df.reindex(columns=all_columns)

                # Combine dataframes
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)

                print(f"Appended {len(new_df)} new records to {len(existing_df)} existing records")

            except Exception as e:
                print(f"Warning: Could not read existing CSV file: {e}")
                print("Creating new file instead...")
                combined_df = new_df
        else:
            if args.overwrite:
                print(f"\nOverwriting file: {args.output}")
            else:
                print(f"\nCreating new file: {args.output}")
            combined_df = new_df

        # Export to CSV
        combined_df.to_csv(args.output, index=False)

        print(f"\nResults exported to: {args.output}")
        print(f"Total records in file: {len(combined_df)}")
        print(f"New records added this run: {len(all_data)}")

        # Display summary of new data
        print("\nNew data summary:")
        print(new_df.to_string(index=False))

    except KeyboardInterrupt:
        print("\nOperation interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
