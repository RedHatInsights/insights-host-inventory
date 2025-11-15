# PerReporterStaleness


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**last_check_in** | **datetime** |  | [optional]
**stale_timestamp** | **datetime** |  | [optional]
**stale_warning_timestamp** | **datetime** |  | [optional]
**culled_timestamp** | **datetime** |  | [optional]
**check_in_succeeded** | **bool** |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.per_reporter_staleness import PerReporterStaleness

# TODO update the JSON string below
json = "{}"
# create an instance of PerReporterStaleness from a JSON string
per_reporter_staleness_instance = PerReporterStaleness.from_json(json)
# print the JSON string representation of the object
print(PerReporterStaleness.to_json())

# convert the object into a dict
per_reporter_staleness_dict = per_reporter_staleness_instance.to_dict()
# create an instance of PerReporterStaleness from a dict
per_reporter_staleness_from_dict = PerReporterStaleness.from_dict(per_reporter_staleness_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
