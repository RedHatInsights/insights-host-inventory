# /hbi-pr-review - Structured Code Review for HBI Pull Requests

Perform a thorough, HBI-aware code review on a pull request from the RedHatInsights/insights-host-inventory repository.

## Input

The PR number is provided as: $ARGUMENTS

If `$ARGUMENTS` is empty or not a valid number, ask the user to provide a PR number (e.g., `/hbi-pr-review 3485`).

## Instructions

### Phase 1: Fetch PR Context

1. Fetch PR metadata:
   ```
   gh pr view $ARGUMENTS --repo RedHatInsights/insights-host-inventory --json number,title,author,state,body,baseRefName,headRefName,labels,reviews,reviewRequests,additions,deletions,changedFiles
   ```

2. Fetch the list of changed files:
   ```
   gh pr view $ARGUMENTS --repo RedHatInsights/insights-host-inventory --json files --jq '.files[].path'
   ```

3. Fetch the full diff:
   ```
   gh pr diff $ARGUMENTS --repo RedHatInsights/insights-host-inventory
   ```

4. Fetch PR comments and review comments for additional context:
   ```
   gh pr view $ARGUMENTS --repo RedHatInsights/insights-host-inventory --json comments --jq '.comments[].body'
   ```

5. If the diff is very large, note that and still proceed — review what you can.

### Phase 2: Understand Scope

Categorize every changed file into one or more of these buckets:

| Category | Path patterns |
|----------|--------------|
| API endpoints | `api/` |
| API spec | `swagger/api.spec.yaml` |
| Models | `app/models.py`, `app/models/` |
| Migrations | `migrations/` |
| Business logic | `lib/` |
| Background jobs | `jobs/` |
| Auth / identity | `app/auth/`, `app/identity.py` |
| Config | `app/config.py`, `app/environment.py` |
| Tests | `tests/` |
| Kafka / MQ | `app/queue/` |
| Logging | `app/logging.py` |
| Build / CI | `Dockerfile`, `.github/`, `Jenkinsfile`, `Makefile`, `Pipfile*` |
| Other | anything else |

Write a 2-3 sentence summary of what the PR does and which categories it touches.

### Phase 3: Review Checklist

Evaluate the PR against each applicable criterion. Skip criteria that are clearly irrelevant to the changed files.

#### 3.1 API Spec Consistency
- If any files in `api/` change endpoints, query parameters, request/response schemas, or status codes, check whether `swagger/api.spec.yaml` is also updated to match.
- Read the relevant sections of `swagger/api.spec.yaml` to compare against the code changes.
- Flag any mismatch between the spec and the implementation.

#### 3.2 Model / Migration Alignment
- If `app/models.py` or files in `app/models/` change (new columns, renamed fields, type changes, new tables), verify there is a corresponding migration in `migrations/versions/`.
- If a migration is present, read it to confirm it matches the model changes (column types, nullable, defaults, index creation).
- Check for `downgrade()` completeness — it should reverse all `upgrade()` operations.

#### 3.3 Auth and Multi-Tenancy
- If new database queries are introduced (in `api/`, `lib/`, or `jobs/`), verify they filter by `org_id` to maintain tenant isolation.
- Check that `x-rh-identity` header handling is correct if auth-related code changes.
- Look for any code path that could leak data across org_id boundaries.

#### 3.4 Test Coverage
- If new functionality is added, are there corresponding tests in `tests/`?
- Do test files follow the `tests/test_*.py` naming convention?
- Are edge cases covered (empty results, invalid input, permission denied)?
- If the PR modifies a function, check whether existing tests for that function are updated.

#### 3.5 Code Style
- Look for obvious style issues: unused imports, debug print statements, hardcoded values that should be config.
- Check import ordering (stdlib, third-party, local).
- Look for overly broad exception handling (`except Exception`).
- Note: detailed linting is handled by ruff/pre-commit, so focus on semantic issues.

#### 3.6 Database Considerations
- Are queries aware of partitioned tables? HBI uses partitioned tables in the `hbi` schema.
- Do new queries risk N+1 problems? Look for queries inside loops.
- If new indexes are added, are they on the correct partition key(s)?
- Are there large `UPDATE` or `DELETE` operations that could lock tables?
- Check for proper use of `db.session` and transaction boundaries.

#### 3.7 Kafka / Message Queue
- If `app/queue/` files change, verify message format consistency.
- Check that Kafka topics are correctly referenced.
- Verify error handling for message consumption/production failures.

#### 3.8 Security
- No raw SQL with string interpolation (use parameterized queries or SQLAlchemy ORM).
- No secrets, tokens, or credentials hardcoded in the diff.
- Input validation on user-supplied values (query params, request bodies).
- Check for SSRF, path traversal, or injection risks in any new code paths.

#### 3.9 Breaking Changes
- Does the PR remove or rename API endpoints?
- Does it change response schemas in ways that could break existing consumers?
- Are query parameter names or behaviors changed?
- If breaking changes exist, is there a deprecation strategy or migration path?

### Phase 4: Line-Level Feedback

Walk through the diff file by file. For each notable observation:

1. **Read surrounding source code** when the diff alone lacks context. For example, if the diff modifies a method, read the full class to understand how the method fits in.
2. Provide feedback using this format:

   **`file/path.py:42`** - [ISSUE / SUGGESTION / NOTE / POSITIVE]
   Description of the finding.

   Use these severity labels:
   - **ISSUE** — something that should be fixed before merging (bugs, security, data integrity)
   - **SUGGESTION** — improvement that would make the code better but isn't blocking
   - **NOTE** — observation or question for the author to consider
   - **POSITIVE** — something done well worth calling out

3. When pointing out an issue, explain *why* it matters and suggest a fix when possible.
4. Reference specific line numbers from the diff using `file:line` format.

### Phase 5: Summary Verdict

Present the final review in this structure:

#### Overall Assessment

State one of:
- **Approve** — no issues found, or only minor suggestions
- **Request Changes** — issues that should be addressed before merging
- **Comment** — observations and questions, no strong opinion on merge readiness

#### Findings Summary

| Severity | Count | Key Areas |
|----------|-------|-----------|
| ISSUE | N | brief list |
| SUGGESTION | N | brief list |
| NOTE | N | brief list |
| POSITIVE | N | brief list |

#### Checklist Results

| Check | Result | Notes |
|-------|--------|-------|
| API spec consistency | PASS/FAIL/N/A | details |
| Model/migration alignment | PASS/FAIL/N/A | details |
| Auth & multi-tenancy | PASS/FAIL/N/A | details |
| Test coverage | PASS/FAIL/N/A | details |
| Code style | PASS/FAIL/N/A | details |
| DB considerations | PASS/FAIL/N/A | details |
| Kafka / MQ | PASS/FAIL/N/A | details |
| Security | PASS/FAIL/N/A | details |
| Breaking changes | PASS/FAIL/N/A | details |

#### Action Items

Numbered list of concrete actions the PR author should take, ordered by priority. If no actions are needed, say so.

## Important Notes

- Do NOT automatically post the review to GitHub. Present it to the user so they can read, refine, and decide whether to post.
- When the diff alone is insufficient context, use Read to examine the full source files referenced in the diff.
- Be specific and constructive — vague feedback like "this could be better" is not helpful.
- Acknowledge good work — positive feedback encourages good practices.
- Focus on substance over style — ruff and pre-commit handle formatting.
