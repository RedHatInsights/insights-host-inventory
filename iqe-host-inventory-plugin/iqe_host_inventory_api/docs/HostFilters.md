# HostFilters

Host-level query filters that correspond to the /hosts endpoint query parameters. Stored with the view so the frontend can reconstruct the full query when loading hosts for this view.
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**hostname_or_id** | **str** | Display name or ID substring search. | [optional]
**staleness** | **list[str]** | Culling states to include. | [optional]
**registered_with** | **list[str]** | Filter by reporting source. | [optional]
**tags** | **list[str]** | Tag filters in namespace/key&#x3D;value format. | [optional]
**workspace_name** | **list[str]** | Filter by workspace name. | [optional]
**last_check_in_start** | **datetime** | Start of last check-in date range (ISO 8601). | [optional]
**last_check_in_end** | **datetime** | End of last check-in date range (ISO 8601). | [optional]
**updated_start** | **datetime** | Start of last-modified date range (ISO 8601). | [optional]
**updated_end** | **datetime** | End of last-modified date range (ISO 8601). | [optional]
**system_type** | **list[str]** | Filter by system type. | [optional]

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
