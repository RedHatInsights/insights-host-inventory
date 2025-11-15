# StalenessIn

Data of a single account staleness.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**conventional_time_to_stale** | **int** |  | [optional]
**conventional_time_to_stale_warning** | **int** |  | [optional]
**conventional_time_to_delete** | **int** |  | [optional]
**immutable_time_to_stale** | **int** |  | [optional]
**immutable_time_to_stale_warning** | **int** |  | [optional]
**immutable_time_to_delete** | **int** |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.staleness_in import StalenessIn

# TODO update the JSON string below
json = "{}"
# create an instance of StalenessIn from a JSON string
staleness_in_instance = StalenessIn.from_json(json)
# print the JSON string representation of the object
print(StalenessIn.to_json())

# convert the object into a dict
staleness_in_dict = staleness_in_instance.to_dict()
# create an instance of StalenessIn from a dict
staleness_in_from_dict = StalenessIn.from_dict(staleness_in_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
