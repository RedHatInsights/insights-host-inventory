# RDS CloudWatch Metrics Collection Tool

The `collect_rds_metrics.py` script collects peak metrics from AWS CloudWatch for the host-inventory-prod RDS instance on every Tuesday, providing insights into database performance patterns.

## Metrics Collected

For each Tuesday, the script collects peak values for:
- **CPU Utilization**: Peak CPU usage percentage during the day
- **Total IOPS**: Peak combined read + write IOPS (Input/Output Operations Per Second)
- **Freeable Memory**: Minimum freeable memory in GB (indicates peak memory pressure)
- **Database Connections**: Peak number of concurrent database connections

All metrics are collected for the full day (00:00 to 23:59 UTC) with maximum/minimum aggregation as appropriate.

## Prerequisites

### Red Hat AWS SAML Login Setup

For Red Hat employees accessing AWS accounts, use the official Red Hat SAML login tool:

```bash
# Install rh-aws-saml-login
pip install rh-aws-saml-login

# Login to AWS using Red Hat SSO
rh-aws-saml-login

# OR login to specific profile/account
rh-aws-saml-login --profile production-account
```

**Reference Documentation:**
- Tool: https://github.com/app-sre/rh-aws-saml-login
- Setup Guide: https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/docs/app-sre/aws-account-sso.md

### Alternative: Standard AWS CLI Setup
If not using Red Hat SSO, you can use standard AWS CLI:
```bash
# Install AWS CLI (if not already installed)
pip install awscli

# Configure AWS credentials
aws configure
# OR use AWS profiles
aws configure --profile your-profile-name
```

### Required AWS Permissions
Your AWS user/role needs CloudWatch read permissions:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "cloudwatch:GetMetricData"
            ],
            "Resource": "*"
        }
    ]
}
```

## Usage

### Basic Usage

```bash
# Collect metrics for all Tuesdays in 2026 (default behavior)
./utils/collect_rds_metrics.py

# Collect metrics for a specific date range
./utils/collect_rds_metrics.py --start-date 2026-01-01 --end-date 2026-06-30

# Use a different RDS instance
./utils/collect_rds_metrics.py --db-instance host-inventory-stage

# Specify custom output file
./utils/collect_rds_metrics.py --output my_rds_metrics.csv
```

### Advanced Usage

```bash
# First, authenticate with Red Hat SAML (recommended for RH employees)
rh-aws-saml-login --profile production-account

# Use specific AWS profile
./utils/collect_rds_metrics.py --profile production-account

# Overwrite existing file instead of appending
./utils/collect_rds_metrics.py --overwrite

# Collect for specific date range with custom settings
./utils/collect_rds_metrics.py \
    --start-date 2026-01-01 \
    --end-date 2026-12-31 \
    --db-instance host-inventory-prod \
    --profile production-account \
    --output 2026_rds_metrics.csv
```

## Output Format

The script generates a CSV file with the following columns:
- `date`: The Tuesday date (YYYY-MM-DD format)
- `peak_cpu_utilization_percent`: Peak CPU usage percentage
- `peak_total_iops`: Peak total IOPS (read + write combined)
- `min_freeable_memory_gb`: Minimum freeable memory in GB
- `peak_db_connections`: Peak number of database connections
- `query_timestamp`: ISO timestamp of when the metrics were collected

### Example Output

```csv
date,peak_cpu_utilization_percent,peak_total_iops,min_freeable_memory_gb,peak_db_connections,query_timestamp
2026-01-07,85.67,1250.45,2.150,45,2026-01-28T15:30:45.123456
2026-01-14,92.34,1389.12,1.876,52,2026-01-28T15:31:12.789012
2026-01-21,78.91,1156.78,2.543,38,2026-01-28T15:31:40.345678
2026-01-28,88.45,1345.67,2.012,48,2026-01-28T15:32:08.901234
```

## Tuesday-Only Collection

The script automatically identifies and collects data only for Tuesdays within the specified date range. This is useful for:

- **Weekly pattern analysis**: Understand how performance varies week to week
- **Consistent sampling**: Same day of week eliminates weekly pattern variance
- **Trend tracking**: Monitor performance changes over time on comparable days
- **Capacity planning**: Use Tuesday patterns to predict peak loads

## Append Behavior

By default, the script **appends** new results to existing CSV files, similar to the table size collection script:

- **Historical tracking**: Maintains records of past measurements
- **Incremental updates**: Add new weeks without losing previous data
- **Duplicate handling**: Automatically removes duplicate dates when appending
- **Sorted output**: Results are sorted by date for easy analysis

Use `--overwrite` to replace the file contents instead of appending.

## Error Handling

- Individual date failures don't stop collection for other dates
- Missing data points are marked as NULL in the CSV
- AWS CLI errors are logged with detailed error messages
- Network/authentication issues are handled gracefully

## Integration with Table Size Data

This RDS metrics data complements the table size data from `extract_table_sizes.py`:

- **Correlation analysis**: Compare table growth with performance metrics
- **Performance impact**: See how table size affects CPU, IOPS, and memory
- **Capacity planning**: Use both datasets to predict infrastructure needs
- **Optimization opportunities**: Identify when table growth drives performance issues

## Troubleshooting

### Common Issues

1. **AWS credentials not configured**
   ```bash
   aws configure list
   # Ensure credentials are set up properly
   ```

2. **No data returned**
   - Verify the RDS instance name is correct
   - Check that the instance existed during the queried time period
   - Ensure you have CloudWatch permissions

3. **Date parsing errors**
   - Use YYYY-MM-DD format for dates
   - Ensure start date is before end date

### Verification Commands

#### Red Hat SAML Login Verification
```bash
# Check current AWS identity (after rh-aws-saml-login)
aws sts get-caller-identity

# List available AWS profiles
aws configure list-profiles

# Test CloudWatch access
aws cloudwatch describe-alarms --max-items 1

# Verify RDS instance exists
aws rds describe-db-instances --db-instance-identifier host-inventory-prod

# Check available metrics
aws cloudwatch list-metrics --namespace AWS/RDS | head -20
```

#### Standard AWS CLI Verification
```bash
# Test AWS CLI access
aws cloudwatch describe-alarms --alarm-names test

# Verify credentials are configured
aws configure list

# Check available metrics
aws cloudwatch list-metrics --namespace AWS/RDS
```
