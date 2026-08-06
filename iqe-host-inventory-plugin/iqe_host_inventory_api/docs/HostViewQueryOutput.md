# HostViewQueryOutput

A paginated host view that optionally includes application data joins.
## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**count** | **int** | The number of items on the current page |
**page** | **int** | The page number |
**per_page** | **int** | The number of items to return per page |
**total** | **int** | Total number of items |
**results** | [**list[HostViewHost]**](HostViewHost.md) | Combined host and application entries. |
**denied_services** | **list[str]** | List of app_data service names the user lacks permission for. Present when per-service RBAC is active; omitted when RBAC is bypassed. | [optional]

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
