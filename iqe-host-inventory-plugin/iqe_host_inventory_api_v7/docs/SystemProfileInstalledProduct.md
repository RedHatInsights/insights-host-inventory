# SystemProfileInstalledProduct

Representation of one installed product

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**name** | **str** |  | [optional]
**id** | **str** | The product ID | [optional]
**status** | **str** | Subscription status for product | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.system_profile_installed_product import SystemProfileInstalledProduct

# TODO update the JSON string below
json = "{}"
# create an instance of SystemProfileInstalledProduct from a JSON string
system_profile_installed_product_instance = SystemProfileInstalledProduct.from_json(json)
# print the JSON string representation of the object
print(SystemProfileInstalledProduct.to_json())

# convert the object into a dict
system_profile_installed_product_dict = system_profile_installed_product_instance.to_dict()
# create an instance of SystemProfileInstalledProduct from a dict
system_profile_installed_product_from_dict = SystemProfileInstalledProduct.from_dict(system_profile_installed_product_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
