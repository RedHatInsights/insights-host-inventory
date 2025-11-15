# iqe_host_inventory_api_v7.ResourceTypesApi

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**api_resource_type_get_resource_type_groups_list**](ResourceTypesApi.md#api_resource_type_get_resource_type_groups_list) | **GET** /resource-types/inventory-groups | Get the list of inventory groups in resource-types format
[**api_resource_type_get_resource_type_list**](ResourceTypesApi.md#api_resource_type_get_resource_type_list) | **GET** /resource-types | Get the list of resource types


# **api_resource_type_get_resource_type_groups_list**
> ResourceTypesGroupsQueryOutput api_resource_type_get_resource_type_groups_list(name=name, per_page=per_page, page=page)

Get the list of inventory groups in resource-types format

Returns the list of groups in the current account. <br /><br /> Required permissions: rbac:*:*

### Example

* Api Key Authentication (ApiKeyAuth):

```python
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.resource_types_groups_query_output import ResourceTypesGroupsQueryOutput
from iqe_host_inventory_api_v7.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to http://localhost
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api_v7.Configuration(
    host = "http://localhost"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration.api_key['ApiKeyAuth'] = os.environ["API_KEY"]

# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['ApiKeyAuth'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api_v7.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api_v7.ResourceTypesApi(api_client)
    name = 'name_example' # str | Filter by group name (optional)
    per_page = 10 # int | A number of items to return per page. (optional) (default to 10)
    page = 1 # int | A page number of the items to return. (optional) (default to 1)

    try:
        # Get the list of inventory groups in resource-types format
        api_response = api_instance.api_resource_type_get_resource_type_groups_list(name=name, per_page=per_page, page=page)
        print("The response of ResourceTypesApi->api_resource_type_get_resource_type_groups_list:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ResourceTypesApi->api_resource_type_get_resource_type_groups_list: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **name** | **str**| Filter by group name | [optional]
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 10]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]

### Return type

[**ResourceTypesGroupsQueryOutput**](ResourceTypesGroupsQueryOutput.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully read the resource-types groups list. |  -  |
**400** | Groups not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_resource_type_get_resource_type_list**
> ResourceTypesQueryOutput api_resource_type_get_resource_type_list(per_page=per_page, page=page)

Get the list of resource types

Returns the list of available RBAC resource types. <br /><br /> Required permissions: rbac:*:*

### Example

* Api Key Authentication (ApiKeyAuth):

```python
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.resource_types_query_output import ResourceTypesQueryOutput
from iqe_host_inventory_api_v7.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to http://localhost
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api_v7.Configuration(
    host = "http://localhost"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration.api_key['ApiKeyAuth'] = os.environ["API_KEY"]

# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['ApiKeyAuth'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api_v7.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api_v7.ResourceTypesApi(api_client)
    per_page = 10 # int | A number of items to return per page. (optional) (default to 10)
    page = 1 # int | A page number of the items to return. (optional) (default to 1)

    try:
        # Get the list of resource types
        api_response = api_instance.api_resource_type_get_resource_type_list(per_page=per_page, page=page)
        print("The response of ResourceTypesApi->api_resource_type_get_resource_type_list:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling ResourceTypesApi->api_resource_type_get_resource_type_list: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 10]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]

### Return type

[**ResourceTypesQueryOutput**](ResourceTypesQueryOutput.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully read the resource types list. |  -  |
**400** | Resource types not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)
