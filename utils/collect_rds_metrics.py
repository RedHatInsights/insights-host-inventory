#!/usr/bin/env python3

"""
collect_rds_metrics.py

This script collects peak metrics from AWS CloudWatch for the host-inventory-prod RDS instance.
Collects data for every Tuesday starting from January 1st, 2026.

Metrics collected:
- CPU Utilization (peak percentage)
- Total IOPS (peak read + write IOPS combined)
- Memory Usage (calculated from freeable memory)

AWS Authentication:
- Red Hat employees: Use `rh-aws-saml-login --profile production-account` before running
- Standard setup: Use `aws configure` to set up credentials

Usage:
    # Red Hat employees (recommended)
    rh-aws-saml-login --profile production-account
    ./collect_rds_metrics.py [--profile production-account]

    # Standard AWS CLI
    ./collect_rds_metrics.py [--db-instance <DB_INSTANCE>] [--output <CSV_FILE>] [--profile <AWS_PROFILE>]
    ./collect_rds_metrics.py --start-date 2026-01-01 --end-date 2026-12-31
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from datetime import timedelta
from pathlib import Path

import pandas as pd


def find_tuesdays(start_date, end_date):
    """
    Find all Tuesdays between start_date and end_date

    Args:
        start_date (datetime): Start date
        end_date (datetime): End date

    Returns:
        list: List of Tuesday dates
    """
    tuesdays = []
    current_date = start_date

    # Find the first Tuesday on or after start_date
    days_until_tuesday = (1 - current_date.weekday()) % 7  # Tuesday is weekday 1
    first_tuesday = current_date + timedelta(days=days_until_tuesday)

    current_tuesday = first_tuesday
    while current_tuesday <= end_date:
        tuesdays.append(current_tuesday.date())
        current_tuesday += timedelta(days=7)  # Add one week

    return tuesdays


def get_cloudwatch_metrics(date, db_instance, aws_profile=None):
    """
    Get CloudWatch metrics for a specific date

    Args:
        date: The date to query (datetime.date object)
        db_instance (str): RDS instance identifier
        aws_profile (str): AWS profile to use

    Returns:
        dict: Parsed metrics data
    """

    # Convert date to start and end timestamps
    start_time = f"{date}T00:00:00Z"
    end_time = f"{date}T23:59:59Z"

    # Define the metric queries
    metric_queries = [
        # CPU Utilization
        {
            "Id": "cpu",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/RDS",
                    "MetricName": "CPUUtilization",
                    "Dimensions": [{"Name": "DBInstanceIdentifier", "Value": db_instance}],
                },
                "Period": 86400,  # 1 day
                "Stat": "Maximum",
            },
            "Label": "Peak CPU Utilization",
            "ReturnData": True,
        },
        # Read IOPS
        {
            "Id": "read_iops",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/RDS",
                    "MetricName": "ReadIOPS",
                    "Dimensions": [{"Name": "DBInstanceIdentifier", "Value": db_instance}],
                },
                "Period": 86400,
                "Stat": "Maximum",
            },
            "ReturnData": False,
        },
        # Write IOPS
        {
            "Id": "write_iops",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/RDS",
                    "MetricName": "WriteIOPS",
                    "Dimensions": [{"Name": "DBInstanceIdentifier", "Value": db_instance}],
                },
                "Period": 86400,
                "Stat": "Maximum",
            },
            "ReturnData": False,
        },
        # Total IOPS (Read + Write)
        {"Id": "total_iops", "Expression": "read_iops + write_iops", "Label": "Peak Total IOPS", "ReturnData": True},
        # Freeable Memory (to calculate memory usage)
        {
            "Id": "freeable_memory",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/RDS",
                    "MetricName": "FreeableMemory",
                    "Dimensions": [{"Name": "DBInstanceIdentifier", "Value": db_instance}],
                },
                "Period": 86400,
                "Stat": "Minimum",  # Minimum free memory = peak memory usage
            },
            "Label": "Minimum Freeable Memory",
            "ReturnData": True,
        },
        # Database Connections (bonus metric)
        {
            "Id": "db_connections",
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/RDS",
                    "MetricName": "DatabaseConnections",
                    "Dimensions": [{"Name": "DBInstanceIdentifier", "Value": db_instance}],
                },
                "Period": 86400,
                "Stat": "Maximum",
            },
            "Label": "Peak Database Connections",
            "ReturnData": True,
        },
    ]

    # Build AWS CLI command
    cmd = ["aws", "cloudwatch", "get-metric-data"]
    cmd.extend(["--start-time", start_time])
    cmd.extend(["--end-time", end_time])
    cmd.extend(["--metric-data-queries", json.dumps(metric_queries)])

    if aws_profile:
        cmd.extend(["--profile", aws_profile])

    print(f"Collecting metrics for {date}...")

    try:
        # Execute AWS CLI command
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Parse JSON response
        response_data = json.loads(result.stdout)

        # Extract metric values
        metrics = {}
        metrics["date"] = str(date)
        metrics["query_timestamp"] = datetime.now().isoformat()

        for metric_result in response_data.get("MetricDataResults", []):
            metric_id = metric_result["Id"]
            values = metric_result.get("Values", [])

            if values:
                # Take the first (and should be only) value for the day
                value = values[0]

                if metric_id == "cpu":
                    metrics["peak_cpu_utilization_percent"] = round(value, 2)
                elif metric_id == "total_iops":
                    metrics["peak_total_iops"] = round(value, 2)
                elif metric_id == "freeable_memory":
                    # Convert from bytes to GB for easier reading
                    freeable_memory_gb = value / (1024**3)
                    metrics["min_freeable_memory_gb"] = round(freeable_memory_gb, 3)
                elif metric_id == "db_connections":
                    metrics["peak_db_connections"] = int(value)
            else:
                print(f"Warning: No data found for metric '{metric_id}' on {date}")

                # Set default values for missing data
                if metric_id == "cpu":
                    metrics["peak_cpu_utilization_percent"] = None
                elif metric_id == "total_iops":
                    metrics["peak_total_iops"] = None
                elif metric_id == "freeable_memory":
                    metrics["min_freeable_memory_gb"] = None
                elif metric_id == "db_connections":
                    metrics["peak_db_connections"] = None

        return metrics

    except subprocess.CalledProcessError as e:
        print(f"Error running AWS CLI command for {date}:")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        raise

    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response for {date}: {e}")
        print(f"Raw output: {result.stdout}")
        raise


def main():
    parser = argparse.ArgumentParser(description="Collect peak RDS metrics for Tuesdays from AWS CloudWatch")
    parser.add_argument(
        "--db-instance",
        default="host-inventory-prod",
        help="RDS database instance identifier (default: host-inventory-prod)",
    )
    parser.add_argument(
        "--start-date", default="2026-01-01", help="Start date in YYYY-MM-DD format (default: 2026-01-01)"
    )
    parser.add_argument("--end-date", help="End date in YYYY-MM-DD format (default: current date)")
    parser.add_argument(
        "--output", default="rds_tuesday_metrics.csv", help="Output CSV file name (default: rds_tuesday_metrics.csv)"
    )
    parser.add_argument("--profile", help="AWS profile to use (uses default if not specified)")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output file instead of appending to it (default: append)",
    )

    args = parser.parse_args()

    try:
        # Parse dates
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")

        end_date = datetime.strptime(args.end_date, "%Y-%m-%d") if args.end_date else datetime.now()

        # Find all Tuesdays in the date range
        tuesdays = find_tuesdays(start_date, end_date)

        if not tuesdays:
            print("No Tuesdays found in the specified date range.")
            sys.exit(1)

        print(f"Found {len(tuesdays)} Tuesdays between {start_date.date()} and {end_date.date()}")
        print(f"Database instance: {args.db_instance}")
        print()

        # Collect metrics for each Tuesday
        all_metrics = []

        for tuesday in tuesdays:
            try:
                metrics = get_cloudwatch_metrics(tuesday, args.db_instance, args.profile)
                all_metrics.append(metrics)
                print(f"✓ Collected metrics for {tuesday}")

            except Exception as e:
                print(f"✗ Failed to collect metrics for {tuesday}: {e}")
                continue

        if not all_metrics:
            print("No metrics data collected. Exiting.")
            sys.exit(1)

        # Create DataFrame
        new_df = pd.DataFrame(all_metrics)

        # Reorder columns for better readability
        column_order = [
            "date",
            "peak_cpu_utilization_percent",
            "peak_total_iops",
            "min_freeable_memory_gb",
            "peak_db_connections",
            "query_timestamp",
        ]

        available_columns = [col for col in column_order if col in new_df.columns]
        new_df = new_df[available_columns]

        # Handle CSV output (append vs overwrite)
        output_path = Path(args.output)

        if output_path.exists() and not args.overwrite:
            print(f"\nAppending to existing file: {args.output}")
            try:
                # Read existing data
                existing_df = pd.read_csv(args.output)

                # Remove duplicates by date (in case we're re-running for same dates)
                existing_df = existing_df[~existing_df["date"].isin(new_df["date"])]

                # Combine dataframes
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)

                # Sort by date
                combined_df = combined_df.sort_values("date").reset_index(drop=True)

                print(f"Appended {len(new_df)} new records, removed any duplicates")

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
        print(f"New records added this run: {len(all_metrics)}")

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
