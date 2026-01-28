# HBI Database Monitoring - Usage Summary

## ✅ Key Confirmations

### 1. Table Size Output - ALWAYS IN GB
The `extract_table_sizes.py` script **always outputs values in gigabytes (GB)** as numeric values:

```csv
table_name,heap_size_gb,toast_size_gb,indexes_size_gb,total_size_gb,query_timestamp
hbi.hosts,2.500,0.128,1.200,3.828,2026-01-28T10:30:45.123456
hbi.system_profiles_static,1.800,0.064,0.781,2.645,2026-01-28T10:30:50.789012
hbi.system_profiles_dynamic,3.200,0.256,1.500,4.956,2026-01-28T10:30:55.345678
```

**Key Points:**
- ✅ All values are **numeric** (not text like "2.5 GB")
- ✅ All values are in **gigabytes** (converted from bytes)
- ✅ **3 decimal precision** for accuracy
- ✅ Column names have **_gb suffix** for clarity

### 2. Complete Tool Suite Available

| Script | Purpose | Output |
|--------|---------|---------|
| `extract_table_sizes.py` | Collect table sizes from GABI | CSV with GB values |
| `analyze_sizes.py` | Analyze size trends and growth | Console/file report |
| `collect_rds_metrics.py` | Collect CloudWatch metrics | CSV with performance data |
| `analyze_combined_metrics.py` | Correlate sizes with performance | Console/file report |

## 🚀 Complete Workflow Examples

### Daily Table Size Monitoring

```bash
# 1. Collect current table sizes (always in GB!)
./utils/extract_table_sizes.py --env prod

# 2. Analyze the collected data
./utils/analyze_sizes.py

# 3. Save analysis to file for records
./utils/analyze_sizes.py --output daily_analysis_$(date +%Y%m%d).txt
```

### Weekly Performance + Size Analysis

```bash
# 1. Collect table sizes (GB values)
./utils/extract_table_sizes.py --env prod

# 2. Analyze table size patterns
./utils/analyze_sizes.py --output weekly_size_analysis.txt

# 3. If it's Tuesday, collect RDS metrics
if [ $(date +%u) -eq 2 ]; then
    # Authenticate with Red Hat SAML (for RH employees)
    rh-aws-saml-login --profile production-account
    ./utils/collect_rds_metrics.py
fi

# 4. Generate combined analysis (if we have both datasets)
./utils/analyze_combined_metrics.py --output-report weekly_combined_report.txt
```

### Monthly Deep Dive

```bash
# Collect full month of data
./utils/extract_table_sizes.py --env prod
./utils/collect_rds_metrics.py --start-date 2026-01-01 --end-date 2026-01-31

# Generate comprehensive reports
./utils/analyze_sizes.py --output monthly_sizes.txt
./utils/analyze_combined_metrics.py --output-report monthly_combined.txt

# Review results
echo "=== Size Analysis ==="
cat monthly_sizes.txt
echo "=== Combined Analysis ==="
cat monthly_combined.txt
```

## 📊 Sample Output Formats

### Table Size Analysis (`analyze_sizes.py`)
```
HBI Table Size Analysis
=======================

Dataset Overview:
- Total measurements: 12
- Tables tracked: hbi.hosts, hbi.system_profiles_static, hbi.system_profiles_dynamic
- Date range: 2026-01-15 to 2026-01-28
- Measurement span: 13 days

Latest Table Sizes (GB):
--------------------------------------------------
hbi.hosts                         3.828 GB
  ├─ Heap:       2.500 GB
  ├─ Toast:      0.128 GB
  └─ Indexes:    1.200 GB
...

Growth Analysis:
--------------------------------------------------
hbi.hosts:
  Growth: +0.027 GB (+0.71%)
  Daily avg: +0.002077 GB/day
...
```

### Combined Analysis (`analyze_combined_metrics.py`)
```
HBI Database Analysis Report
==================================================

TABLE SIZE ANALYSIS
------------------------------
Total Database Size: 11.429 GB
Largest Table: hbi.system_profiles_dynamic (4.956 GB)

PERFORMANCE ANALYSIS
------------------------------
Average CPU Utilization: 85.64%
Peak Total IOPS: 1389.12

CORRELATION ANALYSIS
------------------------------
Database Size vs CPU Utilization: 0.756
Strong positive correlation: Database growth significantly increases CPU usage
...
```

## 🔧 Key Features Confirmed

### Table Size Collection (`extract_table_sizes.py`)
- ✅ **Always outputs in GB** - no more MB/KB conversions needed
- ✅ **Numeric values** - perfect for calculations and analysis
- ✅ **Append functionality** - builds time series data
- ✅ **3 decimal precision** - accurate size tracking

### Size Analysis (`analyze_sizes.py`)
- ✅ **Console output** - immediate results
- ✅ **File output** - save reports with `--output`
- ✅ **Table filtering** - analyze specific tables with `--table`
- ✅ **Growth calculations** - automatic trend analysis

### RDS Metrics (`collect_rds_metrics.py`)
- ✅ **Tuesday collection** - consistent weekly sampling
- ✅ **Peak metrics** - CPU, IOPS, memory pressure
- ✅ **CloudWatch integration** - uses AWS CLI
- ✅ **Append functionality** - builds time series

### Combined Analysis (`analyze_combined_metrics.py`)
- ✅ **Correlation analysis** - links size growth to performance
- ✅ **Alert generation** - identifies concerning patterns
- ✅ **Trend analysis** - growth rates and patterns
- ✅ **File reports** - save comprehensive analyses

## 📈 Benefits of GB-Only Output

With all values in GB, you can now easily:

```bash
# Calculate total database size
awk -F, 'NR>1 {sum+=$5} END {print "Total DB:", sum, "GB"}' hbi_table_sizes.csv

# Find growth rates
awk -F, 'NR>1 {print $1, $5}' hbi_table_sizes.csv | sort | uniq

# Set up monitoring alerts
awk -F, 'NR>1 && $5 > 10 {print "ALERT:", $1, "is", $5, "GB"}' hbi_table_sizes.csv

# Import into Excel, Python, R for advanced analysis
# All values are already numeric - no conversion needed!
```

## 🎯 Ready to Use!

Your complete HBI database monitoring suite is now ready with:
- ✅ **GB-only output** for all table sizes
- ✅ **Full analysis tools** including `analyze_sizes.py`
- ✅ **Time series tracking** for both sizes and performance
- ✅ **Correlation analysis** to link growth with performance impact
- ✅ **Automated reporting** with file output options

Start monitoring with: `./utils/extract_table_sizes.py --env prod`
