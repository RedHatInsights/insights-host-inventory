# Spec: RHINENG-13148

## Summary
Remove infinite recursion and x-propertyNames from system profile schema

## Root Cause
The system profile schema (swagger/system_profile.spec.yaml) defines NestedObject with an infinite recursion in its additionalProperties (referencing itself via $ref: '#/$defs/NestedObject') and includes the non-standard 'x-propertyNames' property. This causes infinite recursion issues with security scanners like rapidast. Since there is no custom validator in the codebase that processes 'x-propertyNames', and empty keys are already validated programmatically via the check_empty_keys validator in Python, we can safely remove the infinite recursion and 'x-propertyNames' from the schema.

## Plan

- `swagger/system_profile.spec.yaml` (modify): In the NestedObject definition (lines 5–15), remove the comment about x-propertyNames, remove the x-propertyNames property (and its minLength child), and replace the recursive additionalProperties (the oneOf with the self-referencing $ref and not-object) with a simple additionalProperties: true. The resulting NestedObject should be a plain object type with additionalProperties: true, retaining only its type and description.

- `swagger/openapi.json` (regenerate): Automatically regenerated and validated by the existing Swagger bundle pre-commit hook. No manual steps needed.

- `swagger/openapi_v2.json` (regenerate): Automatically regenerated and validated by the existing Swagger bundle pre-commit hook. No manual steps needed.

## Constraints
- Do not modify the DiskDevice definition or any other schema that references NestedObject — only the NestedObject definition itself should change
- Do not modify the check_empty_keys Python validator or any other Python validation code
