# HBI Table Size Extraction Tool

The `extract_table_sizes.py` script extracts size information for HBI database tables using the GABI endpoint and exports the results to CSV format using pandas.

## Tables Analyzed

The script queries the following tables for partition size information:
- `hbi.hosts`
- `hbi.system_profiles_static`
- `hbi.system_profiles_dynamic`

## Size Metrics Collected

For each table, the script collects all sizes in **gigabytes (GB)** as numeric values:
- **Heap Size GB**: Size of the table data itself in gigabytes
- **Toast Size GB**: Size of TOAST (The Oversized-Attribute Storage Technique) data in gigabytes
- **Indexes Size GB**: Size of all indexes on the table in gigabytes
- **Total Size GB**: Combined size of all components in gigabytes

All values are rounded to 3 decimal places for precision.

## Usage

### Prerequisites

Make sure you're in the pipenv environment:
```bash
pipenv shell
```

### Basic Usage

By default, the script **APPENDS** new results to the existing CSV file, allowing you to track table sizes over time.

```bash
# Query production environment (appends to existing file)
./utils/extract_table_sizes.py --env prod

# Query staging environment (appends to existing file)
./utils/extract_table_sizes.py --env stage

# Specify custom output file (appends to existing file)
./utils/extract_table_sizes.py --env prod --output my_table_sizes.csv

# Overwrite the file instead of appending
./utils/extract_table_sizes.py --env prod --overwrite
```

### Advanced Usage

```bash
# Use custom GABI endpoint URL (appends to existing file)
./utils/extract_table_sizes.py --url https://your-gabi-endpoint.com/query

# Provide custom auth token (appends to existing file)
./utils/extract_table_sizes.py --env prod --auth your_token_here

# Combine custom URL, auth, and overwrite mode
./utils/extract_table_sizes.py --url https://your-gabi-endpoint.com/query --auth your_token_here --output custom_sizes.csv --overwrite
```

### Time Series Data Collection

The append functionality makes it easy to collect time series data for monitoring table growth:

```bash
# Run daily to track table growth over time
./utils/extract_table_sizes.py --env prod

# The CSV file will contain multiple entries with timestamps:
# 2026-01-28T09:00:00 - First run
# 2026-01-28T15:30:00 - Second run
# 2026-01-29T09:00:00 - Next day
# etc.
```

## Data Analysis Tool

The included `analyze_sizes.py` script provides automated analysis of your size data:

```bash
# Analyze all tables in the default CSV file
./utils/analyze_sizes.py

# Analyze a specific table
./utils/analyze_sizes.py --table hbi.hosts

# Analyze a custom CSV file
./utils/analyze_sizes.py --file my_custom_sizes.csv
```

The analysis includes:
- **Current sizes**: Latest measurements for all tables
- **Growth rates**: Daily growth trends and percentages
- **Size composition**: Breakdown of heap, TOAST, and index components
- **Total database size**: Combined size across all tables

### Output

The script generates a CSV file (default: `hbi_table_sizes.csv`) with the following columns:
- `table_name`: Name of the table
- `heap_size_gb`: Heap size in gigabytes (numeric, e.g., 2.456)
- `toast_size_gb`: TOAST size in gigabytes (numeric, e.g., 0.128)
- `indexes_size_gb`: Indexes size in gigabytes (numeric, e.g., 1.234)
- `total_size_gb`: Total size in gigabytes (numeric, e.g., 3.818)
- `query_timestamp`: ISO timestamp of when the query was executed

### Example Output

```csv
table_name,heap_size_gb,toast_size_gb,indexes_size_gb,total_size_gb,query_timestamp
hbi.hosts,2.500,0.128,1.200,3.828,2026-01-28T10:30:45.123456
hbi.system_profiles_static,1.800,0.064,0.781,2.645,2026-01-28T10:30:50.789012
hbi.system_profiles_dynamic,3.200,0.256,1.500,4.956,2026-01-28T10:30:55.345678
hbi.hosts,2.500,0.130,1.200,3.830,2026-01-28T15:45:12.567890
hbi.system_profiles_static,1.800,0.065,0.785,2.650,2026-01-28T15:45:15.234567
hbi.system_profiles_dynamic,3.300,0.258,1.500,5.058,2026-01-28T15:45:18.901234
```

Notice how the second run (later timestamp) shows slight growth in some tables, with values as precise numeric gigabytes for easy analysis and calculations.

## Append Behavior

**Important**: By default, the script **appends** new results to existing CSV files rather than overwriting them. This allows for:

- **Time series tracking**: Monitor table size growth over time
- **Historical data**: Keep records of past measurements
- **Trend analysis**: Analyze growth patterns and performance impacts
- **Column compatibility**: Automatically handles schema changes by aligning columns

Use `--overwrite` if you want to replace the file contents instead of appending.

## Error Handling

- If a table query fails, the script will continue processing other tables
- Failed queries are logged with error messages
- The script exits with status code 1 if no data is collected
- Individual table failures don't stop the entire process
- Column mismatches between old and new data are automatically resolved

## Requirements

- `pandas`: For DataFrame operations and CSV export
- `tabulate`: For table formatting (already in dev dependencies)
- Access to OpenShift cluster with `oc` command (for auto-authentication)
- OR valid authentication token for manual auth

## Authentication

The script uses the same authentication mechanism as `run_gabi_interactive.py`:

1. **Automatic**: Uses `oc whoami -t` to get the current OpenShift token
2. **Manual**: Provide token with `--auth` parameter
3. **URL derivation**: Auto-derives GABI URL from `oc whoami --show-server` based on environment
