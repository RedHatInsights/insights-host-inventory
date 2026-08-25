# Spec: RHINENG-30276

## Summary
Remove Jira automation connector from the #cloudservices-[service] Slack channel and archive or repurpose the channel

## Root Cause
The repository (Host Based Inventory / HBI) has an associated Slack channel following the #cloudservices-[service] naming convention. A Jira-Slack connector (Jira for Slack app or Jira automation rule) was configured to post Jira issue updates to this channel. The team is decommissioning this integration. Within the repository itself, the `.github/workflows/pr-review-reminder.yaml` workflow posts daily Slack notifications via a `SLACK_WEBHOOK_URL` secret — this is the in-repo Slack integration mechanism. Additionally, `README.md` contains hardcoded references to Slack channel URLs (#team-insights-inventory at CQFKM031T, and 'Inventory Slack Channel' at C01A49ZGQ05) that may need to be updated if channels are archived or repurposed. The Jira connector itself is configured in Jira/Slack admin settings (external to the repository), but any documentation or workflow pointing to the affected channel must be updated in-repo.

## Plan

- `README.md` (modify): In the '5. Monitoring of deployment' section (around line 730), replace the hardcoded 'Inventory Slack Channel' link (pointing to channel C01A49ZGQ05 in workspace T027F3GAJ) with a reference to the team's active Slack channel (#team-insights-inventory, already linked at line 651). This consolidates both mentions to the same live channel and removes the stale link to the channel being decommissioned.

## Constraints
- The Jira-Slack connector removal itself is an administrative action in Jira project settings — no repository file contains the connector configuration.
- The SLACK_WEBHOOK_URL secret in pr-review-reminder.yaml determines which Slack channel receives PR reminders; if it currently points to the decommissioned channel, the GitHub Actions secret must be updated in repository settings (not a code change).
- Archiving the #cloudservices-[service] Slack channel is a Slack admin action, not a code change.
- Do not remove the #team-insights-inventory link at line 651 — it is the team's active channel and must remain.
