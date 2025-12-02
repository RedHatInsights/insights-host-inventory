# StalenessOutput

Data of a account staleness.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**conventional_time_to_stale** | **int** |  |
**conventional_time_to_stale_warning** | **int** |  |
**conventional_time_to_delete** | **int** |  |
**immutable_time_to_stale** | **int** |  |
**immutable_time_to_stale_warning** | **int** |  |
**immutable_time_to_delete** | **int** |  |
**id** | [**StalenessId**](StalenessId.md) |  |
**org_id** | **str** | The Org ID of the tenant that owns the host. |
**created** | **datetime** | A timestamp when the entry was created. |
**updated** | **datetime** | A timestamp when the entry was last updated. |

## Example

```python
from iqe_host_inventory_api_v7.models.staleness_output import StalenessOutput

# TODO update the JSON string below
json = "{}"
# create an instance of StalenessOutput from a JSON string
staleness_output_instance = StalenessOutput.from_json(json)
# print the JSON string representation of the object
print(StalenessOutput.to_json())

# convert the object into a dict
staleness_output_dict = staleness_output_instance.to_dict()
# create an instance of StalenessOutput from a dict
staleness_output_from_dict = StalenessOutput.from_dict(staleness_output_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
