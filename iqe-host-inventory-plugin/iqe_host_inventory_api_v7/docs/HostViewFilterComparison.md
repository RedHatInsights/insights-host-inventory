# HostViewFilterComparison

Supported comparison operators for application metrics filtering.  **Value comparisons:** - `eq` - Equal to - `ne` - Not equal to - `gt` - Greater than - `lt` - Less than - `gte` - Greater than or equal to - `lte` - Less than or equal to  **Null checks:** - `nil` - Field is null/missing - `not_nil` - Field is not null/exists

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**eq** | **str** |  | [optional]
**ne** | **str** |  | [optional]
**gt** | **str** |  | [optional]
**lt** | **str** |  | [optional]
**gte** | **str** |  | [optional]
**lte** | **str** |  | [optional]
**nil** | **bool** | When true, matches hosts where this field is null/missing. | [optional]
**not_nil** | **bool** | When true, matches hosts where this field exists and is not null. | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.host_view_filter_comparison import HostViewFilterComparison

# TODO update the JSON string below
json = "{}"
# create an instance of HostViewFilterComparison from a JSON string
host_view_filter_comparison_instance = HostViewFilterComparison.from_json(json)
# print the JSON string representation of the object
print(HostViewFilterComparison.to_json())

# convert the object into a dict
host_view_filter_comparison_dict = host_view_filter_comparison_instance.to_dict()
# create an instance of HostViewFilterComparison from a dict
host_view_filter_comparison_from_dict = HostViewFilterComparison.from_dict(host_view_filter_comparison_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
