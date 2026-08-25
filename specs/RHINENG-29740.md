# Spec: RHINENG-29740

## Summary
RHINENG-29740: Konflux onboarding stage release for cost-management-rhdh-plugin — Enterprise Contract (EC) failures block the stage release pipeline. In the insights-host-inventory repository specifically, the security-compliance (SC) Tekton pipeline files pin the `docker-build-oci-ta` pipeline to `main` (unpinned) instead of the tagged version `v1.72.0` used by the non-SC files, creating inconsistency and potential EC non-compliance.

## Root Cause
The Jira task involves fixing Konflux pipeline EC failures and triggering a stage release. In the insights-host-inventory repo, the two SC PipelineRun files (`.tekton/insights-host-inventory-sc-pull-request.yaml` and `.tekton/insights-host-inventory-sc-push.yaml`) reference the `docker-build-oci-ta` pipeline via `https://github.com/RedHatInsights/konflux-pipelines/raw/main/pipelines/docker-build-oci-ta.yaml` — using the `main` branch instead of a pinned tag. By contrast, the non-SC equivalents were already updated (from `v1.71.0` to `v1.72.0`) in recent commits. Using `main` means the SC pipelines are not reproducible, bypass Renovate/MintMaker version tracking, and may pick up untrusted or non-EC-compliant task versions. The same class of problem described in the Jira comments (old/untrusted `prefetch-dependencies-oci-ta` < 0.7.1 causing Conforma to fail) can manifest here if `main` drifts to a version that doesn't meet the Enterprise Contract policy.

## Plan

- `.tekton/insights-host-inventory-sc-pull-request.yaml` (modify): Replace the `main` branch reference in the `pipelinesascode.tekton.dev/pipeline` annotation with the pinned tag `v1.72.0`, matching the pattern already used in `.tekton/insights-host-inventory-pull-request.yaml`.

- `.tekton/insights-host-inventory-sc-push.yaml` (modify): Replace the `main` branch reference in the `pipelinesascode.tekton.dev/pipeline` annotation with the pinned tag `v1.72.0`, matching the pattern already used in `.tekton/insights-host-inventory-push.yaml`.

## Constraints
- Only the `pipelinesascode.tekton.dev/pipeline` annotation value must change; all other fields (workspaces, params, serviceAccountName, labels) must remain untouched.
- The SC-specific `volumeClaimTemplate` workspace (ReadWriteOnce, 1Gi) must not be replaced with the OCI-TA trusted-artifact pattern used by the non-SC files — that difference is intentional.
