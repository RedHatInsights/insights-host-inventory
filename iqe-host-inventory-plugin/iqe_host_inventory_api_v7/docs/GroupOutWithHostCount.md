# GroupOutWithHostCount

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
**host_count** | **int** | The number of hosts associated with the group. | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.group_out_with_host_count import GroupOutWithHostCount

# TODO update the JSON string below
json = "{}"
# create an instance of GroupOutWithHostCount from a JSON string
group_out_with_host_count_instance = GroupOutWithHostCount.from_json(json)
# print the JSON string representation of the object
print(GroupOutWithHostCount.to_json())

# convert the object into a dict
group_out_with_host_count_dict = group_out_with_host_count_instance.to_dict()
# create an instance of GroupOutWithHostCount from a dict
group_out_with_host_count_from_dict = GroupOutWithHostCount.from_dict(group_out_with_host_count_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
