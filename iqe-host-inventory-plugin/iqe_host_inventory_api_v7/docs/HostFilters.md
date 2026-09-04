# HostFilters

Host-level query filters that correspond to the /hosts endpoint query parameters. Stored with the view so the frontend can reconstruct the full query when loading hosts for this view.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**hostname_or_id** | **str** | Display name or ID substring search. | [optional]
**staleness** | **List[str]** | Culling states to include. | [optional]
**registered_with** | **List[str]** | Filter by reporting source. | [optional]
**tags** | **List[str]** | Tag filters in namespace/key&#x3D;value format. | [optional]
**workspace_name** | **List[str]** | Filter by workspace name. | [optional]
**last_check_in_start** | **datetime** | Start of last check-in date range (ISO 8601). | [optional]
**last_check_in_end** | **datetime** | End of last check-in date range (ISO 8601). | [optional]
**updated_start** | **datetime** | Start of last-modified date range (ISO 8601). | [optional]
**updated_end** | **datetime** | End of last-modified date range (ISO 8601). | [optional]
**system_type** | **List[str]** | Filter by system type. | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.host_filters import HostFilters

# TODO update the JSON string below
json = "{}"
# create an instance of HostFilters from a JSON string
host_filters_instance = HostFilters.from_json(json)
# print the JSON string representation of the object
print(HostFilters.to_json())

# convert the object into a dict
host_filters_dict = host_filters_instance.to_dict()
# create an instance of HostFilters from a dict
host_filters_from_dict = HostFilters.from_dict(host_filters_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
