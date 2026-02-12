# iqe_host_inventory_api.GroupsApi

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
[**api_host_group_get_host_list_by_group**](GroupsApi.md#api_host_group_get_host_list_by_group) | **GET** /groups/{group_id}/hosts | Read the list of hosts in a group


# **api_group_create_group**
> GroupOutWithHostCount api_group_create_group(group_in)

Create a new group matching the provided name and list of hosts IDs

Creates a new group containing the hosts associated with the host IDs provided. <br /><br /> Required permissions: inventory:groups:write

### Example

* Api Key Authentication (ApiKeyAuth):
```python
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Configure Bearer authorization: BearerAuth
configuration = iqe_host_inventory_api.Configuration(
    access_token = 'YOUR_BEARER_TOKEN'
)

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.GroupsApi(api_client)
    group_in = iqe_host_inventory_api.GroupIn() # GroupIn | Data required to create a record for a group.

    try:
        # Create a new group matching the provided name and list of hosts IDs
        api_response = api_instance.api_group_create_group(group_in)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling GroupsApi->api_group_create_group: %s\n" % e)
```

* Bearer Authentication (BearerAuth):
```python
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Configure Bearer authorization: BearerAuth
configuration = iqe_host_inventory_api.Configuration(
    access_token = 'YOUR_BEARER_TOKEN'
)

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.GroupsApi(api_client)
    group_in = iqe_host_inventory_api.GroupIn() # GroupIn | Data required to create a record for a group.

    try:
        # Create a new group matching the provided name and list of hosts IDs
        api_response = api_instance.api_group_create_group(group_in)
        pprint(api_response)
    except ApiException as e:
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
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.GroupsApi(api_client)
    group_id_list = ['group_id_list_example'] # list[str] | A comma-separated list of group IDs.

    try:
        # Delete a list of groups
        api_instance.api_group_delete_groups(group_id_list)
    except ApiException as e:
        print("Exception when calling GroupsApi->api_group_delete_groups: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **group_id_list** | [**list[str]**](str.md)| A comma-separated list of group IDs. |

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
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.GroupsApi(api_client)
    host_id_list = ['host_id_list_example'] # list[str] | A comma-separated list of host IDs.

    try:
        # Delete a list of hosts from the groups they are in
        api_instance.api_group_delete_hosts_from_different_groups(host_id_list)
    except ApiException as e:
        print("Exception when calling GroupsApi->api_group_delete_hosts_from_different_groups: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**list[str]**](str.md)| A comma-separated list of host IDs. |

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
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.GroupsApi(api_client)
    name = 'name_example' # str | Filter by group name (optional)
per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
page = 1 # int | A page number of the items to return. (optional) (default to 1)
order_by = 'order_by_example' # str | Ordering field name (optional)
order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for name, and to DESC for host_count (optional)
group_type = 'standard' # str | The type of workspaces that should be returned. (optional) (default to 'standard')

    try:
        # Read the entire list of groups
        api_response = api_instance.api_group_get_group_list(name=name, per_page=per_page, page=page, order_by=order_by, order_how=order_how, group_type=group_type)
        pprint(api_response)
    except ApiException as e:
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
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.GroupsApi(api_client)
    group_id_list = ['group_id_list_example'] # list[str] | A comma-separated list of group IDs.
per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
page = 1 # int | A page number of the items to return. (optional) (default to 1)
order_by = 'order_by_example' # str | Ordering field name (optional)
order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for name, and to DESC for host_count (optional)

    try:
        # Find groups by their IDs
        api_response = api_instance.api_group_get_groups_by_id(group_id_list, per_page=per_page, page=page, order_by=order_by, order_how=order_how)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling GroupsApi->api_group_get_groups_by_id: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **group_id_list** | [**list[str]**](str.md)| A comma-separated list of group IDs. |
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
**404** | One or more requested resources were not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_group_patch_group_by_id**
> GroupOutWithHostCount api_group_patch_group_by_id(group_id, group_in)

Update group information

Update group information, removing any existing host associations from the group. <br /><br /> Required permissions: inventory:groups:write

### Example

* Api Key Authentication (ApiKeyAuth):
```python
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.GroupsApi(api_client)
    group_id = 'group_id_example' # str | Group ID.
group_in = iqe_host_inventory_api.GroupIn() # GroupIn | A dictionary with new information with which to update the original group.

    try:
        # Update group information
        api_response = api_instance.api_group_patch_group_by_id(group_id, group_in)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling GroupsApi->api_group_patch_group_by_id: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **group_id** | [**str**](.md)| Group ID. |
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
**404** | One or more requested resources were not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_group_add_host_list_to_group**
> GroupOutWithHostCount api_host_group_add_host_list_to_group(group_id, request_body)

Add host IDs to the provided group

Adds the host list in the request body to the provided group. <br /><br /> Required permissions: inventory:groups:write

### Example

* Api Key Authentication (ApiKeyAuth):
```python
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.GroupsApi(api_client)
    group_id = 'group_id_example' # str | Group ID.
request_body = ['request_body_example'] # list[str] | A list of hosts IDs to associate with the provided group.

    try:
        # Add host IDs to the provided group
        api_response = api_instance.api_host_group_add_host_list_to_group(group_id, request_body)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling GroupsApi->api_host_group_add_host_list_to_group: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **group_id** | [**str**](.md)| Group ID. |
 **request_body** | [**list[str]**](str.md)| A list of hosts IDs to associate with the provided group. |

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
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.GroupsApi(api_client)
    group_id = 'group_id_example' # str | Group ID.
host_id_list = ['host_id_list_example'] # list[str] | A comma-separated list of host IDs.

    try:
        # Delete one or more hosts from a group
        api_instance.api_host_group_delete_hosts_from_group(group_id, host_id_list)
    except ApiException as e:
        print("Exception when calling GroupsApi->api_host_group_delete_hosts_from_group: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **group_id** | [**str**](.md)| Group ID. |
 **host_id_list** | [**list[str]**](str.md)| A comma-separated list of host IDs. |

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

# **api_host_group_get_host_list_by_group**
> HostQueryOutput api_host_group_get_host_list_by_group(group_id, display_name=display_name, fqdn=fqdn, hostname_or_id=hostname_or_id, insights_id=insights_id, per_page=per_page, page=page, order_by=order_by, order_how=order_how, staleness=staleness, tags=tags, registered_with=registered_with, filter=filter, fields=fields)

Read the list of hosts in a group

Read the list of all hosts in a specific group. <br /><br /> Required permissions: inventory:hosts:read

### Example

* Api Key Authentication (ApiKeyAuth):
```python
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.GroupsApi(api_client)
    group_id = 'group_id_example' # str | Group ID.
display_name = 'display_name_example' # str | Filter by display_name (case-insensitive) (optional)
fqdn = 'fqdn_example' # str | Filter by FQDN (case-insensitive) (optional)
hostname_or_id = 'hostname_or_id_example' # str | Filter by display_name, fqdn, id (case-insensitive) (optional)
insights_id = 'insights_id_example' # str | Filter by insights_id (optional)
per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
page = 1 # int | A page number of the items to return. (optional) (default to 1)
order_by = 'order_by_example' # str | Ordering field name (optional)
order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system (optional)
staleness = ["fresh","stale","stale_warning"] # list[str] | Culling states of the hosts. Default: fresh, stale and stale_warning (optional) (default to ["fresh","stale","stale_warning"])
tags = ['tags_example'] # list[str] | filters out hosts not tagged by the given tags (optional)
registered_with = ['registered_with_example'] # list[str] | Filters out any host not registered by the specified reporters (optional)
filter = {'key': {}} # dict(str, object) | Filters hosts based on system_profile fields. For example: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"workloads\": {\"sap\": {\"sap_system\": {\"eq\": \"true\"}}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][sap_system][eq]=true\" <br /><br /> To get \"edge\" hosts, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"host_type\": {\"eq\": \"edge\"}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][host_type][eq]=edge\" <br /><br /> To get hosts with an specific operating system, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"operating_system\": {\"name\": {\"eq\": \"rhel\"}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][name][eq]=rhel\" (optional)
fields = {'key': {}} # dict(str, object) | Fetches only mentioned system_profile fields. For example, <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": [\"arch\", \"host_type\"]} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?fields[system_profile]=arch,host_type\" (optional)

    try:
        # Read the list of hosts in a group
        api_response = api_instance.api_host_group_get_host_list_by_group(group_id, display_name=display_name, fqdn=fqdn, hostname_or_id=hostname_or_id, insights_id=insights_id, per_page=per_page, page=page, order_by=order_by, order_how=order_how, staleness=staleness, tags=tags, registered_with=registered_with, filter=filter, fields=fields)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling GroupsApi->api_host_group_get_host_list_by_group: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **group_id** | [**str**](.md)| Group ID. |
 **display_name** | **str**| Filter by display_name (case-insensitive) | [optional]
 **fqdn** | **str**| Filter by FQDN (case-insensitive) | [optional]
 **hostname_or_id** | **str**| Filter by display_name, fqdn, id (case-insensitive) | [optional]
 **insights_id** | [**str**](.md)| Filter by insights_id | [optional]
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **order_by** | **str**| Ordering field name | [optional]
 **order_how** | **str**| Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system | [optional]
 **staleness** | [**list[str]**](str.md)| Culling states of the hosts. Default: fresh, stale and stale_warning | [optional] [default to [&quot;fresh&quot;,&quot;stale&quot;,&quot;stale_warning&quot;]]
 **tags** | [**list[str]**](str.md)| filters out hosts not tagged by the given tags | [optional]
 **registered_with** | [**list[str]**](str.md)| Filters out any host not registered by the specified reporters | [optional]
 **filter** | [**dict(str, object)**](object.md)| Filters hosts based on system_profile fields. For example: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;workloads\&quot;: {\&quot;sap\&quot;: {\&quot;sap_system\&quot;: {\&quot;eq\&quot;: \&quot;true\&quot;}}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][sap_system][eq]&#x3D;true\&quot; &lt;br /&gt;&lt;br /&gt; To get \&quot;edge\&quot; hosts, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;host_type\&quot;: {\&quot;eq\&quot;: \&quot;edge\&quot;}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][host_type][eq]&#x3D;edge\&quot; &lt;br /&gt;&lt;br /&gt; To get hosts with an specific operating system, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;operating_system\&quot;: {\&quot;name\&quot;: {\&quot;eq\&quot;: \&quot;rhel\&quot;}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][name][eq]&#x3D;rhel\&quot; | [optional]
 **fields** | [**dict(str, object)**](object.md)| Fetches only mentioned system_profile fields. For example, &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: [\&quot;arch\&quot;, \&quot;host_type\&quot;]} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?fields[system_profile]&#x3D;arch,host_type\&quot; | [optional]

### Return type

[**HostQueryOutput**](HostQueryOutput.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully read the hosts in the group. |  -  |
**404** | Group not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)
