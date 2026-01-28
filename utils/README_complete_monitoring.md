# Complete HBI Database Monitoring Suite

This directory contains a comprehensive monitoring solution for the HBI database that combines table size tracking with RDS performance metrics to provide complete visibility into database growth and performance patterns.

## 📊 Overview

The monitoring suite consists of these main components:

1. **Table Size Collection** (`extract_table_sizes.py`) - Tracks database partition sizes over time *(always outputs in GB)*
2. **Table Size Analysis** (`analyze_sizes.py`) - Analyzes size trends and growth patterns
3. **RDS Metrics Collection** (`collect_rds_metrics.py`) - Collects CloudWatch performance metrics
4. **Combined Analysis** (`analyze_combined_metrics.py`) - Correlates size and performance data

## 🚀 Quick Start

### 1. Collect Table Size Data

```bash
# Activate environment
pipenv shell

# Collect current table sizes (creates/appends to CSV)
# ✅ ALL VALUES SAVED IN GIGABYTES AS NUMERIC VALUES
./utils/extract_table_sizes.py --env prod

# Run regularly to build time series data
./utils/extract_table_sizes.py --env prod  # Run daily/weekly

# Analyze the collected size data
./utils/analyze_sizes.py  # Shows trends, growth rates, size breakdown
```

### 2. Collect RDS Performance Metrics

```bash
# Authenticate with Red Hat SAML (for RH employees)
rh-aws-saml-login --profile production-account

# OR configure standard AWS credentials
aws configure

# Collect Tuesday metrics for 2026 (creates/appends to CSV)
./utils/collect_rds_metrics.py

# Collect for specific date range
./utils/collect_rds_metrics.py --start-date 2026-01-01 --end-date 2026-06-30
```

### 3. Analyze Combined Data

```bash
# Generate comprehensive analysis report
./utils/analyze_combined_metrics.py

# Save report to file
./utils/analyze_combined_metrics.py --output-report hbi_analysis_report.txt
```

## 📈 Data Collection Strategy

### Table Size Data
- **Frequency**: Daily or weekly collection recommended
- **Metrics**: Heap, TOAST, indexes, total size (all in GB)
- **Tables**: `hbi.hosts`, `hbi.system_profiles_static`, `hbi.system_profiles_dynamic`
- **Output**: `hbi_table_sizes.csv` (numeric GB values, append by default)

### RDS Performance Data
- **Frequency**: Weekly collection on Tuesdays
- **Metrics**: Peak CPU, IOPS, memory pressure, connections
- **Source**: AWS CloudWatch via AWS CLI
- **Output**: `rds_tuesday_metrics.csv` (append by default)
- **Authentication**: Red Hat SAML login preferred for RH employees

### Why Tuesdays?
- Consistent weekly sampling eliminates day-of-week variance
- Tuesdays typically represent normal business operation patterns
- Avoids Monday startup effects and Friday wind-down patterns
- Enables clean week-over-week trending analysis

## 📋 Example Workflow

### Weekly Monitoring Routine

```bash
# 1. Collect current table sizes (always in GB!)
./utils/extract_table_sizes.py --env prod

# 2. Analyze table size trends and growth
./utils/analyze_sizes.py

# 3. If it's Tuesday, collect RDS metrics
if [ $(date +%u) -eq 2 ]; then
    # Authenticate first (Red Hat employees)
    rh-aws-saml-login --profile production-account
    ./utils/collect_rds_metrics.py
fi

# 4. Generate combined analysis report
./utils/analyze_combined_metrics.py --output-report weekly_report_$(date +%Y%m%d).txt

# 5. Check for alerts in the report
grep -E "(⚠️|🔴)" weekly_report_$(date +%Y%m%d).txt || echo "No alerts detected"
```

### Monthly Deep Analysis

```bash
# Ensure you have table size data (all values in GB)
./utils/extract_table_sizes.py --env prod

# Analyze table size patterns
./utils/analyze_sizes.py --output monthly_sizes_analysis.txt

# Authenticate for AWS access (Red Hat employees)
rh-aws-saml-login --profile production-account

# Collect complete month of Tuesday data
./utils/collect_rds_metrics.py --start-date 2026-01-01 --end-date 2026-01-31

# Generate combined detailed report
./utils/analyze_combined_metrics.py --output-report monthly_combined_analysis.txt

# Review trends and correlations
echo "=== Table Size Analysis ==="
cat monthly_sizes_analysis.txt
echo "=== Combined Analysis ==="
cat monthly_combined_analysis.txt
```

## 🔧 Authentication Setup

### Red Hat Employees (Recommended)
```bash
# Install Red Hat SAML login tool
pip install rh-aws-saml-login

# Login to AWS using Red Hat SSO
rh-aws-saml-login

# Login to specific AWS account/profile
rh-aws-saml-login --profile production-account

# Verify authentication
aws sts get-caller-identity
```

**References:**
- Tool: https://github.com/app-sre/rh-aws-saml-login
- Setup Guide: https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/docs/app-sre/aws-account-sso.md

### Standard AWS Setup
```bash
# Install AWS CLI
pip install awscli

# Configure credentials
aws configure
# OR use profiles
aws configure --profile your-profile-name
```

## 📊 Sample Output Files

### Table Sizes CSV (`hbi_table_sizes.csv`)
```csv
table_name,heap_size_gb,toast_size_gb,indexes_size_gb,total_size_gb,query_timestamp
hbi.hosts,2.500,0.128,1.200,3.828,2026-01-28T10:30:45.123456
hbi.system_profiles_static,1.800,0.064,0.781,2.645,2026-01-28T10:30:50.789012
hbi.system_profiles_dynamic,3.200,0.256,1.500,4.956,2026-01-28T10:30:55.345678
```

### RDS Metrics CSV (`rds_tuesday_metrics.csv`)
```csv
date,peak_cpu_utilization_percent,peak_total_iops,min_freeable_memory_gb,peak_db_connections,query_timestamp
2026-01-07,85.67,1250.45,2.150,45,2026-01-28T15:30:45.123456
2026-01-14,92.34,1389.12,1.876,52,2026-01-28T15:31:12.789012
2026-01-21,78.91,1156.78,2.543,38,2026-01-28T15:31:40.345678
```

### Combined Analysis Report
```
HBI Database Analysis Report
==================================================

TABLE SIZE ANALYSIS
------------------------------
Total Database Size: 11.429 GB
Largest Table: hbi.system_profiles_dynamic (4.956 GB)

Growth Rates by Table:
  hbi.system_profiles_dynamic:
    Total Growth: +0.174 GB (+3.51%)
    Daily Average: +0.174000 GB/day

PERFORMANCE ANALYSIS
------------------------------
Average CPU Utilization: 85.64%
Peak CPU Utilization: 92.34%
Peak Total IOPS: 1389.12

Performance Alerts:
  ⚠️  High CPU days (>80%): 2

CORRELATION ANALYSIS
------------------------------
Database Size vs CPU Utilization: 0.756
Database Size vs Total IOPS: 0.623

Interpretation:
  🔴 Strong positive correlation: Database growth significantly increases CPU usage

RECOMMENDATIONS
------------------------------
• Consider CPU optimization or instance upgrade - peak CPU is high
• Monitor table growth closely - strong correlation with performance impact
```

## 🚨 Monitoring and Alerts

### Key Metrics to Watch

**Table Growth Alerts:**
- Daily growth > 100MB per table
- Total database size > 50GB
- Any table > 10GB individually

**Performance Alerts:**
- CPU utilization > 80% consistently
- IOPS > 3000 regularly
- Freeable memory < 1GB

**Correlation Alerts:**
- Size vs CPU correlation > 0.7 (strong performance impact from growth)
- Rapid growth coinciding with performance degradation

### Automation Ideas

```bash
# Crontab example for automated collection
# Run daily at 6 AM
0 6 * * * /path/to/pipenv run /path/to/extract_table_sizes.py --env prod

# Run Tuesday metrics at 7 AM on Tuesdays (after SAML login)
0 7 * * 2 /usr/bin/rh-aws-saml-login --profile prod && /path/to/pipenv run /path/to/collect_rds_metrics.py

# Weekly analysis report on Wednesdays
0 8 * * 3 /path/to/pipenv run /path/to/analyze_combined_metrics.py --output-report /reports/weekly_$(date +\%Y\%m\%d).txt
```

## 📚 Additional Resources

- **Table Sizes**: See `README_table_sizes.md` for detailed size collection info
- **RDS Metrics**: See `README_rds_metrics.md` for CloudWatch metrics details
- **Examples**: Run `./example_usage.sh` for interactive examples
- **Analysis**: Use `./analyze_sizes.py` for table-size-only analysis

## 🔍 Troubleshooting

### Common Issues

1. **Red Hat SAML authentication issues**
   ```bash
   # Check authentication status
   aws sts get-caller-identity

   # Re-authenticate if needed
   rh-aws-saml-login --profile production-account
   ```

2. **Standard AWS credentials not configured**
   ```bash
   aws configure list  # Check credentials
   aws sts get-caller-identity  # Verify access
   ```

3. **No overlapping dates in correlation analysis**
   - Ensure both scripts have been run for the same time periods
   - Check that dates align between the two datasets

4. **Missing data points**
   - GABI endpoint issues: Check VPN/network connectivity
   - AWS API issues: Verify CloudWatch permissions and region settings
   - RDS instance name: Confirm exact spelling of database identifier

### Verification Commands

```bash
# Check data files exist and have content
ls -la *table_sizes*.csv *rds*metrics*.csv
head -5 hbi_table_sizes.csv
head -5 rds_tuesday_metrics.csv

# Verify AWS access (Red Hat SAML)
aws sts get-caller-identity
aws rds describe-db-instances --db-instance-identifier host-inventory-prod
aws cloudwatch list-metrics --namespace AWS/RDS | head -20
```

This monitoring suite provides comprehensive visibility into your HBI database performance and helps identify optimization opportunities before they become critical issues.
