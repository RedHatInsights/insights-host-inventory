# GroupIn

Data of a single group belonging to an account.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**name** | **str** | A group’s human-readable name. | [optional]
**host_ids** | **List[str]** | A comma-separated list of host IDs that belong to the group. | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.group_in import GroupIn

# TODO update the JSON string below
json = "{}"
# create an instance of GroupIn from a JSON string
group_in_instance = GroupIn.from_json(json)
# print the JSON string representation of the object
print(GroupIn.to_json())

# convert the object into a dict
group_in_dict = group_in_instance.to_dict()
# create an instance of GroupIn from a dict
group_in_from_dict = GroupIn.from_dict(group_in_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
