# /hbi-vuln-triage - HBI Container Vulnerability Triage

Analyze a vulnerability report pasted from Jira (pipe-delimited table rows) and produce a deduplicated, actionable triage with Jira-formatted output.

## Input

The user provides vulnerability data as pipe-delimited table rows in this format:

```
|Workstream|OSD Namespace|Image|Image Tag|Vulnerability ID|Alt Vulnerability ID(s)|Severity|NVD Severity|KEV Detection Date|Name|Version|Fixed Version|Upstream Fix Status|Package Type|
```

The input is provided as: $ARGUMENTS

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

### Phase 4: Produce Jira-Formatted Output

Generate output using Jira wiki markup that the user can paste directly into a Jira ticket comment. Use this structure:

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

### Phase 5: Plain-Text Summary

After the Jira block, provide a brief plain-text summary:
- Total vulnerabilities vs unique after dedup
- How many are already fixed in the current codebase
- How many are fixed by a simple rebuild
- How many require upstream action
- Key recommended next steps
