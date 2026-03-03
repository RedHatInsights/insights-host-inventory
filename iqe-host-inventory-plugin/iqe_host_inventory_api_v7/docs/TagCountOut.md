# TagCountOut


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**count** | **int** | The number of items on the current page |
**page** | **int** | The page number |
**per_page** | **int** | The number of items to return per page |
**total** | **int** | Total number of items |
**results** | **Dict[str, int]** | The list of tags on the systems | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.tag_count_out import TagCountOut

# TODO update the JSON string below
json = "{}"
# create an instance of TagCountOut from a JSON string
tag_count_out_instance = TagCountOut.from_json(json)
# print the JSON string representation of the object
print(TagCountOut.to_json())

# convert the object into a dict
tag_count_out_dict = tag_count_out_instance.to_dict()
# create an instance of TagCountOut from a dict
tag_count_out_from_dict = TagCountOut.from_dict(tag_count_out_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
