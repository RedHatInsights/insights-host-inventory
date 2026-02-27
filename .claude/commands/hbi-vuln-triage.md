# /hbi-vuln-triage - HBI Container Vulnerability Triage

Analyze a vulnerability report and produce a deduplicated, actionable triage with Jira-formatted output.

## Prerequisites (optional)

To fetch vulnerability data directly from Jira tickets, install and configure the [go-jira](https://github.com/go-jira/jira) CLI. This is optional — you can always paste raw vulnerability data instead.

### 1. Install go-jira

```bash
# With Go installed:
go install github.com/go-jira/jira/cmd/jira@latest

# Or via Homebrew (macOS):
brew install go-jira
```

### 2. Create a Personal Access Token

1. Log in to your Jira instance (e.g., `https://issues.redhat.com/`)
2. Navigate to **Profile** > **Personal Access Tokens**
3. Click **Create token**, give it a name (e.g., `go-jira`), and copy the generated token
4. Store the token securely (see step 3 for options)

### 3. Configure go-jira

Create `~/.jira.d/config.yml`. The example below uses `pass` (the standard Unix password manager), but go-jira supports other `password-source` methods — see the [go-jira documentation](https://github.com/go-jira/jira#password-source) for alternatives such as `keyring`, `stdin`, or setting the token directly via environment variables.

**Example using `pass`:**

```bash
# Store your PAT in pass
pass insert GoJira/youruser@redhat.com
```

```yaml
endpoint: https://issues.redhat.com/
authentication-method: bearer-token
password-source: pass
password-name: GoJira/youruser@redhat.com
user: rh-gs-youruser
```

- `endpoint` — your Jira instance URL
- `authentication-method` — set to `bearer-token` to use a PAT
- `password-source` — how go-jira retrieves the token (`pass`, `keyring`, `stdin`, etc.)
- `password-name` — the entry name in your chosen password store
- `user` — your Jira username

### 4. Verify

```bash
jira view RHINENG-23874 --gjq 'fields.summary'
```

If this prints the issue summary, the CLI is configured correctly.

## Input

The input is provided as: $ARGUMENTS

The argument can be **either**:

1. **A Jira issue key** (e.g., `RHINENG-23874`) — the vulnerability data will be fetched automatically from the ticket.
2. **Raw pipe-delimited table rows** pasted directly — the traditional input format.

### Phase 0: Resolve Input

Determine which input format was provided:

- If `$ARGUMENTS` matches the pattern of a Jira issue key (e.g., `RHINENG-\d+` or similar `PROJECT-NUMBER` format):
  1. Check if the `jira` CLI (go-jira) is available locally by running `which jira`.
  2. If available, **validate the issue is related to Host-Inventory**. Fetch the metadata and description:
     ```
     jira view <ISSUE_KEY> --gjq 'fields.summary'
     jira view <ISSUE_KEY> --gjq 'fields.components'
     jira view <ISSUE_KEY> --gjq 'fields.description'
     ```
     The issue must satisfy **all three** of these conditions (case-insensitive):
     - The summary contains `Host-Inventory` or `host-inventory`
     - The components list includes `Inventory`
     - The description contains `insights-host-inventory`

     If any condition fails, report which checks passed and which failed: *"Issue <KEY> does not appear to be related to Host-Inventory: summary '<summary>' [PASS/FAIL], components [<list>] [PASS/FAIL], description contains insights-host-inventory [PASS/FAIL]. Please verify the issue key."* and stop.
  3. Extract the pipe-delimited vulnerability table from the description by filtering lines that start with `|` and contain vulnerability data (skip the header row if it matches `|Workstream|OSD Namespace|...`). If the table is empty, report the error and stop.
  6. If `jira` is NOT available, report the error and ask the user to either install go-jira (`go install github.com/go-jira/jira/cmd/jira@latest`) or paste the vulnerability data directly.
  7. If the `jira` command fails (auth error, issue not found), report the error and stop.

- If `$ARGUMENTS` contains pipe-delimited rows (starts with `|`), use them directly as the vulnerability data.

The expected table format is:
```
|Workstream|OSD Namespace|Image|Image Tag|Vulnerability ID|Alt Vulnerability ID(s)|Severity|NVD Severity|KEV Detection Date|Name|Version|Fixed Version|Upstream Fix Status|Package Type|
```

## Instructions

### Phase 1: Parse and Deduplicate

1. Parse every row from the input data.
2. Extract these fields from each row: Image, Image Tag, Vulnerability ID, Alt Vulnerability ID(s), Severity, NVD Severity, Name (package), Version, Fixed Version, Upstream Fix Status, Package Type.
3. Deduplicate by grouping:
   - Same CVE affecting sibling RPM packages (e.g., openssl, openssl-libs, openssl-devel share the same vulnerability) — collapse into one row listing all affected sub-packages.
   - Same CVE appearing across multiple image tags (e.g., dc81577, 6d1977e, bc0b6ae) — collapse into one row noting all affected tags.
4. Count: report original row count vs deduplicated row count.

### Phase 2: Identify Image Tags

1. For each unique image tag found in the report, check if it corresponds to a git commit in this repo:
   ```
   git log --format="%h %ai %s" -1 <tag>
   ```
2. Report what each tag represents (commit date, message).
3. Identify the newest tag — vulnerabilities only in older tags may already be resolved.

### Phase 3: Check Current Codebase State

For **Python package** vulnerabilities (Package Type = python):

1. Check `Pipfile.lock` for the current pinned version of each vulnerable package:
   ```
   grep -A 5 '"<package_name>"' Pipfile.lock
   ```
2. Compare the locked version against the "Fixed Version" from the report.
3. Mark as ALREADY FIXED if the locked version meets or exceeds the fixed version.

For **RPM package** vulnerabilities (Package Type = rpm):

1. Read the `Dockerfile` to understand:
   - Which base image is used (e.g., `ubi9/ubi-minimal:latest`)
   - Which packages are explicitly installed
   - Which devel packages are removed in the cleanup step
2. Determine if a simple rebuild would pull updated RPMs from the base image.
3. Flag any `-devel` packages (e.g., `openssl-devel`) that are installed but NOT removed in the Dockerfile cleanup step — these ship unnecessarily in the final image.

For vulnerabilities in **external images** (e.g., `registry.access.redhat.com/ubi9/nginx-124`):

1. Note these are NOT controlled by HBI — they are upstream Red Hat images.
2. Recommend checking if Red Hat has published an updated image.

### Phase 4: Present Triage Results

Present the full triage findings using GitHub-flavored markdown so they are readable directly in the Claude Code session. Use tables, bold for severity, and standard markdown formatting:

- **Image tags in report**: table with tag, date, commit message, status (newest/older)
- **Python packages**: table with package, vulnerable version(s), fixed version, CVE/GHSA, severity, Pipfile.lock status (already fixed or needs update), recommended action
- **RPM packages (HBI image)**: table with package(s), current version, fixed version, CVE(s), highest severity, action — split into "present in newest tag" and "only in older tags" sub-sections
- **RPM packages (external images)**: table with image, package(s), current version, fixed version, CVE(s), highest severity, action
- **Dockerfile findings**: list devel/build packages that remain in the final image unnecessarily
- **Summary**: table with category, unique CVE count, highest severity, fix status
- **Recommended actions**: numbered list in priority order

### Phase 5: Produce Jira-Formatted Output

Generate the same content as Phase 4, but using Jira wiki markup so the user can paste it directly into a Jira ticket comment. Use this structure:

```
h2. Vulnerability Triage - HBI Container Images

_Original report: <N> rows → Deduplicated: <M> unique vulnerability/package combinations_

h3. Image Tags in Report

||Tag||Date||Commit||Status||
|<tag>|<date>|<commit message>|Newest / Older|

h3. 1. Python Packages (HBI image) - Direct Control

||Package||Vuln Version(s)||Fixed Version||CVE / GHSA||Severity||Pipfile.lock Status||Action||
|<package>|<versions>|<fixed>|<cve>|{color:red}*High*{color} or {color:orange}*Medium*{color} or Low||(/) Already fixed (==<ver>) or (x) Needs update|Rebuild image / Update Pipfile|

h3. 2. RPM Packages (HBI image) - Base Image Rebuild

||Package(s)||Current Version||Fixed Version||CVE(s)||Highest Severity||Action||
|<pkg1> / <pkg2>|<current>|<fixed>|<cve list>|{color:red}*High*{color}|Rebuild image|

h3. 3. RPM Packages (External Images) - Upstream

||Image||Package(s)||Current Version||Fixed Version||CVE(s)||Highest Severity||Action||
|<image>|<pkg>|<current>|<fixed>|<cve list>|{color:red}*High*{color}|Wait for upstream refresh + redeploy|

h3. Dockerfile Findings

List any `-devel` packages or build tools that remain in the final image but could be added to the `microdnf remove` cleanup step to reduce attack surface.

h3. Summary

||Category||Unique CVEs||Highest Severity||Fix||
|Python packages (HBI)|<n>|<sev>|(/) or (x) status|
|RPM packages (HBI)|<n>|<sev>|description|
|RPM packages (external)|<n>|<sev>|description|

h3. Recommended Actions

# <numbered action items in priority order>
```

### Formatting Rules

- Use `{color:red}*High*{color}` for High severity
- Use `{color:orange}*Medium*{color}` for Medium severity
- Use `Low` (no color) for Low severity
- Use `(/)` for checkmark (fixed/resolved)
- Use `(x)` for X mark (needs action)
- Use `(!)` for warning (upstream/external dependency)
- Use `{{monospace}}` for package names in prose text
- Wrap the entire Jira output in a code block so the user can copy it easily

### Phase 6: Plain-Text Summary

After the Jira block, provide a brief plain-text summary:
- Total vulnerabilities vs unique after dedup
- How many are already fixed in the current codebase
- How many are fixed by a simple rebuild
- How many require upstream action
- Key recommended next steps
