# iqe_host_inventory_api_v7.HostsApi

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


# **api_host_delete_all_hosts**
> api_host_delete_all_hosts(confirm_delete_all=confirm_delete_all)

Delete all hosts on the account

Delete all hosts on the account.  The request must include \"confirm_delete_all=true\". <br /><br /> Required permissions: inventory:hosts:write

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
    api_instance = iqe_host_inventory_api_v7.HostsApi(api_client)
    confirm_delete_all = True # bool | Confirmation to delete all hosts on the account (optional)

    try:
        # Delete all hosts on the account
        api_instance.api_host_delete_all_hosts(confirm_delete_all=confirm_delete_all)
    except Exception as e:
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
    api_instance = iqe_host_inventory_api_v7.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # List[str] | A comma-separated list of host IDs.
    branch_id = 'branch_id_example' # str | Filter by branch_id (optional)

    try:
        # Delete hosts by IDs
        api_response = api_instance.api_host_delete_host_by_id(host_id_list, branch_id=branch_id)
        print("The response of HostsApi->api_host_delete_host_by_id:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling HostsApi->api_host_delete_host_by_id: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**List[str]**](str.md)| A comma-separated list of host IDs. |
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
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.system_profile_nested_object_value import SystemProfileNestedObjectValue
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
    api_instance = iqe_host_inventory_api_v7.HostsApi(api_client)
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
    group_name = ['group_name_example'] # List[str] | Filter by group name (optional)
    group_id = ['group_id_example'] # List[str] | Filter by group ID (UUID format) (optional)
    registered_with = ['registered_with_example'] # List[str] | Filters out any host not registered by the specified reporters (optional)
    system_type = ['system_type_example'] # List[str] | Filters systems by type (optional)
    staleness = ['staleness_example'] # List[str] | Culling states of the hosts. (optional)
    tags = ['tags_example'] # List[str] | filters out hosts not tagged by the given tags (optional)
    filter = {'key': iqe_host_inventory_api_v7.SystemProfileNestedObjectValue()} # Dict[str, SystemProfileNestedObjectValue] | Filters hosts based on system_profile fields. For example: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"workloads\": {\"sap\": {\"sap_system\": {\"eq\": \"true\"}}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][sap_system][eq]=true\" <br /><br /> To get \"edge\" hosts, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"host_type\": {\"eq\": \"edge\"}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][host_type][eq]=edge\" <br /><br /> To get hosts with an specific operating system, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"operating_system\": {\"name\": {\"eq\": \"rhel\"}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][name][eq]=rhel\" (optional)
    subscription_manager_id = 'subscription_manager_id_example' # str | Filter by subscription_manager_id (optional)

    try:
        # Delete the entire list of hosts filtered by the given parameters
        api_instance.api_host_delete_hosts_by_filter(display_name=display_name, fqdn=fqdn, hostname_or_id=hostname_or_id, insights_id=insights_id, provider_id=provider_id, provider_type=provider_type, updated_start=updated_start, updated_end=updated_end, last_check_in_start=last_check_in_start, last_check_in_end=last_check_in_end, group_name=group_name, group_id=group_id, registered_with=registered_with, system_type=system_type, staleness=staleness, tags=tags, filter=filter, subscription_manager_id=subscription_manager_id)
    except Exception as e:
        print("Exception when calling HostsApi->api_host_delete_hosts_by_filter: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **display_name** | **str**| Filter by display_name (case-insensitive) | [optional]
 **fqdn** | **str**| Filter by FQDN (case-insensitive) | [optional]
 **hostname_or_id** | **str**| Filter by display_name, fqdn, id (case-insensitive) | [optional]
 **insights_id** | **str**| Filter by insights_id | [optional]
 **provider_id** | **str**| Filter by provider_id | [optional]
 **provider_type** | **str**| Filter by provider_type | [optional]
 **updated_start** | **datetime**| Only show hosts last modified after the given date | [optional]
 **updated_end** | **datetime**| Only show hosts last modified before the given date | [optional]
 **last_check_in_start** | **datetime**| Only show hosts last checked in after the given date | [optional]
 **last_check_in_end** | **datetime**| Only show hosts last checked in before the given date | [optional]
 **group_name** | [**List[str]**](str.md)| Filter by group name | [optional]
 **group_id** | [**List[str]**](str.md)| Filter by group ID (UUID format) | [optional]
 **registered_with** | [**List[str]**](str.md)| Filters out any host not registered by the specified reporters | [optional]
 **system_type** | [**List[str]**](str.md)| Filters systems by type | [optional]
 **staleness** | [**List[str]**](str.md)| Culling states of the hosts. | [optional]
 **tags** | [**List[str]**](str.md)| filters out hosts not tagged by the given tags | [optional]
 **filter** | [**Dict[str, SystemProfileNestedObjectValue]**](SystemProfileNestedObjectValue.md)| Filters hosts based on system_profile fields. For example: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;workloads\&quot;: {\&quot;sap\&quot;: {\&quot;sap_system\&quot;: {\&quot;eq\&quot;: \&quot;true\&quot;}}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][sap_system][eq]&#x3D;true\&quot; &lt;br /&gt;&lt;br /&gt; To get \&quot;edge\&quot; hosts, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;host_type\&quot;: {\&quot;eq\&quot;: \&quot;edge\&quot;}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][host_type][eq]&#x3D;edge\&quot; &lt;br /&gt;&lt;br /&gt; To get hosts with an specific operating system, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;operating_system\&quot;: {\&quot;name\&quot;: {\&quot;eq\&quot;: \&quot;rhel\&quot;}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][name][eq]&#x3D;rhel\&quot; | [optional]
 **subscription_manager_id** | **str**| Filter by subscription_manager_id | [optional]

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
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.host_query_output import HostQueryOutput
from iqe_host_inventory_api_v7.models.system_profile_nested_object_value import SystemProfileNestedObjectValue
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
    api_instance = iqe_host_inventory_api_v7.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # List[str] | A comma-separated list of host IDs.
    branch_id = 'branch_id_example' # str | Filter by branch_id (optional)
    per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
    page = 1 # int | A page number of the items to return. (optional) (default to 1)
    order_by = 'order_by_example' # str | Ordering field name (optional)
    order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system (optional)
    fields = {'key': iqe_host_inventory_api_v7.SystemProfileNestedObjectValue()} # Dict[str, SystemProfileNestedObjectValue] | Fetches only mentioned system_profile fields. For example, <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": [\"arch\", \"host_type\"]} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?fields[system_profile]=arch,host_type\" (optional)

    try:
        # Find hosts by their IDs
        api_response = api_instance.api_host_get_host_by_id(host_id_list, branch_id=branch_id, per_page=per_page, page=page, order_by=order_by, order_how=order_how, fields=fields)
        print("The response of HostsApi->api_host_get_host_by_id:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling HostsApi->api_host_get_host_by_id: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**List[str]**](str.md)| A comma-separated list of host IDs. |
 **branch_id** | **str**| Filter by branch_id | [optional]
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **order_by** | **str**| Ordering field name | [optional]
 **order_how** | **str**| Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system | [optional]
 **fields** | [**Dict[str, SystemProfileNestedObjectValue]**](SystemProfileNestedObjectValue.md)| Fetches only mentioned system_profile fields. For example, &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: [\&quot;arch\&quot;, \&quot;host_type\&quot;]} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?fields[system_profile]&#x3D;arch,host_type\&quot; | [optional]

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
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.host_id_out import HostIdOut
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
    api_instance = iqe_host_inventory_api_v7.HostsApi(api_client)
    insights_id = 'insights_id_example' # str | Filter by insights_id (optional)

    try:
        # Find one host by insights_id, if it exists
        api_response = api_instance.api_host_get_host_exists(insights_id=insights_id)
        print("The response of HostsApi->api_host_get_host_exists:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling HostsApi->api_host_get_host_exists: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **insights_id** | **str**| Filter by insights_id | [optional]

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
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.host_query_output import HostQueryOutput
from iqe_host_inventory_api_v7.models.system_profile_nested_object_value import SystemProfileNestedObjectValue
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
    api_instance = iqe_host_inventory_api_v7.HostsApi(api_client)
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
    group_name = ['group_name_example'] # List[str] | Filter by group name (optional)
    group_id = ['group_id_example'] # List[str] | Filter by group ID (UUID format) (optional)
    branch_id = 'branch_id_example' # str | Filter by branch_id (optional)
    per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
    page = 1 # int | A page number of the items to return. (optional) (default to 1)
    order_by = 'order_by_example' # str | Ordering field name (optional)
    order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system (optional)
    staleness = ["fresh","stale","stale_warning"] # List[str] | Culling states of the hosts. Default: fresh, stale and stale_warning (optional) (default to ["fresh","stale","stale_warning"])
    tags = ['tags_example'] # List[str] | filters out hosts not tagged by the given tags (optional)
    registered_with = ['registered_with_example'] # List[str] | Filters out any host not registered by the specified reporters (optional)
    system_type = ['system_type_example'] # List[str] | Filters systems by type (optional)
    filter = {'key': iqe_host_inventory_api_v7.SystemProfileNestedObjectValue()} # Dict[str, SystemProfileNestedObjectValue] | Filters hosts based on system_profile fields. For example: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"workloads\": {\"sap\": {\"sap_system\": {\"eq\": \"true\"}}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][sap_system][eq]=true\" <br /><br /> To get \"edge\" hosts, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"host_type\": {\"eq\": \"edge\"}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][host_type][eq]=edge\" <br /><br /> To get hosts with an specific operating system, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"operating_system\": {\"name\": {\"eq\": \"rhel\"}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][name][eq]=rhel\" (optional)
    fields = {'key': iqe_host_inventory_api_v7.SystemProfileNestedObjectValue()} # Dict[str, SystemProfileNestedObjectValue] | Fetches only mentioned system_profile fields. For example, <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": [\"arch\", \"host_type\"]} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?fields[system_profile]=arch,host_type\" (optional)

    try:
        # Read the entire list of hosts
        api_response = api_instance.api_host_get_host_list(display_name=display_name, fqdn=fqdn, hostname_or_id=hostname_or_id, insights_id=insights_id, subscription_manager_id=subscription_manager_id, provider_id=provider_id, provider_type=provider_type, updated_start=updated_start, updated_end=updated_end, last_check_in_start=last_check_in_start, last_check_in_end=last_check_in_end, group_name=group_name, group_id=group_id, branch_id=branch_id, per_page=per_page, page=page, order_by=order_by, order_how=order_how, staleness=staleness, tags=tags, registered_with=registered_with, system_type=system_type, filter=filter, fields=fields)
        print("The response of HostsApi->api_host_get_host_list:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling HostsApi->api_host_get_host_list: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **display_name** | **str**| Filter by display_name (case-insensitive) | [optional]
 **fqdn** | **str**| Filter by FQDN (case-insensitive) | [optional]
 **hostname_or_id** | **str**| Filter by display_name, fqdn, id (case-insensitive) | [optional]
 **insights_id** | **str**| Filter by insights_id | [optional]
 **subscription_manager_id** | **str**| Filter by subscription_manager_id | [optional]
 **provider_id** | **str**| Filter by provider_id | [optional]
 **provider_type** | **str**| Filter by provider_type | [optional]
 **updated_start** | **datetime**| Only show hosts last modified after the given date | [optional]
 **updated_end** | **datetime**| Only show hosts last modified before the given date | [optional]
 **last_check_in_start** | **datetime**| Only show hosts last checked in after the given date | [optional]
 **last_check_in_end** | **datetime**| Only show hosts last checked in before the given date | [optional]
 **group_name** | [**List[str]**](str.md)| Filter by group name | [optional]
 **group_id** | [**List[str]**](str.md)| Filter by group ID (UUID format) | [optional]
 **branch_id** | **str**| Filter by branch_id | [optional]
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **order_by** | **str**| Ordering field name | [optional]
 **order_how** | **str**| Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system | [optional]
 **staleness** | [**List[str]**](str.md)| Culling states of the hosts. Default: fresh, stale and stale_warning | [optional] [default to [&quot;fresh&quot;,&quot;stale&quot;,&quot;stale_warning&quot;]]
 **tags** | [**List[str]**](str.md)| filters out hosts not tagged by the given tags | [optional]
 **registered_with** | [**List[str]**](str.md)| Filters out any host not registered by the specified reporters | [optional]
 **system_type** | [**List[str]**](str.md)| Filters systems by type | [optional]
 **filter** | [**Dict[str, SystemProfileNestedObjectValue]**](SystemProfileNestedObjectValue.md)| Filters hosts based on system_profile fields. For example: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;workloads\&quot;: {\&quot;sap\&quot;: {\&quot;sap_system\&quot;: {\&quot;eq\&quot;: \&quot;true\&quot;}}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][sap_system][eq]&#x3D;true\&quot; &lt;br /&gt;&lt;br /&gt; To get \&quot;edge\&quot; hosts, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;host_type\&quot;: {\&quot;eq\&quot;: \&quot;edge\&quot;}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][host_type][eq]&#x3D;edge\&quot; &lt;br /&gt;&lt;br /&gt; To get hosts with an specific operating system, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;operating_system\&quot;: {\&quot;name\&quot;: {\&quot;eq\&quot;: \&quot;rhel\&quot;}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][name][eq]&#x3D;rhel\&quot; | [optional]
 **fields** | [**Dict[str, SystemProfileNestedObjectValue]**](SystemProfileNestedObjectValue.md)| Fetches only mentioned system_profile fields. For example, &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: [\&quot;arch\&quot;, \&quot;host_type\&quot;]} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?fields[system_profile]&#x3D;arch,host_type\&quot; | [optional]

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
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.system_profile_by_host_out import SystemProfileByHostOut
from iqe_host_inventory_api_v7.models.system_profile_nested_object_value import SystemProfileNestedObjectValue
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
    api_instance = iqe_host_inventory_api_v7.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # List[str] | A comma-separated list of host IDs.
    per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
    page = 1 # int | A page number of the items to return. (optional) (default to 1)
    order_by = 'order_by_example' # str | Ordering field name (optional)
    order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system (optional)
    branch_id = 'branch_id_example' # str | Filter by branch_id (optional)
    fields = {'key': iqe_host_inventory_api_v7.SystemProfileNestedObjectValue()} # Dict[str, SystemProfileNestedObjectValue] | Fetches only mentioned system_profile fields. For example, <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": [\"arch\", \"host_type\"]} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?fields[system_profile]=arch,host_type\" (optional)

    try:
        # Return one or more hosts system profile
        api_response = api_instance.api_host_get_host_system_profile_by_id(host_id_list, per_page=per_page, page=page, order_by=order_by, order_how=order_how, branch_id=branch_id, fields=fields)
        print("The response of HostsApi->api_host_get_host_system_profile_by_id:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling HostsApi->api_host_get_host_system_profile_by_id: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**List[str]**](str.md)| A comma-separated list of host IDs. |
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **order_by** | **str**| Ordering field name | [optional]
 **order_how** | **str**| Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system | [optional]
 **branch_id** | **str**| Filter by branch_id | [optional]
 **fields** | [**Dict[str, SystemProfileNestedObjectValue]**](SystemProfileNestedObjectValue.md)| Fetches only mentioned system_profile fields. For example, &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: [\&quot;arch\&quot;, \&quot;host_type\&quot;]} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?fields[system_profile]&#x3D;arch,host_type\&quot; | [optional]

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
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.tag_count_out import TagCountOut
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
    api_instance = iqe_host_inventory_api_v7.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # List[str] | A comma-separated list of host IDs.
    per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
    page = 1 # int | A page number of the items to return. (optional) (default to 1)
    order_by = 'order_by_example' # str | Ordering field name (optional)
    order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system (optional)

    try:
        # Get the number of tags on a host or hosts
        api_response = api_instance.api_host_get_host_tag_count(host_id_list, per_page=per_page, page=page, order_by=order_by, order_how=order_how)
        print("The response of HostsApi->api_host_get_host_tag_count:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling HostsApi->api_host_get_host_tag_count: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**List[str]**](str.md)| A comma-separated list of host IDs. |
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
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.tags_out import TagsOut
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
    api_instance = iqe_host_inventory_api_v7.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # List[str] | A comma-separated list of host IDs.
    per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
    page = 1 # int | A page number of the items to return. (optional) (default to 1)
    order_by = 'order_by_example' # str | Ordering field name (optional)
    order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive); defaults to ASC for display_name, and to DESC for updated and operating_system (optional)
    search = 'search_example' # str | Used for searching tags and sap_sids that match the given search string. For searching tags, a tag's namespace, key, and/or value is used for matching. (optional)

    try:
        # Get the tags on a host
        api_response = api_instance.api_host_get_host_tags(host_id_list, per_page=per_page, page=page, order_by=order_by, order_how=order_how, search=search)
        print("The response of HostsApi->api_host_get_host_tags:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling HostsApi->api_host_get_host_tags: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**List[str]**](str.md)| A comma-separated list of host IDs. |
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
* Bearer Authentication (BearerAuth):

```python
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.create_check_in import CreateCheckIn
from iqe_host_inventory_api_v7.models.host_out import HostOut
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
    api_instance = iqe_host_inventory_api_v7.HostsApi(api_client)
    create_check_in = iqe_host_inventory_api_v7.CreateCheckIn() # CreateCheckIn | Data required to create a check-in record for a host.

    try:
        # Update staleness timestamps for a host matching the provided facts
        api_response = api_instance.api_host_host_checkin(create_check_in)
        print("The response of HostsApi->api_host_host_checkin:\n")
        pprint(api_response)
    except Exception as e:
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
    api_instance = iqe_host_inventory_api_v7.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # List[str] | A comma-separated list of host IDs.
    namespace = 'namespace_example' # str | A namespace of the merged facts.
    body = None # object | A dictionary with the new facts to merge with the original ones.
    branch_id = 'branch_id_example' # str | Filter by branch_id (optional)

    try:
        # Merge facts under a namespace
        api_instance.api_host_merge_facts(host_id_list, namespace, body, branch_id=branch_id)
    except Exception as e:
        print("Exception when calling HostsApi->api_host_merge_facts: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**List[str]**](str.md)| A comma-separated list of host IDs. |
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
import iqe_host_inventory_api_v7
from iqe_host_inventory_api_v7.models.patch_host_in import PatchHostIn
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
    api_instance = iqe_host_inventory_api_v7.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # List[str] | A comma-separated list of host IDs.
    patch_host_in = iqe_host_inventory_api_v7.PatchHostIn() # PatchHostIn | A group of fields to be updated on the hosts
    branch_id = 'branch_id_example' # str | Filter by branch_id (optional)

    try:
        # Update hosts
        api_response = api_instance.api_host_patch_host_by_id(host_id_list, patch_host_in, branch_id=branch_id)
        print("The response of HostsApi->api_host_patch_host_by_id:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling HostsApi->api_host_patch_host_by_id: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**List[str]**](str.md)| A comma-separated list of host IDs. |
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
    api_instance = iqe_host_inventory_api_v7.HostsApi(api_client)
    host_id_list = ['host_id_list_example'] # List[str] | A comma-separated list of host IDs.
    namespace = 'namespace_example' # str | A namespace of the merged facts.
    body = None # object | A dictionary with the new facts to replace the original ones.
    branch_id = 'branch_id_example' # str | Filter by branch_id (optional)

    try:
        # Replace facts under a namespace
        api_instance.api_host_replace_facts(host_id_list, namespace, body, branch_id=branch_id)
    except Exception as e:
        print("Exception when calling HostsApi->api_host_replace_facts: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **host_id_list** | [**List[str]**](str.md)| A comma-separated list of host IDs. |
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
