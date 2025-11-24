# TagsOut


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**count** | **int** | The number of items on the current page |
**page** | **int** | The page number |
**per_page** | **int** | The number of items to return per page |
**total** | **int** | Total number of items |
**results** | **Dict[str, List[StructuredTag]]** | The list of tags on the systems | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.tags_out import TagsOut

# TODO update the JSON string below
json = "{}"
# create an instance of TagsOut from a JSON string
tags_out_instance = TagsOut.from_json(json)
# print the JSON string representation of the object
print(TagsOut.to_json())

# convert the object into a dict
tags_out_dict = tags_out_instance.to_dict()
# create an instance of TagsOut from a dict
tags_out_from_dict = TagsOut.from_dict(tags_out_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
