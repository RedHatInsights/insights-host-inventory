#!/bin/bash

# Example usage script for extract_table_sizes.py
# This demonstrates how to use the append functionality for time series data collection

echo "HBI Table Size Extraction - Example Usage"
echo "========================================"

# Activate pipenv environment
echo "Activating pipenv environment..."
pipenv shell

echo ""
echo "Example 1: First run (creates new CSV file)"
echo "--------------------------------------------"
echo "Command: ./utils/extract_table_sizes.py --env prod"
echo ""
echo "This will create 'hbi_table_sizes.csv' with initial data"

echo ""
echo "Example 2: Subsequent runs (appends to existing file)"
echo "----------------------------------------------------"
echo "Command: ./utils/extract_table_sizes.py --env prod"
echo ""
echo "This will append new measurements to the existing CSV file"
echo "allowing you to track table size growth over time"

echo ""
echo "Example 3: Force overwrite (replaces file contents)"
echo "-------------------------------------------------"
echo "Command: ./utils/extract_table_sizes.py --env prod --overwrite"
echo ""
echo "This will replace the entire CSV file with new data"

echo ""
echo "Example 4: Using custom output file for different tracking"
echo "--------------------------------------------------------"
echo "Command: ./utils/extract_table_sizes.py --env stage --output staging_sizes.csv"
echo ""
echo "This creates/appends to a separate file for staging data"

echo ""
echo "Time Series Data Collection Workflow:"
echo "====================================="
echo "1. Run daily:     ./utils/extract_table_sizes.py --env prod"
echo "2. Run weekly:    ./utils/extract_table_sizes.py --env prod --output weekly_sizes.csv"
echo "3. Run monthly:   ./utils/extract_table_sizes.py --env prod --output monthly_sizes.csv"
echo ""
echo "Each file will accumulate historical data for trend analysis"

echo ""
echo "Viewing accumulated data:"
echo "========================"
echo "head -10 hbi_table_sizes.csv    # View first 10 rows"
echo "tail -10 hbi_table_sizes.csv    # View last 10 rows"
echo "wc -l hbi_table_sizes.csv       # Count total measurements"

echo ""
echo "Data Analysis:"
echo "=============="
echo "./utils/analyze_sizes.py                          # Full table size analysis"
echo "./utils/analyze_sizes.py --table hbi.hosts        # Analyze specific table"
echo "./utils/analyze_sizes.py --output report.txt      # Save analysis to file"

echo ""
echo "Sample output format (all values in GB):"
echo "========================================"
echo "table_name,heap_size_gb,toast_size_gb,indexes_size_gb,total_size_gb,query_timestamp"
echo "hbi.hosts,2.500,0.128,1.200,3.828,2026-01-28T10:30:45.123456"
echo "hbi.system_profiles_static,1.800,0.064,0.781,2.645,2026-01-28T10:30:50.789012"
echo "Numeric values enable easy calculations, trending, and analysis!"

echo ""
echo "RDS Metrics Collection (CloudWatch):"
echo "===================================="
echo "# First, authenticate with Red Hat SAML (for RH employees)"
echo "rh-aws-saml-login --profile production-account"
echo ""
echo "./utils/collect_rds_metrics.py                    # Collect all Tuesdays in 2026"
echo "./utils/collect_rds_metrics.py --start-date 2026-01-01 --end-date 2026-06-30"
echo "./utils/collect_rds_metrics.py --db-instance host-inventory-stage"

echo ""
echo "Combined Analysis:"
echo "=================="
echo "./utils/analyze_combined_metrics.py               # Full correlation analysis"
echo "./utils/analyze_combined_metrics.py --output-report analysis.txt"

echo ""
echo "Complete Monitoring Workflow:"
echo "============================="
echo "1. ./utils/extract_table_sizes.py --env prod      # Collect table sizes (GB values)"
echo "2. ./utils/analyze_sizes.py                       # Analyze table size trends"
echo "3. ./utils/collect_rds_metrics.py                 # Collect RDS metrics (Tuesdays)"
echo "4. ./utils/analyze_combined_metrics.py            # Generate combined analysis"
