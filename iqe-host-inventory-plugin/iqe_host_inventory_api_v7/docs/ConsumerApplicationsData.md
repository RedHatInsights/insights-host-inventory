# ConsumerApplicationsData

Application-specific metrics and metadata associated with a host.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**advisor** | [**AdvisorAppData**](AdvisorAppData.md) |  | [optional]
**vulnerability** | [**VulnerabilityAppData**](VulnerabilityAppData.md) |  | [optional]
**patch** | [**PatchAppData**](PatchAppData.md) |  | [optional]
**remediations** | [**RemediationsAppData**](RemediationsAppData.md) |  | [optional]
**compliance** | [**ComplianceAppData**](ComplianceAppData.md) |  | [optional]
**malware** | [**MalwareAppData**](MalwareAppData.md) |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.consumer_applications_data import ConsumerApplicationsData

# TODO update the JSON string below
json = "{}"
# create an instance of ConsumerApplicationsData from a JSON string
consumer_applications_data_instance = ConsumerApplicationsData.from_json(json)
# print the JSON string representation of the object
print(ConsumerApplicationsData.to_json())

# convert the object into a dict
consumer_applications_data_dict = consumer_applications_data_instance.to_dict()
# create an instance of ConsumerApplicationsData from a dict
consumer_applications_data_from_dict = ConsumerApplicationsData.from_dict(consumer_applications_data_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
