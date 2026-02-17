# iqe_host_inventory_api.HostsApi

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**api_host_delete_all_hosts**](HostsApi.md#api_host_delete_all_hosts) | **DELETE** /hosts/all | Delete all hosts on the account
[**api_host_delete_host_by_id**](HostsApi.md#api_host_delete_host_by_id) | **DELETE** /hosts/{host_id_list} | Delete hosts by IDs
[**api_host_delete_hosts_by_filter**](HostsApi.md#api_host_delete_hosts_by_filter) | **DELETE** /hosts | Delete the entire list of hosts filtered by the given parameters
[**api_host_get_host_by_id**](HostsApi.md#api_host_get_host_by_id) | **GET** /hosts/{host_id_list} | Find hosts by their IDs
[**api_host_get_host_exists**](HostsApi.md#api_host_get_host_exists) | **GET** /host_exists | Find one host by insights_id, if it exists
[**api_host_get_host_list**](HostsApi.md#api_host_get_host_list) | **GET** /hosts | Read the entire list of hosts
[**api_host_get_host_system_profile_by_id**](HostsApi.md#api_host_get_host_system_profile_by_id) | **GET** /hosts/{host_id_list}/system_profile | Return one or more hosts system profile
[**api_host_get_host_tag_count**](HostsApi.md#api_host_get_host_tag_count) | **GET** /hosts/{host_id_list}/tags/count | Get the number of tags on a host or hosts
[**api_host_get_host_tags**](HostsApi.md#api_host_get_host_tags) | **GET** /hosts/{host_id_list}/tags | Get the tags on a host
[**api_host_host_checkin**](HostsApi.md#api_host_host_checkin) | **POST** /hosts/checkin | Update staleness timestamps for a host matching the provided facts
[**api_host_merge_facts**](HostsApi.md#api_host_merge_facts) | **PATCH** /hosts/{host_id_list}/facts/{namespace} | Merge facts under a namespace
[**api_host_patch_host_by_id**](HostsApi.md#api_host_patch_host_by_id) | **PATCH** /hosts/{host_id_list} | Update hosts
[**api_host_replace_facts**](HostsApi.md#api_host_replace_facts) | **PUT** /hosts/{host_id_list}/facts/{namespace} | Replace facts under a namespace
[**api_host_views_get_host_views**](HostsApi.md#api_host_views_get_host_views) | **GET** /beta/hosts-view | Read aggregated host and application data


# **api_host_delete_all_hosts**
> api_host_delete_all_hosts(confirm_delete_all=confirm_delete_all)

Delete all hosts on the account

Delete all hosts on the account.  The request must include \"confirm_delete_all=true\". <br /><br /> Required permissions: inventory:hosts:write

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
    api_instance = iqe_host_inventory_api.HostsApi(api_client)
    confirm_delete_all = True # bool | Confirmation to delete all hosts on the account (optional)

    try:
        # Delete all hosts on the account
        api_instance.api_host_delete_all_hosts(confirm_delete_all=confirm_delete_all)
    except ApiException as e:
        print("Exception when calling HostsApi->api_host_delete_all_hosts: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **confirm_delete_all** | **bool**| Confirmation to delete all hosts on the account | [optional]

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
**202** | Request for deleting all hosts has been accepted. |  -  |
**400** | Invalid request. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_delete_host_by_id**
> object api_host_delete_host_by_id(host_id_list, branch_id=branch_id)

Delete hosts by IDs

Delete hosts by IDs <br /><br /> Required permissions: inventory:hosts:write

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
    api_instance = iqe_host_inventory_api.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # list[str] | A comma-separated list of host IDs.
branch_id = 'branch_id_example' # str | Filter by branch_id (optional)

    try:
        # Delete hosts by IDs
        api_response = api_instance.api_host_delete_host_by_id(host_id_list, branch_id=branch_id)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling HostsApi->api_host_delete_host_by_id: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**list[str]**](str.md)| A comma-separated list of host IDs. |
 **branch_id** | **str**| Filter by branch_id | [optional]

### Return type

**object**

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully deleted hosts. |  -  |
**400** | Invalid request. |  -  |
**404** | One or more requested resources were not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_delete_hosts_by_filter**
> api_host_delete_hosts_by_filter(display_name=display_name, fqdn=fqdn, hostname_or_id=hostname_or_id, insights_id=insights_id, provider_id=provider_id, provider_type=provider_type, updated_start=updated_start, updated_end=updated_end, last_check_in_start=last_check_in_start, last_check_in_end=last_check_in_end, group_name=group_name, group_id=group_id, registered_with=registered_with, system_type=system_type, staleness=staleness, tags=tags, filter=filter, subscription_manager_id=subscription_manager_id)

Delete the entire list of hosts filtered by the given parameters

Delete the entire list of hosts filtered by the given parameters. <br /><br /> Required permissions: inventory:hosts:write

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
    api_instance = iqe_host_inventory_api.HostsApi(api_client)
    display_name = 'display_name_example' # str | Filter by display_name (case-insensitive) (optional)
fqdn = 'fqdn_example' # str | Filter by FQDN (case-insensitive) (optional)
hostname_or_id = 'hostname_or_id_example' # str | Filter by display_name, fqdn, id (case-insensitive) (optional)
insights_id = 'insights_id_example' # str | Filter by insights_id (optional)
provider_id = 'provider_id_example' # str | Filter by provider_id (optional)
provider_type = 'provider_type_example' # str | Filter by provider_type (optional)
updated_start = '2013-10-20T19:20:30+01:00' # datetime | Only show hosts last modified after the given date (optional)
updated_end = '2013-10-20T19:20:30+01:00' # datetime | Only show hosts last modified before the given date (optional)
last_check_in_start = '2013-10-20T19:20:30+01:00' # datetime | Only show hosts last checked in after the given date (optional)
last_check_in_end = '2013-10-20T19:20:30+01:00' # datetime | Only show hosts last checked in before the given date (optional)
group_name = ['group_name_example'] # list[str] | Filter by group name (optional)
group_id = ['group_id_example'] # list[str] | Filter by group ID (UUID format) (optional)
registered_with = ['registered_with_example'] # list[str] | Filters out any host not registered by the specified reporters (optional)
system_type = ['system_type_example'] # list[str] | Filters systems by type (optional)
staleness = ['staleness_example'] # list[str] | Culling states of the hosts. (optional)
tags = ['tags_example'] # list[str] | Filters systems by tag(s). Specify multiple tags as a comma-separated list (e.g. insights-client/security=strict,env/type=prod). (optional)
filter = {'key': {}} # dict(str, object) | Filters hosts based on system_profile fields. For example: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"workloads\": {\"sap\": {\"sap_system\": {\"eq\": \"true\"}}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][sap_system][eq]=true\" <br /><br /> To get \"edge\" hosts, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"host_type\": {\"eq\": \"edge\"}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][host_type][eq]=edge\" <br /><br /> To get hosts with an specific operating system, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"operating_system\": {\"name\": {\"eq\": \"rhel\"}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][name][eq]=rhel\" (optional)
subscription_manager_id = 'subscription_manager_id_example' # str | Filter by subscription_manager_id (optional)

    try:
        # Delete the entire list of hosts filtered by the given parameters
        api_instance.api_host_delete_hosts_by_filter(display_name=display_name, fqdn=fqdn, hostname_or_id=hostname_or_id, insights_id=insights_id, provider_id=provider_id, provider_type=provider_type, updated_start=updated_start, updated_end=updated_end, last_check_in_start=last_check_in_start, last_check_in_end=last_check_in_end, group_name=group_name, group_id=group_id, registered_with=registered_with, system_type=system_type, staleness=staleness, tags=tags, filter=filter, subscription_manager_id=subscription_manager_id)
    except ApiException as e:
        print("Exception when calling HostsApi->api_host_delete_hosts_by_filter: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **display_name** | **str**| Filter by display_name (case-insensitive) | [optional]
 **fqdn** | **str**| Filter by FQDN (case-insensitive) | [optional]
 **hostname_or_id** | **str**| Filter by display_name, fqdn, id (case-insensitive) | [optional]
 **insights_id** | [**str**](.md)| Filter by insights_id | [optional]
 **provider_id** | **str**| Filter by provider_id | [optional]
 **provider_type** | **str**| Filter by provider_type | [optional]
 **updated_start** | **datetime**| Only show hosts last modified after the given date | [optional]
 **updated_end** | **datetime**| Only show hosts last modified before the given date | [optional]
 **last_check_in_start** | **datetime**| Only show hosts last checked in after the given date | [optional]
 **last_check_in_end** | **datetime**| Only show hosts last checked in before the given date | [optional]
 **group_name** | [**list[str]**](str.md)| Filter by group name | [optional]
 **group_id** | [**list[str]**](str.md)| Filter by group ID (UUID format) | [optional]
 **registered_with** | [**list[str]**](str.md)| Filters out any host not registered by the specified reporters | [optional]
 **system_type** | [**list[str]**](str.md)| Filters systems by type | [optional]
 **staleness** | [**list[str]**](str.md)| Culling states of the hosts. | [optional]
 **tags** | [**list[str]**](str.md)| Filters systems by tag(s). Specify multiple tags as a comma-separated list (e.g. insights-client/security&#x3D;strict,env/type&#x3D;prod). | [optional]
 **filter** | [**dict(str, object)**](object.md)| Filters hosts based on system_profile fields. For example: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;workloads\&quot;: {\&quot;sap\&quot;: {\&quot;sap_system\&quot;: {\&quot;eq\&quot;: \&quot;true\&quot;}}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][sap_system][eq]&#x3D;true\&quot; &lt;br /&gt;&lt;br /&gt; To get \&quot;edge\&quot; hosts, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;host_type\&quot;: {\&quot;eq\&quot;: \&quot;edge\&quot;}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][host_type][eq]&#x3D;edge\&quot; &lt;br /&gt;&lt;br /&gt; To get hosts with an specific operating system, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;operating_system\&quot;: {\&quot;name\&quot;: {\&quot;eq\&quot;: \&quot;rhel\&quot;}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][name][eq]&#x3D;rhel\&quot; | [optional]
 **subscription_manager_id** | [**str**](.md)| Filter by subscription_manager_id | [optional]

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
**202** | Request for deletion of filtered hosts has been accepted. |  -  |
**400** | Invalid request. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_get_host_by_id**
> HostQueryOutput api_host_get_host_by_id(host_id_list, branch_id=branch_id, per_page=per_page, page=page, order_by=order_by, order_how=order_how, fields=fields)

Find hosts by their IDs

Find one or more hosts by their ID. <br /><br /> Required permissions: inventory:hosts:read

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
    api_instance = iqe_host_inventory_api.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # list[str] | A comma-separated list of host IDs.
branch_id = 'branch_id_example' # str | Filter by branch_id (optional)
per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
page = 1 # int | A page number of the items to return. (optional) (default to 1)
order_by = 'order_by_example' # str | Ordering field name (optional)
order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system (optional)
fields = {'key': {}} # dict(str, object) | Fetches only mentioned system_profile fields. For example, <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": [\"arch\", \"host_type\"]} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?fields[system_profile]=arch,host_type\" (optional)

    try:
        # Find hosts by their IDs
        api_response = api_instance.api_host_get_host_by_id(host_id_list, branch_id=branch_id, per_page=per_page, page=page, order_by=order_by, order_how=order_how, fields=fields)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling HostsApi->api_host_get_host_by_id: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**list[str]**](str.md)| A comma-separated list of host IDs. |
 **branch_id** | **str**| Filter by branch_id | [optional]
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **order_by** | **str**| Ordering field name | [optional]
 **order_how** | **str**| Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system | [optional]
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
**200** | Successfully searched for hosts. |  -  |
**400** | Invalid request. |  -  |
**404** | One or more requested resources were not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_get_host_exists**
> HostIdOut api_host_get_host_exists(insights_id=insights_id)

Find one host by insights_id, if it exists

Find one host by insights_id, if it exists. <br /><br /> Required permissions: inventory:hosts:read

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
    api_instance = iqe_host_inventory_api.HostsApi(api_client)
    insights_id = 'insights_id_example' # str | Filter by insights_id (optional)

    try:
        # Find one host by insights_id, if it exists
        api_response = api_instance.api_host_get_host_exists(insights_id=insights_id)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling HostsApi->api_host_get_host_exists: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **insights_id** | [**str**](.md)| Filter by insights_id | [optional]

### Return type

[**HostIdOut**](HostIdOut.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Found a matching host. |  -  |
**400** | Invalid request. |  -  |
**404** | Host not found. |  -  |
**409** | Multiple matching hosts detected. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_get_host_list**
> HostQueryOutput api_host_get_host_list(display_name=display_name, fqdn=fqdn, hostname_or_id=hostname_or_id, insights_id=insights_id, subscription_manager_id=subscription_manager_id, provider_id=provider_id, provider_type=provider_type, updated_start=updated_start, updated_end=updated_end, last_check_in_start=last_check_in_start, last_check_in_end=last_check_in_end, group_name=group_name, group_id=group_id, branch_id=branch_id, per_page=per_page, page=page, order_by=order_by, order_how=order_how, staleness=staleness, tags=tags, registered_with=registered_with, system_type=system_type, filter=filter, fields=fields)

Read the entire list of hosts

Read the entire list of all hosts available to the account. <br /><br /> Required permissions: inventory:hosts:read

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
    api_instance = iqe_host_inventory_api.HostsApi(api_client)
    display_name = 'display_name_example' # str | Filter by display_name (case-insensitive) (optional)
fqdn = 'fqdn_example' # str | Filter by FQDN (case-insensitive) (optional)
hostname_or_id = 'hostname_or_id_example' # str | Filter by display_name, fqdn, id (case-insensitive) (optional)
insights_id = 'insights_id_example' # str | Filter by insights_id (optional)
subscription_manager_id = 'subscription_manager_id_example' # str | Filter by subscription_manager_id (optional)
provider_id = 'provider_id_example' # str | Filter by provider_id (optional)
provider_type = 'provider_type_example' # str | Filter by provider_type (optional)
updated_start = '2013-10-20T19:20:30+01:00' # datetime | Only show hosts last modified after the given date (optional)
updated_end = '2013-10-20T19:20:30+01:00' # datetime | Only show hosts last modified before the given date (optional)
last_check_in_start = '2013-10-20T19:20:30+01:00' # datetime | Only show hosts last checked in after the given date (optional)
last_check_in_end = '2013-10-20T19:20:30+01:00' # datetime | Only show hosts last checked in before the given date (optional)
group_name = ['group_name_example'] # list[str] | Filter by group name (optional)
group_id = ['group_id_example'] # list[str] | Filter by group ID (UUID format) (optional)
branch_id = 'branch_id_example' # str | Filter by branch_id (optional)
per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
page = 1 # int | A page number of the items to return. (optional) (default to 1)
order_by = 'order_by_example' # str | Ordering field name (optional)
order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system (optional)
staleness = ["fresh","stale","stale_warning"] # list[str] | Culling states of the hosts. Default: fresh, stale and stale_warning (optional) (default to ["fresh","stale","stale_warning"])
tags = ['tags_example'] # list[str] | Filters systems by tag(s). Specify multiple tags as a comma-separated list (e.g. insights-client/security=strict,env/type=prod). (optional)
registered_with = ['registered_with_example'] # list[str] | Filters out any host not registered by the specified reporters (optional)
system_type = ['system_type_example'] # list[str] | Filters systems by type (optional)
filter = {'key': {}} # dict(str, object) | Filters hosts based on system_profile fields. For example: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"workloads\": {\"sap\": {\"sap_system\": {\"eq\": \"true\"}}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][sap_system][eq]=true\" <br /><br /> To get \"edge\" hosts, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"host_type\": {\"eq\": \"edge\"}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][host_type][eq]=edge\" <br /><br /> To get hosts with an specific operating system, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"operating_system\": {\"name\": {\"eq\": \"rhel\"}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][name][eq]=rhel\" (optional)
fields = {'key': {}} # dict(str, object) | Fetches only mentioned system_profile fields. For example, <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": [\"arch\", \"host_type\"]} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?fields[system_profile]=arch,host_type\" (optional)

    try:
        # Read the entire list of hosts
        api_response = api_instance.api_host_get_host_list(display_name=display_name, fqdn=fqdn, hostname_or_id=hostname_or_id, insights_id=insights_id, subscription_manager_id=subscription_manager_id, provider_id=provider_id, provider_type=provider_type, updated_start=updated_start, updated_end=updated_end, last_check_in_start=last_check_in_start, last_check_in_end=last_check_in_end, group_name=group_name, group_id=group_id, branch_id=branch_id, per_page=per_page, page=page, order_by=order_by, order_how=order_how, staleness=staleness, tags=tags, registered_with=registered_with, system_type=system_type, filter=filter, fields=fields)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling HostsApi->api_host_get_host_list: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **display_name** | **str**| Filter by display_name (case-insensitive) | [optional]
 **fqdn** | **str**| Filter by FQDN (case-insensitive) | [optional]
 **hostname_or_id** | **str**| Filter by display_name, fqdn, id (case-insensitive) | [optional]
 **insights_id** | [**str**](.md)| Filter by insights_id | [optional]
 **subscription_manager_id** | [**str**](.md)| Filter by subscription_manager_id | [optional]
 **provider_id** | **str**| Filter by provider_id | [optional]
 **provider_type** | **str**| Filter by provider_type | [optional]
 **updated_start** | **datetime**| Only show hosts last modified after the given date | [optional]
 **updated_end** | **datetime**| Only show hosts last modified before the given date | [optional]
 **last_check_in_start** | **datetime**| Only show hosts last checked in after the given date | [optional]
 **last_check_in_end** | **datetime**| Only show hosts last checked in before the given date | [optional]
 **group_name** | [**list[str]**](str.md)| Filter by group name | [optional]
 **group_id** | [**list[str]**](str.md)| Filter by group ID (UUID format) | [optional]
 **branch_id** | **str**| Filter by branch_id | [optional]
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **order_by** | **str**| Ordering field name | [optional]
 **order_how** | **str**| Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system | [optional]
 **staleness** | [**list[str]**](str.md)| Culling states of the hosts. Default: fresh, stale and stale_warning | [optional] [default to [&quot;fresh&quot;,&quot;stale&quot;,&quot;stale_warning&quot;]]
 **tags** | [**list[str]**](str.md)| Filters systems by tag(s). Specify multiple tags as a comma-separated list (e.g. insights-client/security&#x3D;strict,env/type&#x3D;prod). | [optional]
 **registered_with** | [**list[str]**](str.md)| Filters out any host not registered by the specified reporters | [optional]
 **system_type** | [**list[str]**](str.md)| Filters systems by type | [optional]
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
**200** | Successfully read the hosts list. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_get_host_system_profile_by_id**
> SystemProfileByHostOut api_host_get_host_system_profile_by_id(host_id_list, per_page=per_page, page=page, order_by=order_by, order_how=order_how, branch_id=branch_id, fields=fields)

Return one or more hosts system profile

Find one or more hosts by their ID and return the id and system profile <br /><br /> Required permissions: inventory:hosts:read

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
    api_instance = iqe_host_inventory_api.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # list[str] | A comma-separated list of host IDs.
per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
page = 1 # int | A page number of the items to return. (optional) (default to 1)
order_by = 'order_by_example' # str | Ordering field name (optional)
order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system (optional)
branch_id = 'branch_id_example' # str | Filter by branch_id (optional)
fields = {'key': {}} # dict(str, object) | Fetches only mentioned system_profile fields. For example, <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": [\"arch\", \"host_type\"]} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?fields[system_profile]=arch,host_type\" (optional)

    try:
        # Return one or more hosts system profile
        api_response = api_instance.api_host_get_host_system_profile_by_id(host_id_list, per_page=per_page, page=page, order_by=order_by, order_how=order_how, branch_id=branch_id, fields=fields)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling HostsApi->api_host_get_host_system_profile_by_id: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**list[str]**](str.md)| A comma-separated list of host IDs. |
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **order_by** | **str**| Ordering field name | [optional]
 **order_how** | **str**| Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system | [optional]
 **branch_id** | **str**| Filter by branch_id | [optional]
 **fields** | [**dict(str, object)**](object.md)| Fetches only mentioned system_profile fields. For example, &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: [\&quot;arch\&quot;, \&quot;host_type\&quot;]} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?fields[system_profile]&#x3D;arch,host_type\&quot; | [optional]

### Return type

[**SystemProfileByHostOut**](SystemProfileByHostOut.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully searched for hosts. |  -  |
**400** | Invalid request. |  -  |
**404** | One or more requested resources were not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_get_host_tag_count**
> TagCountOut api_host_get_host_tag_count(host_id_list, per_page=per_page, page=page, order_by=order_by, order_how=order_how)

Get the number of tags on a host or hosts

Get the number of tags on a host or hosts <br /><br /> Required permissions: inventory:hosts:read

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
    api_instance = iqe_host_inventory_api.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # list[str] | A comma-separated list of host IDs.
per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
page = 1 # int | A page number of the items to return. (optional) (default to 1)
order_by = 'order_by_example' # str | Ordering field name (optional)
order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system (optional)

    try:
        # Get the number of tags on a host or hosts
        api_response = api_instance.api_host_get_host_tag_count(host_id_list, per_page=per_page, page=page, order_by=order_by, order_how=order_how)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling HostsApi->api_host_get_host_tag_count: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**list[str]**](str.md)| A comma-separated list of host IDs. |
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **order_by** | **str**| Ordering field name | [optional]
 **order_how** | **str**| Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system | [optional]

### Return type

[**TagCountOut**](TagCountOut.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully found tag count. |  -  |
**400** | Invalid request. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_get_host_tags**
> TagsOut api_host_get_host_tags(host_id_list, per_page=per_page, page=page, order_by=order_by, order_how=order_how, search=search)

Get the tags on a host

Get the tags on a host <br /><br /> Required permissions: inventory:hosts:read

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
    api_instance = iqe_host_inventory_api.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # list[str] | A comma-separated list of host IDs.
per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
page = 1 # int | A page number of the items to return. (optional) (default to 1)
order_by = 'order_by_example' # str | Ordering field name (optional)
order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system (optional)
search = 'search_example' # str | Used for searching tags and sap_sids that match the given search string. For searching tags, a tag's namespace, key, and/or value is used for matching. (optional)

    try:
        # Get the tags on a host
        api_response = api_instance.api_host_get_host_tags(host_id_list, per_page=per_page, page=page, order_by=order_by, order_how=order_how, search=search)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling HostsApi->api_host_get_host_tags: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**list[str]**](str.md)| A comma-separated list of host IDs. |
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **order_by** | **str**| Ordering field name | [optional]
 **order_how** | **str**| Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system | [optional]
 **search** | **str**| Used for searching tags and sap_sids that match the given search string. For searching tags, a tag&#39;s namespace, key, and/or value is used for matching. | [optional]

### Return type

[**TagsOut**](TagsOut.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully found tags. |  -  |
**400** | Invalid request. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_host_checkin**
> HostOut api_host_host_checkin(create_check_in)

Update staleness timestamps for a host matching the provided facts

Finds a host and updates its staleness timestamps. It uses the supplied canonical facts to determine which host to update. By default, the staleness timestamp is set to 1 hour from when the request is received; however, this can be overridden by supplying the interval. <br /><br /> Required permissions: inventory:hosts:write

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
    api_instance = iqe_host_inventory_api.HostsApi(api_client)
    create_check_in = iqe_host_inventory_api.CreateCheckIn() # CreateCheckIn | Data required to create a check-in record for a host.

    try:
        # Update staleness timestamps for a host matching the provided facts
        api_response = api_instance.api_host_host_checkin(create_check_in)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling HostsApi->api_host_host_checkin: %s\n" % e)
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
    api_instance = iqe_host_inventory_api.HostsApi(api_client)
    create_check_in = iqe_host_inventory_api.CreateCheckIn() # CreateCheckIn | Data required to create a check-in record for a host.

    try:
        # Update staleness timestamps for a host matching the provided facts
        api_response = api_instance.api_host_host_checkin(create_check_in)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling HostsApi->api_host_host_checkin: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **create_check_in** | [**CreateCheckIn**](CreateCheckIn.md)| Data required to create a check-in record for a host. |

### Return type

[**HostOut**](HostOut.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth), [BearerAuth](../README.md#BearerAuth)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**201** | Successfully checked in Host. |  -  |
**404** | Not Found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_merge_facts**
> api_host_merge_facts(host_id_list, namespace, body, branch_id=branch_id)

Merge facts under a namespace

Merge one or multiple hosts facts under a namespace. <br /><br /> Required permissions: inventory:hosts:write

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
    api_instance = iqe_host_inventory_api.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # list[str] | A comma-separated list of host IDs.
namespace = 'namespace_example' # str | A namespace of the merged facts.
body = None # object | A dictionary with the new facts to merge with the original ones.
branch_id = 'branch_id_example' # str | Filter by branch_id (optional)

    try:
        # Merge facts under a namespace
        api_instance.api_host_merge_facts(host_id_list, namespace, body, branch_id=branch_id)
    except ApiException as e:
        print("Exception when calling HostsApi->api_host_merge_facts: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**list[str]**](str.md)| A comma-separated list of host IDs. |
 **namespace** | **str**| A namespace of the merged facts. |
 **body** | **object**| A dictionary with the new facts to merge with the original ones. |
 **branch_id** | **str**| Filter by branch_id | [optional]

### Return type

void (empty response body)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: Not defined

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully merged facts. |  -  |
**400** | Invalid request. |  -  |
**404** | Host or namespace not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_patch_host_by_id**
> object api_host_patch_host_by_id(host_id_list, patch_host_in, branch_id=branch_id)

Update hosts

Update hosts <br /><br /> Required permissions: inventory:hosts:write

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
    api_instance = iqe_host_inventory_api.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # list[str] | A comma-separated list of host IDs.
patch_host_in = iqe_host_inventory_api.PatchHostIn() # PatchHostIn | A group of fields to be updated on the hosts
branch_id = 'branch_id_example' # str | Filter by branch_id (optional)

    try:
        # Update hosts
        api_response = api_instance.api_host_patch_host_by_id(host_id_list, patch_host_in, branch_id=branch_id)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling HostsApi->api_host_patch_host_by_id: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**list[str]**](str.md)| A comma-separated list of host IDs. |
 **patch_host_in** | [**PatchHostIn**](PatchHostIn.md)| A group of fields to be updated on the hosts |
 **branch_id** | **str**| Filter by branch_id | [optional]

### Return type

**object**

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully updated the hosts. |  -  |
**400** | Invalid request. |  -  |
**404** | One or more requested resources were not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_replace_facts**
> api_host_replace_facts(host_id_list, namespace, body, branch_id=branch_id)

Replace facts under a namespace

Replace facts under a namespace <br /><br /> Required permissions: inventory:hosts:write

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
    api_instance = iqe_host_inventory_api.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # list[str] | A comma-separated list of host IDs.
namespace = 'namespace_example' # str | A namespace of the merged facts.
body = None # object | A dictionary with the new facts to replace the original ones.
branch_id = 'branch_id_example' # str | Filter by branch_id (optional)

    try:
        # Replace facts under a namespace
        api_instance.api_host_replace_facts(host_id_list, namespace, body, branch_id=branch_id)
    except ApiException as e:
        print("Exception when calling HostsApi->api_host_replace_facts: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**list[str]**](str.md)| A comma-separated list of host IDs. |
 **namespace** | **str**| A namespace of the merged facts. |
 **body** | **object**| A dictionary with the new facts to replace the original ones. |
 **branch_id** | **str**| Filter by branch_id | [optional]

### Return type

void (empty response body)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: Not defined

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully replaced facts. |  -  |
**400** | Invalid request. |  -  |
**404** | Host or namespace not found. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_host_views_get_host_views**
> HostViewQueryOutput api_host_views_get_host_views(display_name=display_name, fqdn=fqdn, hostname_or_id=hostname_or_id, insights_id=insights_id, subscription_manager_id=subscription_manager_id, provider_id=provider_id, provider_type=provider_type, updated_start=updated_start, updated_end=updated_end, last_check_in_start=last_check_in_start, last_check_in_end=last_check_in_end, group_name=group_name, branch_id=branch_id, per_page=per_page, page=page, order_by=order_by, order_how=order_how, staleness=staleness, tags=tags, registered_with=registered_with, system_type=system_type, filter=filter, fields=fields)

Read aggregated host and application data

Read a combined view of hosts with optional application data such as Advisor, Vulnerability, Compliance, Patch, and others. Application joins are opt-in and controlled through the fields parameter.<br /><br /> Required permissions: inventory:hosts:read

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
    api_instance = iqe_host_inventory_api.HostsApi(api_client)
    display_name = 'display_name_example' # str | Filter by display_name (case-insensitive) (optional)
fqdn = 'fqdn_example' # str | Filter by FQDN (case-insensitive) (optional)
hostname_or_id = 'hostname_or_id_example' # str | Filter by display_name, fqdn, id (case-insensitive) (optional)
insights_id = 'insights_id_example' # str | Filter by insights_id (optional)
subscription_manager_id = 'subscription_manager_id_example' # str | Filter by subscription_manager_id (optional)
provider_id = 'provider_id_example' # str | Filter by provider_id (optional)
provider_type = 'provider_type_example' # str | Filter by provider_type (optional)
updated_start = '2013-10-20T19:20:30+01:00' # datetime | Only show hosts last modified after the given date (optional)
updated_end = '2013-10-20T19:20:30+01:00' # datetime | Only show hosts last modified before the given date (optional)
last_check_in_start = '2013-10-20T19:20:30+01:00' # datetime | Only show hosts last checked in after the given date (optional)
last_check_in_end = '2013-10-20T19:20:30+01:00' # datetime | Only show hosts last checked in before the given date (optional)
group_name = ['group_name_example'] # list[str] | Filter by group name (optional)
branch_id = 'branch_id_example' # str | Filter by branch_id (optional)
per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
page = 1 # int | A page number of the items to return. (optional) (default to 1)
order_by = 'order_by_example' # str | Ordering field for host views. Accepts standard host columns or application metrics using `app:field` format. Use together with `order_how`. **Host fields:** `display_name`, `group_name`, `updated`, `operating_system`, `last_check_in` **App fields:** See `AppSortableFields` schema for the full list of available application sort fields (e.g. `vulnerability:critical_cves`, `advisor:recommendations`). (optional)
order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system (optional)
staleness = ["fresh","stale","stale_warning"] # list[str] | Culling states of the hosts. Default: fresh, stale and stale_warning (optional) (default to ["fresh","stale","stale_warning"])
tags = ['tags_example'] # list[str] | Filters systems by tag(s). Specify multiple tags as a comma-separated list (e.g. insights-client/security=strict,env/type=prod). (optional)
registered_with = ['registered_with_example'] # list[str] | Filters out any host not registered by the specified reporters (optional)
system_type = ['system_type_example'] # list[str] | Filters systems by type (optional)
filter = {'key': iqe_host_inventory_api.dict(str, HostViewFilterComparison)()} # dict(str, dict) | Filters on aggregated application data using the syntax `filter[app_name][field_name][operator]=value`. Supported operators are `eq`, `ne`, `gte`, and `lte`. For example: `filter[vulnerability][critical_cves][gte]=1` or `filter[patch][template][eq]=production`. (optional)
fields = {'key': iqe_host_inventory_api.dict(str, bool)()} # dict(str, dict(str, bool)) | Selects which application objects (or sub-fields) should be joined into the host view response. Use `fields[advisor]=recommendations` to request specific fields, or `fields[advisor]=recommendations&fields[vulnerability]=critical_cves` for multiple apps. When this parameter is omitted, all fields from all applications are returned by default (per JSON:API sparse fieldsets specification). (optional)

    try:
        # Read aggregated host and application data
        api_response = api_instance.api_host_views_get_host_views(display_name=display_name, fqdn=fqdn, hostname_or_id=hostname_or_id, insights_id=insights_id, subscription_manager_id=subscription_manager_id, provider_id=provider_id, provider_type=provider_type, updated_start=updated_start, updated_end=updated_end, last_check_in_start=last_check_in_start, last_check_in_end=last_check_in_end, group_name=group_name, branch_id=branch_id, per_page=per_page, page=page, order_by=order_by, order_how=order_how, staleness=staleness, tags=tags, registered_with=registered_with, system_type=system_type, filter=filter, fields=fields)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling HostsApi->api_host_views_get_host_views: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **display_name** | **str**| Filter by display_name (case-insensitive) | [optional]
 **fqdn** | **str**| Filter by FQDN (case-insensitive) | [optional]
 **hostname_or_id** | **str**| Filter by display_name, fqdn, id (case-insensitive) | [optional]
 **insights_id** | [**str**](.md)| Filter by insights_id | [optional]
 **subscription_manager_id** | [**str**](.md)| Filter by subscription_manager_id | [optional]
 **provider_id** | **str**| Filter by provider_id | [optional]
 **provider_type** | **str**| Filter by provider_type | [optional]
 **updated_start** | **datetime**| Only show hosts last modified after the given date | [optional]
 **updated_end** | **datetime**| Only show hosts last modified before the given date | [optional]
 **last_check_in_start** | **datetime**| Only show hosts last checked in after the given date | [optional]
 **last_check_in_end** | **datetime**| Only show hosts last checked in before the given date | [optional]
 **group_name** | [**list[str]**](str.md)| Filter by group name | [optional]
 **branch_id** | **str**| Filter by branch_id | [optional]
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **order_by** | **str**| Ordering field for host views. Accepts standard host columns or application metrics using &#x60;app:field&#x60; format. Use together with &#x60;order_how&#x60;. **Host fields:** &#x60;display_name&#x60;, &#x60;group_name&#x60;, &#x60;updated&#x60;, &#x60;operating_system&#x60;, &#x60;last_check_in&#x60; **App fields:** See &#x60;AppSortableFields&#x60; schema for the full list of available application sort fields (e.g. &#x60;vulnerability:critical_cves&#x60;, &#x60;advisor:recommendations&#x60;). | [optional]
 **order_how** | **str**| Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system | [optional]
 **staleness** | [**list[str]**](str.md)| Culling states of the hosts. Default: fresh, stale and stale_warning | [optional] [default to [&quot;fresh&quot;,&quot;stale&quot;,&quot;stale_warning&quot;]]
 **tags** | [**list[str]**](str.md)| Filters systems by tag(s). Specify multiple tags as a comma-separated list (e.g. insights-client/security&#x3D;strict,env/type&#x3D;prod). | [optional]
 **registered_with** | [**list[str]**](str.md)| Filters out any host not registered by the specified reporters | [optional]
 **system_type** | [**list[str]**](str.md)| Filters systems by type | [optional]
 **filter** | [**dict(str, dict)**](dict(str, HostViewFilterComparison).md)| Filters on aggregated application data using the syntax &#x60;filter[app_name][field_name][operator]&#x3D;value&#x60;. Supported operators are &#x60;eq&#x60;, &#x60;ne&#x60;, &#x60;gte&#x60;, and &#x60;lte&#x60;. For example: &#x60;filter[vulnerability][critical_cves][gte]&#x3D;1&#x60; or &#x60;filter[patch][template][eq]&#x3D;production&#x60;. | [optional]
 **fields** | [**dict(str, dict(str, bool))**](dict(str, bool).md)| Selects which application objects (or sub-fields) should be joined into the host view response. Use &#x60;fields[advisor]&#x3D;recommendations&#x60; to request specific fields, or &#x60;fields[advisor]&#x3D;recommendations&amp;fields[vulnerability]&#x3D;critical_cves&#x60; for multiple apps. When this parameter is omitted, all fields from all applications are returned by default (per JSON:API sparse fieldsets specification). | [optional]

### Return type

[**HostViewQueryOutput**](HostViewQueryOutput.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Successfully read host views. |  -  |
**400** | Invalid request. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)
