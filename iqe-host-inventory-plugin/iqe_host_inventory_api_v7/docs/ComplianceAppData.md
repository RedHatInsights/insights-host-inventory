# ComplianceAppData


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**policies** | **List[object]** |  | [optional]
**last_scan** | **datetime** |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.compliance_app_data import ComplianceAppData

# TODO update the JSON string below
json = "{}"
# create an instance of ComplianceAppData from a JSON string
compliance_app_data_instance = ComplianceAppData.from_json(json)
# print the JSON string representation of the object
print(ComplianceAppData.to_json())

# convert the object into a dict
compliance_app_data_dict = compliance_app_data_instance.to_dict()
# create an instance of ComplianceAppData from a dict
compliance_app_data_from_dict = ComplianceAppData.from_dict(compliance_app_data_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
