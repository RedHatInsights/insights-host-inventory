# iqe_host_inventory_api.ViewsApi

All URIs are relative to *http://localhost/api/inventory/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**api_views_clone_view**](ViewsApi.md#api_views_clone_view) | **POST** /beta/views/{view_id}/clone | Clone an inventory view
[**api_views_create_view**](ViewsApi.md#api_views_create_view) | **POST** /beta/views | Create a new inventory view
[**api_views_delete_view**](ViewsApi.md#api_views_delete_view) | **DELETE** /beta/views/{view_id} | Delete an inventory view
[**api_views_get_view_by_id**](ViewsApi.md#api_views_get_view_by_id) | **GET** /beta/views/{view_id} | Get a single inventory view
[**api_views_get_views_list**](ViewsApi.md#api_views_get_views_list) | **GET** /beta/views | Read the list of inventory views
[**api_views_update_view**](ViewsApi.md#api_views_update_view) | **PUT** /beta/views/{view_id} | Update an inventory view


# **api_views_clone_view**
> ViewOut api_views_clone_view(view_id)

Clone an inventory view

Creates a copy of any visible view (including system views) as a new private view owned by the requesting user. The cloned view name is prefixed with \"Copy of \". <br /><br /> Required permissions: inventory:views:write <br /><br /> <b>NOTE:</b> This endpoint is not yet implemented and will return HTTP 501.

### Example

* Api Key Authentication (ApiKeyAuth):
```python
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost/api/inventory/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost/api/inventory/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost/api/inventory/v1",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.ViewsApi(api_client)
    view_id = 'view_id_example' # str | View ID.

    try:
        # Clone an inventory view
        api_response = api_instance.api_views_clone_view(view_id)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling ViewsApi->api_views_clone_view: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **view_id** | [**str**](.md)| View ID. |

### Return type

[**ViewOut**](ViewOut.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**201** | Successfully cloned the inventory view. |  -  |
**403** | Forbidden - identity type not supported or missing username. |  -  |
**404** | Source view not found or not visible to the requesting user. |  -  |
**501** | Not yet implemented. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_views_create_view**
> ViewOut api_views_create_view(view_in)

Create a new inventory view

Creates a new inventory view with the provided name and configuration. The view is owned by the requesting user. <br /><br /> Required permissions: inventory:views:write <br /><br /> <b>NOTE:</b> This endpoint is not yet implemented and will return HTTP 501.

### Example

* Api Key Authentication (ApiKeyAuth):
```python
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost/api/inventory/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost/api/inventory/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost/api/inventory/v1",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.ViewsApi(api_client)
    view_in = iqe_host_inventory_api.ViewIn() # ViewIn | Data required to create a new inventory view.

    try:
        # Create a new inventory view
        api_response = api_instance.api_views_create_view(view_in)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling ViewsApi->api_views_create_view: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **view_in** | [**ViewIn**](ViewIn.md)| Data required to create a new inventory view. |

### Return type

[**ViewOut**](ViewOut.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**201** | Successfully created the inventory view. |  -  |
**400** | Invalid request. |  -  |
**403** | Forbidden - identity type not supported or missing username. |  -  |
**501** | Not yet implemented. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_views_delete_view**
> api_views_delete_view(view_id)

Delete an inventory view

Deletes an existing inventory view. Only the view creator can delete a view. System views cannot be deleted. <br /><br /> Required permissions: inventory:views:write <br /><br /> <b>NOTE:</b> This endpoint is not yet implemented and will return HTTP 501.

### Example

* Api Key Authentication (ApiKeyAuth):
```python
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost/api/inventory/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost/api/inventory/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost/api/inventory/v1",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.ViewsApi(api_client)
    view_id = 'view_id_example' # str | View ID.

    try:
        # Delete an inventory view
        api_instance.api_views_delete_view(view_id)
    except ApiException as e:
        print("Exception when calling ViewsApi->api_views_delete_view: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **view_id** | [**str**](.md)| View ID. |

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
**204** | Successfully deleted the inventory view. |  -  |
**403** | Forbidden - not the view owner or view is a system view. |  -  |
**404** | View not found or not visible to the requesting user. |  -  |
**501** | Not yet implemented. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_views_get_view_by_id**
> ViewOut api_views_get_view_by_id(view_id)

Get a single inventory view

Returns the full details and configuration for a single inventory view. The view must be visible to the requesting user. <br /><br /> Required permissions: inventory:views:read <br /><br /> <b>NOTE:</b> This endpoint is not yet implemented and will return HTTP 501.

### Example

* Api Key Authentication (ApiKeyAuth):
```python
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost/api/inventory/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost/api/inventory/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost/api/inventory/v1",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.ViewsApi(api_client)
    view_id = 'view_id_example' # str | View ID.

    try:
        # Get a single inventory view
        api_response = api_instance.api_views_get_view_by_id(view_id)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling ViewsApi->api_views_get_view_by_id: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **view_id** | [**str**](.md)| View ID. |

### Return type

[**ViewOut**](ViewOut.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully returned the inventory view. |  -  |
**403** | Forbidden - identity type not supported or missing username. |  -  |
**404** | View not found or not visible to the requesting user. |  -  |
**501** | Not yet implemented. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_views_get_views_list**
> ViewsListOut api_views_get_views_list(per_page=per_page, page=page)

Read the list of inventory views

Read the list of all inventory views visible to the requesting user. This includes system views, org-wide views, and private views owned by the requester. <br /><br /> Required permissions: inventory:views:read <br /><br /> <b>NOTE:</b> This endpoint is not yet implemented and will return HTTP 501.

### Example

* Api Key Authentication (ApiKeyAuth):
```python
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost/api/inventory/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost/api/inventory/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost/api/inventory/v1",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.ViewsApi(api_client)
    per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
page = 1 # int | A page number of the items to return. (optional) (default to 1)

    try:
        # Read the list of inventory views
        api_response = api_instance.api_views_get_views_list(per_page=per_page, page=page)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling ViewsApi->api_views_get_views_list: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]

### Return type

[**ViewsListOut**](ViewsListOut.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully read the views list. |  -  |
**403** | Forbidden - identity type not supported or missing username. |  -  |
**501** | Not yet implemented. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_views_update_view**
> ViewOut api_views_update_view(view_id, view_patch)

Update an inventory view

Updates an existing inventory view's name, description, configuration, or sharing settings. Only the view creator can update a view. System views cannot be updated. <br /><br /> Required permissions: inventory:views:write <br /><br /> <b>NOTE:</b> This endpoint is not yet implemented and will return HTTP 501.

### Example

* Api Key Authentication (ApiKeyAuth):
```python
from __future__ import print_function
import time
import iqe_host_inventory_api
from iqe_host_inventory_api.rest import ApiException
from pprint import pprint
# Defining the host is optional and defaults to http://localhost/api/inventory/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost/api/inventory/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: ApiKeyAuth
configuration = iqe_host_inventory_api.Configuration(
    host = "http://localhost/api/inventory/v1",
    api_key = {
        'x-rh-identity': 'YOUR_API_KEY'
    }
)
# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['x-rh-identity'] = 'Bearer'

# Enter a context with an instance of the API client
with iqe_host_inventory_api.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = iqe_host_inventory_api.ViewsApi(api_client)
    view_id = 'view_id_example' # str | View ID.
view_patch = iqe_host_inventory_api.ViewPatch() # ViewPatch | Data with which to update the inventory view.

    try:
        # Update an inventory view
        api_response = api_instance.api_views_update_view(view_id, view_patch)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling ViewsApi->api_views_update_view: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **view_id** | [**str**](.md)| View ID. |
 **view_patch** | [**ViewPatch**](ViewPatch.md)| Data with which to update the inventory view. |

### Return type

[**ViewOut**](ViewOut.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully updated the inventory view. |  -  |
**400** | Invalid request. |  -  |
**403** | Forbidden - not the view owner or view is a system view. |  -  |
**404** | View not found or not visible to the requesting user. |  -  |
**501** | Not yet implemented. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)
