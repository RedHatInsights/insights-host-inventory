# iqe_host_inventory_api.AccountsStalenessApi

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**api_staleness_create_staleness**](AccountsStalenessApi.md#api_staleness_create_staleness) | **POST** /account/staleness | Create account staleness record
[**api_staleness_delete_staleness**](AccountsStalenessApi.md#api_staleness_delete_staleness) | **DELETE** /account/staleness | Delete an account staleness
[**api_staleness_get_default_staleness**](AccountsStalenessApi.md#api_staleness_get_default_staleness) | **GET** /account/staleness/defaults | Read the entire list of account staleness
[**api_staleness_get_staleness**](AccountsStalenessApi.md#api_staleness_get_staleness) | **GET** /account/staleness | Read the entire list of account staleness
[**api_staleness_update_staleness**](AccountsStalenessApi.md#api_staleness_update_staleness) | **PATCH** /account/staleness | Update account staleness record


# **api_staleness_create_staleness**
> StalenessOutput api_staleness_create_staleness(staleness_in)

Create account staleness record

Create account staleness record. Required permissions: staleness:staleness:write

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
    api_instance = iqe_host_inventory_api.AccountsStalenessApi(api_client)
    staleness_in = iqe_host_inventory_api.StalenessIn() # StalenessIn | Data required to create a record for a account staleness.

    try:
        # Create account staleness record
        api_response = api_instance.api_staleness_create_staleness(staleness_in)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling AccountsStalenessApi->api_staleness_create_staleness: %s\n" % e)
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
    api_instance = iqe_host_inventory_api.AccountsStalenessApi(api_client)
    staleness_in = iqe_host_inventory_api.StalenessIn() # StalenessIn | Data required to create a record for a account staleness.

    try:
        # Create account staleness record
        api_response = api_instance.api_staleness_create_staleness(staleness_in)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling AccountsStalenessApi->api_staleness_create_staleness: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **staleness_in** | [**StalenessIn**](StalenessIn.md)| Data required to create a record for a account staleness. |

### Return type

[**StalenessOutput**](StalenessOutput.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth), [BearerAuth](../README.md#BearerAuth)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**201** | Successfully account staleness created. |  -  |
**400** | Invalid request. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_staleness_delete_staleness**
> api_staleness_delete_staleness()

Delete an account staleness

Delete an account staleness <br /><br /> Required permissions: staleness:staleness:write

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
    api_instance = iqe_host_inventory_api.AccountsStalenessApi(api_client)

    try:
        # Delete an account staleness
        api_instance.api_staleness_delete_staleness()
    except ApiException as e:
        print("Exception when calling AccountsStalenessApi->api_staleness_delete_staleness: %s\n" % e)
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
    api_instance = iqe_host_inventory_api.AccountsStalenessApi(api_client)

    try:
        # Delete an account staleness
        api_instance.api_staleness_delete_staleness()
    except ApiException as e:
        print("Exception when calling AccountsStalenessApi->api_staleness_delete_staleness: %s\n" % e)
```

### Parameters
This endpoint does not need any parameter.

### Return type

void (empty response body)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth), [BearerAuth](../README.md#BearerAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: Not defined

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**204** | Successfully deleted account staleness. |  -  |
**400** | Invalid request. |  -  |
**404** | Account Staleness not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_staleness_get_default_staleness**
> StalenessOutput api_staleness_get_default_staleness()

Read the entire list of account staleness

Read the entire list of all accounts staleness available. Required permissions: staleness:staleness:read

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
    api_instance = iqe_host_inventory_api.AccountsStalenessApi(api_client)

    try:
        # Read the entire list of account staleness
        api_response = api_instance.api_staleness_get_default_staleness()
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling AccountsStalenessApi->api_staleness_get_default_staleness: %s\n" % e)
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
    api_instance = iqe_host_inventory_api.AccountsStalenessApi(api_client)

    try:
        # Read the entire list of account staleness
        api_response = api_instance.api_staleness_get_default_staleness()
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling AccountsStalenessApi->api_staleness_get_default_staleness: %s\n" % e)
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**StalenessOutput**](StalenessOutput.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth), [BearerAuth](../README.md#BearerAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully read the staleness account. |  -  |
**400** | Invalid request. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_staleness_get_staleness**
> StalenessOutput api_staleness_get_staleness()

Read the entire list of account staleness

Read the entire list of all accounts staleness available. Required permissions: staleness:staleness:read

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
    api_instance = iqe_host_inventory_api.AccountsStalenessApi(api_client)

    try:
        # Read the entire list of account staleness
        api_response = api_instance.api_staleness_get_staleness()
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling AccountsStalenessApi->api_staleness_get_staleness: %s\n" % e)
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
    api_instance = iqe_host_inventory_api.AccountsStalenessApi(api_client)

    try:
        # Read the entire list of account staleness
        api_response = api_instance.api_staleness_get_staleness()
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling AccountsStalenessApi->api_staleness_get_staleness: %s\n" % e)
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**StalenessOutput**](StalenessOutput.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth), [BearerAuth](../README.md#BearerAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully read the staleness account. |  -  |
**400** | Invalid request. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_staleness_update_staleness**
> StalenessOutput api_staleness_update_staleness(staleness_in)

Update account staleness record

Update account staleness record. Required permissions: staleness:staleness:write

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
    api_instance = iqe_host_inventory_api.AccountsStalenessApi(api_client)
    staleness_in = iqe_host_inventory_api.StalenessIn() # StalenessIn | Data required to update a record for a account staleness.

    try:
        # Update account staleness record
        api_response = api_instance.api_staleness_update_staleness(staleness_in)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling AccountsStalenessApi->api_staleness_update_staleness: %s\n" % e)
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
    api_instance = iqe_host_inventory_api.AccountsStalenessApi(api_client)
    staleness_in = iqe_host_inventory_api.StalenessIn() # StalenessIn | Data required to update a record for a account staleness.

    try:
        # Update account staleness record
        api_response = api_instance.api_staleness_update_staleness(staleness_in)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling AccountsStalenessApi->api_staleness_update_staleness: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **staleness_in** | [**StalenessIn**](StalenessIn.md)| Data required to update a record for a account staleness. |

### Return type

[**StalenessOutput**](StalenessOutput.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth), [BearerAuth](../README.md#BearerAuth)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully account staleness updated. |  -  |
**400** | Invalid request. |  -  |
**404** | Staleness record not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)
