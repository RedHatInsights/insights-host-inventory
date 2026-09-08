# ViewConfiguration

The full visual configuration for an inventory view, including column layout, sort order, and active filters.
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**columns** | [**list[ViewColumnConfig]**](ViewColumnConfig.md) | Ordered list of column configurations. |
**sort** | [**ViewSortConfig**](ViewSortConfig.md) |  | [optional]
**filters** | **dict(str, object)** | Active filter criteria for this view. Top-level keys are filter namespaces: app names (e.g. vulnerability, patch), system_profile, or host (for host-level query parameters). Each namespace value is a nested object. system_profile filters may be deeply nested (e.g. operating_system.RHEL.version). The reserved \&quot;host\&quot; key holds host-level query parameters (staleness, tags, etc.) that the frontend replays as /hosts query params. Validated server-side. | [optional]

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
