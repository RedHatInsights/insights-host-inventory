# HostIdOut

A single Host ID that belongs to a host.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.host_id_out import HostIdOut

# TODO update the JSON string below
json = "{}"
# create an instance of HostIdOut from a JSON string
host_id_out_instance = HostIdOut.from_json(json)
# print the JSON string representation of the object
print(HostIdOut.to_json())

# convert the object into a dict
host_id_out_dict = host_id_out_instance.to_dict()
# create an instance of HostIdOut from a dict
host_id_out_from_dict = HostIdOut.from_dict(host_id_out_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
