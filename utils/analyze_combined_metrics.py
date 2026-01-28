#!/usr/bin/env python3

"""
analyze_combined_metrics.py

This script provides comprehensive analysis combining table size data and RDS performance metrics
to identify correlations between database growth and performance impacts.

Usage:
    ./analyze_combined_metrics.py [--sizes-file <CSV>] [--metrics-file <CSV>] [--output-report <FILE>]
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


def load_and_validate_data(sizes_file, metrics_file):
    """
    Load and validate both datasets

    Args:
        sizes_file (str): Path to table sizes CSV
        metrics_file (str): Path to RDS metrics CSV

    Returns:
        tuple: (sizes_df, metrics_df) or raises exception
    """

    # Load table sizes data
    if not Path(sizes_file).exists():
        print(f"Error: Table sizes file '{sizes_file}' not found.")
        print("Run extract_table_sizes.py first to generate size data.")
        sys.exit(1)

    sizes_df = pd.read_csv(sizes_file)
    sizes_df["query_timestamp"] = pd.to_datetime(sizes_df["query_timestamp"])
    sizes_df["date"] = sizes_df["query_timestamp"].dt.date

    # Load RDS metrics data
    if not Path(metrics_file).exists():
        print(f"Error: RDS metrics file '{metrics_file}' not found.")
        print("Run collect_rds_metrics.py first to generate metrics data.")
        sys.exit(1)

    metrics_df = pd.read_csv(metrics_file)
    metrics_df["date"] = pd.to_datetime(metrics_df["date"]).dt.date
    metrics_df["query_timestamp"] = pd.to_datetime(metrics_df["query_timestamp"])

    print(f"Loaded {len(sizes_df)} table size measurements")
    print(f"Loaded {len(metrics_df)} RDS metric measurements")

    return sizes_df, metrics_df


def analyze_size_trends(sizes_df):
    """
    Analyze table size trends over time

    Args:
        sizes_df (pd.DataFrame): Table sizes dataframe

    Returns:
        dict: Analysis results
    """

    analysis = {}

    # Get latest sizes per table
    latest_sizes = sizes_df.loc[sizes_df.groupby("table_name")["query_timestamp"].idxmax()]

    # Calculate total database size
    analysis["total_db_size_gb"] = latest_sizes["total_size_gb"].sum()
    analysis["largest_table"] = latest_sizes.loc[latest_sizes["total_size_gb"].idxmax(), "table_name"]
    analysis["largest_table_size_gb"] = latest_sizes["total_size_gb"].max()

    # Calculate growth rates if we have multiple measurements
    growth_rates = {}
    for table in sizes_df["table_name"].unique():
        table_data = sizes_df[sizes_df["table_name"] == table].sort_values("query_timestamp")

        if len(table_data) > 1:
            first_size = table_data.iloc[0]["total_size_gb"]
            latest_size = table_data.iloc[-1]["total_size_gb"]
            days_span = (table_data.iloc[-1]["query_timestamp"] - table_data.iloc[0]["query_timestamp"]).days

            if days_span > 0 and first_size > 0:
                growth_gb = latest_size - first_size
                growth_percent = (growth_gb / first_size) * 100
                daily_growth = growth_gb / days_span

                growth_rates[table] = {
                    "growth_gb": growth_gb,
                    "growth_percent": growth_percent,
                    "daily_growth_gb": daily_growth,
                    "days_span": days_span,
                }

    analysis["growth_rates"] = growth_rates

    return analysis


def analyze_performance_trends(metrics_df):
    """
    Analyze RDS performance trends

    Args:
        metrics_df (pd.DataFrame): RDS metrics dataframe

    Returns:
        dict: Performance analysis results
    """

    analysis = {}

    # Basic statistics
    analysis["avg_cpu_utilization"] = metrics_df["peak_cpu_utilization_percent"].mean()
    analysis["max_cpu_utilization"] = metrics_df["peak_cpu_utilization_percent"].max()
    analysis["avg_total_iops"] = metrics_df["peak_total_iops"].mean()
    analysis["max_total_iops"] = metrics_df["peak_total_iops"].max()
    analysis["avg_freeable_memory_gb"] = metrics_df["min_freeable_memory_gb"].mean()
    analysis["min_freeable_memory_gb"] = metrics_df["min_freeable_memory_gb"].min()

    # Identify concerning metrics
    high_cpu_days = metrics_df[metrics_df["peak_cpu_utilization_percent"] > 80]
    high_iops_days = metrics_df[metrics_df["peak_total_iops"] > metrics_df["peak_total_iops"].quantile(0.95)]
    low_memory_days = metrics_df[metrics_df["min_freeable_memory_gb"] < 1.0]

    analysis["high_cpu_count"] = len(high_cpu_days)
    analysis["high_iops_count"] = len(high_iops_days)
    analysis["low_memory_count"] = len(low_memory_days)

    return analysis


def find_correlations(sizes_df, metrics_df):
    """
    Find correlations between table sizes and performance metrics

    Args:
        sizes_df (pd.DataFrame): Table sizes dataframe
        metrics_df (pd.DataFrame): RDS metrics dataframe

    Returns:
        dict: Correlation analysis results
    """

    # Aggregate table sizes by date
    daily_sizes = sizes_df.groupby("date").agg({"total_size_gb": "sum"}).reset_index()

    # Merge with performance metrics
    merged_df = pd.merge(daily_sizes, metrics_df, on="date", how="inner")

    if len(merged_df) == 0:
        return {"error": "No overlapping dates found between size and performance data"}

    correlations = {}

    # Calculate correlations
    if len(merged_df) > 2:  # Need at least 3 points for meaningful correlation
        correlations["size_vs_cpu"] = merged_df["total_size_gb"].corr(merged_df["peak_cpu_utilization_percent"])
        correlations["size_vs_iops"] = merged_df["total_size_gb"].corr(merged_df["peak_total_iops"])
        correlations["size_vs_memory"] = merged_df["total_size_gb"].corr(merged_df["min_freeable_memory_gb"])

    correlations["overlapping_dates"] = len(merged_df)
    correlations["date_range"] = f"{merged_df['date'].min()} to {merged_df['date'].max()}"

    return correlations


def generate_report(sizes_analysis, performance_analysis, correlations, output_file=None):
    """
    Generate a comprehensive analysis report

    Args:
        sizes_analysis (dict): Table size analysis results
        performance_analysis (dict): Performance analysis results
        correlations (dict): Correlation analysis results
        output_file (str): Optional file to save the report
    """

    report_lines = []

    report_lines.append("HBI Database Analysis Report")
    report_lines.append("=" * 50)
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")

    # Table Size Analysis
    report_lines.append("TABLE SIZE ANALYSIS")
    report_lines.append("-" * 30)
    report_lines.append(f"Total Database Size: {sizes_analysis['total_db_size_gb']:.3f} GB")
    report_lines.append(
        f"Largest Table: {sizes_analysis['largest_table']} ({sizes_analysis['largest_table_size_gb']:.3f} GB)"
    )
    report_lines.append("")

    if sizes_analysis["growth_rates"]:
        report_lines.append("Growth Rates by Table:")
        for table, growth in sizes_analysis["growth_rates"].items():
            report_lines.append(f"  {table}:")
            report_lines.append(f"    Total Growth: {growth['growth_gb']:+.3f} GB ({growth['growth_percent']:+.2f}%)")
            report_lines.append(f"    Daily Average: {growth['daily_growth_gb']:+.6f} GB/day")
            report_lines.append(f"    Time Span: {growth['days_span']} days")
    report_lines.append("")

    # Performance Analysis
    report_lines.append("PERFORMANCE ANALYSIS")
    report_lines.append("-" * 30)
    report_lines.append(f"Average CPU Utilization: {performance_analysis['avg_cpu_utilization']:.2f}%")
    report_lines.append(f"Peak CPU Utilization: {performance_analysis['max_cpu_utilization']:.2f}%")
    report_lines.append(f"Average Total IOPS: {performance_analysis['avg_total_iops']:.1f}")
    report_lines.append(f"Peak Total IOPS: {performance_analysis['max_total_iops']:.1f}")
    report_lines.append(f"Average Freeable Memory: {performance_analysis['avg_freeable_memory_gb']:.3f} GB")
    report_lines.append(f"Minimum Freeable Memory: {performance_analysis['min_freeable_memory_gb']:.3f} GB")
    report_lines.append("")

    # Performance Alerts
    report_lines.append("Performance Alerts:")
    if performance_analysis["high_cpu_count"] > 0:
        report_lines.append(f"  ⚠️  High CPU days (>80%): {performance_analysis['high_cpu_count']}")
    if performance_analysis["high_iops_count"] > 0:
        report_lines.append(f"  ⚠️  High IOPS days (95th percentile): {performance_analysis['high_iops_count']}")
    if performance_analysis["low_memory_count"] > 0:
        report_lines.append(f"  ⚠️  Low memory days (<1GB free): {performance_analysis['low_memory_count']}")

    if (
        performance_analysis["high_cpu_count"] == 0
        and performance_analysis["high_iops_count"] == 0
        and performance_analysis["low_memory_count"] == 0
    ):
        report_lines.append("  ✅ No performance alerts detected")
    report_lines.append("")

    # Correlation Analysis
    report_lines.append("CORRELATION ANALYSIS")
    report_lines.append("-" * 30)

    if "error" in correlations:
        report_lines.append(f"Error: {correlations['error']}")
    else:
        report_lines.append(f"Analysis based on {correlations['overlapping_dates']} overlapping dates")
        report_lines.append(f"Date range: {correlations['date_range']}")
        report_lines.append("")

        if "size_vs_cpu" in correlations:
            report_lines.append("Correlation Coefficients:")
            report_lines.append(f"  Database Size vs CPU Utilization: {correlations['size_vs_cpu']:.3f}")
            report_lines.append(f"  Database Size vs Total IOPS: {correlations['size_vs_iops']:.3f}")
            report_lines.append(f"  Database Size vs Freeable Memory: {correlations['size_vs_memory']:.3f}")
            report_lines.append("")

            # Interpret correlations
            report_lines.append("Interpretation:")

            cpu_corr = correlations["size_vs_cpu"]
            if cpu_corr > 0.7:
                report_lines.append(
                    "  🔴 Strong positive correlation: Database growth significantly increases CPU usage"
                )
            elif cpu_corr > 0.3:
                report_lines.append("  🟡 Moderate positive correlation: Database growth somewhat increases CPU usage")
            elif cpu_corr < -0.3:
                report_lines.append("  🟢 Negative correlation: Database growth decreases CPU usage (unusual)")
            else:
                report_lines.append("  🟢 Weak correlation: Database size has minimal impact on CPU usage")

    report_lines.append("")

    # Recommendations
    report_lines.append("RECOMMENDATIONS")
    report_lines.append("-" * 20)

    if performance_analysis["max_cpu_utilization"] > 85:
        report_lines.append("• Consider CPU optimization or instance upgrade - peak CPU is high")

    if performance_analysis["min_freeable_memory_gb"] < 1:
        report_lines.append("• Consider memory optimization or instance upgrade - memory pressure detected")

    if performance_analysis["max_total_iops"] > 3000:
        report_lines.append("• Consider storage optimization - high IOPS detected")

    if "size_vs_cpu" in correlations and correlations["size_vs_cpu"] > 0.5:
        report_lines.append("• Monitor table growth closely - strong correlation with performance impact")

    largest_growth = max(
        sizes_analysis["growth_rates"].values(), key=lambda x: x["daily_growth_gb"], default={"daily_growth_gb": 0}
    )

    if largest_growth["daily_growth_gb"] > 0.1:  # Growing more than 100MB per day
        report_lines.append("• Investigate table growth patterns - rapid growth detected")

    if len(report_lines) == len(report_lines) - len([line for line in report_lines if line.startswith("•")]):
        report_lines.append("• No immediate action required - metrics look healthy")

    # Output the report
    report_text = "\n".join(report_lines)
    print(report_text)

    if output_file:
        with open(output_file, "w") as f:
            f.write(report_text)
        print(f"\nReport saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Analyze combined table size and RDS performance data")
    parser.add_argument(
        "--sizes-file", default="hbi_table_sizes.csv", help="Table sizes CSV file (default: hbi_table_sizes.csv)"
    )
    parser.add_argument(
        "--metrics-file",
        default="rds_tuesday_metrics.csv",
        help="RDS metrics CSV file (default: rds_tuesday_metrics.csv)",
    )
    parser.add_argument("--output-report", help="Save report to file (optional)")

    args = parser.parse_args()

    try:
        # Load data
        sizes_df, metrics_df = load_and_validate_data(args.sizes_file, args.metrics_file)

        # Perform analyses
        print("Analyzing table size trends...")
        sizes_analysis = analyze_size_trends(sizes_df)

        print("Analyzing performance trends...")
        performance_analysis = analyze_performance_trends(metrics_df)

        print("Finding correlations...")
        correlations = find_correlations(sizes_df, metrics_df)

        print("\nGenerating comprehensive report...")
        print()

        # Generate report
        generate_report(sizes_analysis, performance_analysis, correlations, args.output_report)

    except KeyboardInterrupt:
        print("\nAnalysis interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"Error during analysis: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
