# GroupOut

Data of a single group belonging to an account.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** |  | [optional]
**name** | **str** | A group’s human-readable name. | [optional]
**account** | **str** | A Red Hat Account number that owns the host. | [optional]
**org_id** | **str** | The Org ID of the tenant that owns the host. | [optional]
**ungrouped** | **bool** | Whether the group is the \&quot;ungrouped hosts\&quot; group | [optional]
**created** | **datetime** | A timestamp when the entry was created. | [optional]
**updated** | **datetime** | A timestamp when the entry was last updated. | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.group_out import GroupOut

# TODO update the JSON string below
json = "{}"
# create an instance of GroupOut from a JSON string
group_out_instance = GroupOut.from_json(json)
# print the JSON string representation of the object
print(GroupOut.to_json())

# convert the object into a dict
group_out_dict = group_out_instance.to_dict()
# create an instance of GroupOut from a dict
group_out_from_dict = GroupOut.from_dict(group_out_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
