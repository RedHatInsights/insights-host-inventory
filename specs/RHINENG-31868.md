# Spec: RHINENG-31868

## Summary
Update V2 API specification externalDocs description to 'Red Hat Lightspeed' for status.redhat.com consistency

## Root Cause
When the V2 API spec skeleton was added in a later commit, the `externalDocs` description in `swagger/api_v2.spec.yaml` and `swagger/openapi_v2.json` was set to 'How to use the Red Hat Insights API' instead of 'Using APIs to configure Red Hat Lightspeed services' (which was already correctly updated for V1 in commit 16d57e52). This inconsistency causes status.redhat.com to display 'Insights' instead of 'Red Hat Lightspeed' for the V2 services.

## Plan

- `swagger/api_v2.spec.yaml` (modify): Change the `externalDocs.description` value on line 15 from 'How to use the Red Hat Insights API' to 'Using APIs to configure Red Hat Lightspeed services', matching the V1 spec (`swagger/api.spec.yaml` line 11).

- `swagger/openapi_v2.json` (modify): Change the `externalDocs.description` value from 'How to use the Red Hat Insights API' to 'Using APIs to configure Red Hat Lightspeed services', matching the V1 JSON spec (`swagger/openapi.json`).

## Constraints
- The exact description string must be 'Using APIs to configure Red Hat Lightspeed services' — no variation.
