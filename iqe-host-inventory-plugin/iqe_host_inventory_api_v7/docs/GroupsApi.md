# iqe_host_inventory_api_v7.GroupsApi

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**api_group_create_group**](GroupsApi.md#api_group_create_group) | **POST** /groups | Create a new group matching the provided name and list of hosts IDs
[**api_group_delete_groups**](GroupsApi.md#api_group_delete_groups) | **DELETE** /groups/{group_id_list} | Delete a list of groups
[**api_group_delete_hosts_from_different_groups**](GroupsApi.md#api_group_delete_hosts_from_different_groups) | **DELETE** /groups/hosts/{host_id_list} | Delete a list of hosts from the groups they are in
[**api_group_get_group_list**](GroupsApi.md#api_group_get_group_list) | **GET** /groups | Read the entire list of groups
[**api_group_get_groups_by_id**](GroupsApi.md#api_group_get_groups_by_id) | **GET** /groups/{group_id_list} | Find groups by their IDs
[**api_group_patch_group_by_id**](GroupsApi.md#api_group_patch_group_by_id) | **PATCH** /groups/{group_id} | Update group information
[**api_host_group_add_host_list_to_group**](GroupsApi.md#api_host_group_add_host_list_to_group) | **POST** /groups/{group_id}/hosts | Add host IDs to the provided group
[**api_host_group_delete_hosts_from_group**](GroupsApi.md#api_host_group_delete_hosts_from_group) | **DELETE** /groups/{group_id}/hosts/{host_id_list} | Delete one or more hosts from a group


# **api_group_create_group**
> GroupOutWithHostCount api_group_create_group(group_in)

Create a new group matching the provided name and list of hosts IDs

Creates a new group containing the hosts associated with the host IDs provided. <br /><br /> Required permissions: inventory:groups:write

### Example

* Api Key Authentication (ApiKeyAuth):
* Bearer Authentication (BearerAuth):

```python
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.group_in import GroupIn
from iqe_host_inventory_api_v7.models.group_out_with_host_count import GroupOutWithHostCount
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

# Configure Bearer authorization: BearerAuth
configuration = iqe_host_inventory_api_v7.Configuration(
    access_token = os.environ["BEARER_TOKEN"]
)

# Enter a context with an instance of the API client
with iqe_host_inventory_api_v7.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api_v7.GroupsApi(api_client)
    group_in = iqe_host_inventory_api_v7.GroupIn() # GroupIn | Data required to create a record for a group.

    try:
        # Create a new group matching the provided name and list of hosts IDs
        api_response = api_instance.api_group_create_group(group_in)
        print("The response of GroupsApi->api_group_create_group:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling GroupsApi->api_group_create_group: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **group_in** | [**GroupIn**](GroupIn.md)| Data required to create a record for a group. |

### Return type

[**GroupOutWithHostCount**](GroupOutWithHostCount.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth), [BearerAuth](../README.md#BearerAuth)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**201** | Successfully created new Group. |  -  |
**400** | Invalid request. |  -  |
**403** | Forbidden - Invalid RBAC permission. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_group_delete_groups**
> api_group_delete_groups(group_id_list)

Delete a list of groups

Delete a list of groups. <br /><br /> Required permissions: inventory:groups:write

### Example

* Api Key Authentication (ApiKeyAuth):

```python
import iqe_host_inventory_api_v7
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
    api_instance = iqe_host_inventory_api_v7.GroupsApi(api_client)
    group_id_list = ['group_id_list_example'] # List[str] | A comma-separated list of group IDs.

    try:
        # Delete a list of groups
        api_instance.api_group_delete_groups(group_id_list)
    except Exception as e:
        print("Exception when calling GroupsApi->api_group_delete_groups: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **group_id_list** | [**List[str]**](str.md)| A comma-separated list of group IDs. |

### Return type

void (empty response body)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: Not defined

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**204** | The groups were successfully deleted. |  -  |
**400** | Invalid request. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_group_delete_hosts_from_different_groups**
> api_group_delete_hosts_from_different_groups(host_id_list)

Delete a list of hosts from the groups they are in

Delete a list of hosts from the groups they are in. <br /><br /> Required permissions: inventory:groups:write

### Example

* Api Key Authentication (ApiKeyAuth):

```python
import iqe_host_inventory_api_v7
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
    api_instance = iqe_host_inventory_api_v7.GroupsApi(api_client)
    host_id_list = ['host_id_list_example'] # List[str] | A comma-separated list of host IDs.

    try:
        # Delete a list of hosts from the groups they are in
        api_instance.api_group_delete_hosts_from_different_groups(host_id_list)
    except Exception as e:
        print("Exception when calling GroupsApi->api_group_delete_hosts_from_different_groups: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**List[str]**](str.md)| A comma-separated list of host IDs. |

### Return type

void (empty response body)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: Not defined

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**204** | The hosts were successfully removed from their groups. |  -  |
**400** | Invalid request. |  -  |
**404** | The provided hosts are ungrouped. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_group_get_group_list**
> GroupQueryOutput api_group_get_group_list(name=name, per_page=per_page, page=page, order_by=order_by, order_how=order_how, group_type=group_type)

Read the entire list of groups

Read the entire list of all groups available to the account. <br /><br /> Required permissions: inventory:groups:read

### Example

* Api Key Authentication (ApiKeyAuth):

```python
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.group_query_output import GroupQueryOutput
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
    api_instance = iqe_host_inventory_api_v7.GroupsApi(api_client)
    name = 'name_example' # str | Filter by group name (optional)
    per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
    page = 1 # int | A page number of the items to return. (optional) (default to 1)
    order_by = 'order_by_example' # str | Ordering field name (optional)
    order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for name, and to DESC for host_count (optional)
    group_type = 'standard' # str | The type of workspaces that should be returned. (optional) (default to 'standard')

    try:
        # Read the entire list of groups
        api_response = api_instance.api_group_get_group_list(name=name, per_page=per_page, page=page, order_by=order_by, order_how=order_how, group_type=group_type)
        print("The response of GroupsApi->api_group_get_group_list:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling GroupsApi->api_group_get_group_list: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **name** | **str**| Filter by group name | [optional]
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **order_by** | **str**| Ordering field name | [optional]
 **order_how** | **str**| Direction of the ordering (case-insensitive); defaults to ASC for name, and to DESC for host_count | [optional]
 **group_type** | **str**| The type of workspaces that should be returned. | [optional] [default to &#39;standard&#39;]

### Return type

[**GroupQueryOutput**](GroupQueryOutput.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully read the groups list. |  -  |
**400** | Groups not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_group_get_groups_by_id**
> GroupQueryOutput api_group_get_groups_by_id(group_id_list, per_page=per_page, page=page, order_by=order_by, order_how=order_how)

Find groups by their IDs

Find one or more groups by their IDs. <br /><br /> Required permissions: inventory:groups:read

### Example

* Api Key Authentication (ApiKeyAuth):

```python
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.group_query_output import GroupQueryOutput
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
    api_instance = iqe_host_inventory_api_v7.GroupsApi(api_client)
    group_id_list = ['group_id_list_example'] # List[str] | A comma-separated list of group IDs.
    per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
    page = 1 # int | A page number of the items to return. (optional) (default to 1)
    order_by = 'order_by_example' # str | Ordering field name (optional)
    order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for name, and to DESC for host_count (optional)

    try:
        # Find groups by their IDs
        api_response = api_instance.api_group_get_groups_by_id(group_id_list, per_page=per_page, page=page, order_by=order_by, order_how=order_how)
        print("The response of GroupsApi->api_group_get_groups_by_id:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling GroupsApi->api_group_get_groups_by_id: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **group_id_list** | [**List[str]**](str.md)| A comma-separated list of group IDs. |
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **order_by** | **str**| Ordering field name | [optional]
 **order_how** | **str**| Direction of the ordering (case-insensitive); defaults to ASC for name, and to DESC for host_count | [optional]

### Return type

[**GroupQueryOutput**](GroupQueryOutput.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully searched for groups. |  -  |
**400** | Invalid request. |  -  |
**404** | Groups not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_group_patch_group_by_id**
> GroupOutWithHostCount api_group_patch_group_by_id(group_id, group_in)

Update group information

Update group information, removing any existing host associations from the group. <br /><br /> Required permissions: inventory:groups:write

### Example

* Api Key Authentication (ApiKeyAuth):

```python
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.group_in import GroupIn
from iqe_host_inventory_api_v7.models.group_out_with_host_count import GroupOutWithHostCount
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
    api_instance = iqe_host_inventory_api_v7.GroupsApi(api_client)
    group_id = 'group_id_example' # str | Group ID.
    group_in = iqe_host_inventory_api_v7.GroupIn() # GroupIn | A dictionary with new information with which to update the original group.

    try:
        # Update group information
        api_response = api_instance.api_group_patch_group_by_id(group_id, group_in)
        print("The response of GroupsApi->api_group_patch_group_by_id:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling GroupsApi->api_group_patch_group_by_id: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **group_id** | **str**| Group ID. |
 **group_in** | [**GroupIn**](GroupIn.md)| A dictionary with new information with which to update the original group. |

### Return type

[**GroupOutWithHostCount**](GroupOutWithHostCount.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Group information successfully updated. |  -  |
**400** | Invalid request. |  -  |
**404** | Group not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_group_add_host_list_to_group**
> GroupOutWithHostCount api_host_group_add_host_list_to_group(group_id, request_body)

Add host IDs to the provided group

Adds the host list in the request body to the provided group. <br /><br /> Required permissions: inventory:groups:write

### Example

* Api Key Authentication (ApiKeyAuth):

```python
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.group_out_with_host_count import GroupOutWithHostCount
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
    api_instance = iqe_host_inventory_api_v7.GroupsApi(api_client)
    group_id = 'group_id_example' # str | Group ID.
    request_body = ['request_body_example'] # List[str] | A list of hosts IDs to associate with the provided group.

    try:
        # Add host IDs to the provided group
        api_response = api_instance.api_host_group_add_host_list_to_group(group_id, request_body)
        print("The response of GroupsApi->api_host_group_add_host_list_to_group:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling GroupsApi->api_host_group_add_host_list_to_group: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **group_id** | **str**| Group ID. |
 **request_body** | [**List[str]**](str.md)| A list of hosts IDs to associate with the provided group. |

### Return type

[**GroupOutWithHostCount**](GroupOutWithHostCount.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Hosts successfully or already previously associated with group. |  -  |
**400** | Invalid request. |  -  |
**404** | Group not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_group_delete_hosts_from_group**
> api_host_group_delete_hosts_from_group(group_id, host_id_list)

Delete one or more hosts from a group

Delete one or more hosts from a group. <br /><br /> Required permissions: inventory:groups:write

### Example

* Api Key Authentication (ApiKeyAuth):

```python
import iqe_host_inventory_api_v7
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
    api_instance = iqe_host_inventory_api_v7.GroupsApi(api_client)
    group_id = 'group_id_example' # str | Group ID.
    host_id_list = ['host_id_list_example'] # List[str] | A comma-separated list of host IDs.

    try:
        # Delete one or more hosts from a group
        api_instance.api_host_group_delete_hosts_from_group(group_id, host_id_list)
    except Exception as e:
        print("Exception when calling GroupsApi->api_host_group_delete_hosts_from_group: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **group_id** | **str**| Group ID. |
 **host_id_list** | [**List[str]**](str.md)| A comma-separated list of host IDs. |

### Return type

void (empty response body)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: Not defined

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**204** | Successfully deleted hosts. |  -  |
**400** | Invalid request. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)
