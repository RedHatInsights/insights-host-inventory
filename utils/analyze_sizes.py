#!/usr/bin/env python3

"""
analyze_sizes.py

This script demonstrates how to analyze the numeric GB values from extract_table_sizes.py
for trend analysis, growth rate calculation, and reporting.

Usage:
    ./analyze_sizes.py [--file <CSV_FILE>] [--table <TABLE_NAME>]
"""

import argparse
import sys
from pathlib import Path

import pandas as pd


def analyze_table_sizes(csv_file, table_filter=None, output_file=None):
    """
    Analyze table size data from the CSV file

    Args:
        csv_file (str): Path to the CSV file
        table_filter (str): Optional table name to filter by
        output_file (str): Optional file to save the report
    """

    # Collect output lines for optional file saving
    output_lines = []

    def output(text=""):
        """Helper function to both print and collect output"""
        print(text)
        output_lines.append(str(text))

    if not Path(csv_file).exists():
        output(f"Error: File '{csv_file}' not found.")
        output("Run extract_table_sizes.py first to generate data.")
        sys.exit(1)

    # Read the data
    df = pd.read_csv(csv_file)

    # Convert timestamp to datetime for better analysis
    df["query_timestamp"] = pd.to_datetime(df["query_timestamp"])

    # Filter by table if specified
    if table_filter:
        df = df[df["table_name"] == table_filter]
        if df.empty:
            output(f"No data found for table '{table_filter}'")
            available_tables = pd.read_csv(csv_file)["table_name"].unique()
            output(f"Available tables: {', '.join(available_tables)}")
            sys.exit(1)

    output("HBI Table Size Analysis")
    output("=======================")
    output()

    # Basic statistics
    output("Dataset Overview:")
    output(f"- Total measurements: {len(df)}")
    output(f"- Tables tracked: {', '.join(df['table_name'].unique())}")
    output(f"- Date range: {df['query_timestamp'].min()} to {df['query_timestamp'].max()}")
    output(f"- Measurement span: {(df['query_timestamp'].max() - df['query_timestamp'].min()).days} days")
    output()

    # Latest sizes per table
    output("Latest Table Sizes (GB):")
    output("-" * 50)
    latest_data = df.loc[df.groupby("table_name")["query_timestamp"].idxmax()]
    for _, row in latest_data.iterrows():
        output(f"{row['table_name']:30} {row['total_size_gb']:>8.3f} GB")
        output(f"  ├─ Heap:    {row['heap_size_gb']:>8.3f} GB")
        output(f"  ├─ Toast:   {row['toast_size_gb']:>8.3f} GB")
        output(f"  └─ Indexes: {row['indexes_size_gb']:>8.3f} GB")
    output()

    # Total database size
    total_db_size = latest_data["total_size_gb"].sum()
    output(f"Total Database Size: {total_db_size:.3f} GB")
    output()

    # Growth analysis (if we have multiple measurements)
    if len(df["query_timestamp"].unique()) > 1:
        output("Growth Analysis:")
        output("-" * 50)

        for table_name in df["table_name"].unique():
            table_data = df[df["table_name"] == table_name].sort_values("query_timestamp")

            if len(table_data) > 1:
                first_measurement = table_data.iloc[0]
                latest_measurement = table_data.iloc[-1]

                total_growth = latest_measurement["total_size_gb"] - first_measurement["total_size_gb"]
                growth_percentage = (total_growth / first_measurement["total_size_gb"]) * 100

                time_span = (
                    latest_measurement["query_timestamp"] - first_measurement["query_timestamp"]
                ).total_seconds() / (24 * 3600)  # days

                output(f"{table_name}:")
                output(f"  Growth: {total_growth:+.3f} GB ({growth_percentage:+.2f}%)")
                if time_span > 0:
                    daily_growth = total_growth / time_span
                    output(f"  Daily avg: {daily_growth:+.6f} GB/day")
                output()

    # Size breakdown analysis
    output("Size Composition Analysis:")
    output("-" * 50)
    for table_name in latest_data["table_name"]:
        row = latest_data[latest_data["table_name"] == table_name].iloc[0]
        total = row["total_size_gb"]

        heap_pct = (row["heap_size_gb"] / total) * 100
        toast_pct = (row["toast_size_gb"] / total) * 100
        indexes_pct = (row["indexes_size_gb"] / total) * 100

        output(f"{table_name}:")
        output(f"  Heap:    {heap_pct:5.1f}% ({row['heap_size_gb']:6.3f} GB)")
        output(f"  Toast:   {toast_pct:5.1f}% ({row['toast_size_gb']:6.3f} GB)")
        output(f"  Indexes: {indexes_pct:5.1f}% ({row['indexes_size_gb']:6.3f} GB)")
        output()

    # Save to file if output_file is specified
    if output_file:
        with open(output_file, "w") as f:
            f.write("\n".join(output_lines))
        output(f"\nReport saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Analyze table size data from extract_table_sizes.py output")
    parser.add_argument(
        "--file", default="hbi_table_sizes.csv", help="CSV file to analyze (default: hbi_table_sizes.csv)"
    )
    parser.add_argument("--table", help="Filter analysis to specific table name")
    parser.add_argument("--output", help="Save analysis report to file (optional)")

    args = parser.parse_args()

    try:
        analyze_table_sizes(args.file, args.table, args.output)
    except KeyboardInterrupt:
        print("\nAnalysis interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"Error during analysis: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
