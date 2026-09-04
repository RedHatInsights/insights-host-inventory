# ViewConfigurationFilters

Active filter criteria for this view. Top-level keys are filter namespaces: app names (e.g. vulnerability, patch), system_profile, or host (for host-level query parameters). Each namespace value is a nested object. system_profile filters may be deeply nested (e.g. operating_system.RHEL.version). The reserved \"host\" key holds host-level query parameters (staleness, tags, etc.) that the frontend replays as /hosts query params. Validated server-side.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**host** | [**HostFilters**](HostFilters.md) |  | [optional]

## Example

```python
from iqe_host_inventory_api_v7.models.view_configuration_filters import ViewConfigurationFilters

# TODO update the JSON string below
json = "{}"
# create an instance of ViewConfigurationFilters from a JSON string
view_configuration_filters_instance = ViewConfigurationFilters.from_json(json)
# print the JSON string representation of the object
print(ViewConfigurationFilters.to_json())

# convert the object into a dict
view_configuration_filters_dict = view_configuration_filters_instance.to_dict()
# create an instance of ViewConfigurationFilters from a dict
view_configuration_filters_from_dict = ViewConfigurationFilters.from_dict(
    view_configuration_filters_dict
)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
