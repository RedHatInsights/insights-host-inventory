# iqe_host_inventory_api.SystemProfileApi

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**api_system_profile_get_operating_system**](SystemProfileApi.md#api_system_profile_get_operating_system) | **GET** /system_profile/operating_system | get all operating system versions and counts on the account
[**api_system_profile_get_sap_sids**](SystemProfileApi.md#api_system_profile_get_sap_sids) | **GET** /system_profile/sap_sids | get all sap sids values and counts on the account
[**api_system_profile_get_sap_system**](SystemProfileApi.md#api_system_profile_get_sap_system) | **GET** /system_profile/sap_system | get all sap system values and counts on the account
[**api_system_profile_validate_schema**](SystemProfileApi.md#api_system_profile_validate_schema) | **POST** /system_profile/validate_schema | validate system profile schema


# **api_system_profile_get_operating_system**
> SystemProfileOperatingSystemOut api_system_profile_get_operating_system(tags=tags, per_page=per_page, page=page, staleness=staleness, registered_with=registered_with, filter=filter)

get all operating system versions and counts on the account

Required permissions: inventory:hosts:read

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
    api_instance = iqe_host_inventory_api.SystemProfileApi(api_client)
    tags = ['tags_example'] # list[str] | Filters systems by tag(s). Specify multiple tags as a comma-separated list (e.g. insights-client/security=strict,env/type=prod). (optional)
per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
page = 1 # int | A page number of the items to return. (optional) (default to 1)
staleness = ["fresh","stale","stale_warning"] # list[str] | Culling states of the hosts. Default: fresh, stale and stale_warning (optional) (default to ["fresh","stale","stale_warning"])
registered_with = ['registered_with_example'] # list[str] | Filters out any host not registered by the specified reporters (optional)
filter = {'key': {}} # dict(str, object) | Filters hosts based on system_profile fields. For example: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"workloads\": {\"sap\": {\"sap_system\": {\"eq\": \"true\"}}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][sap_system][eq]=true\" <br /><br /> To get \"edge\" hosts, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"host_type\": {\"eq\": \"edge\"}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][host_type][eq]=edge\" <br /><br /> To get hosts with an specific operating system, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"operating_system\": {\"name\": {\"eq\": \"rhel\"}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][name][eq]=rhel\" (optional)

    try:
        # get all operating system versions and counts on the account
        api_response = api_instance.api_system_profile_get_operating_system(tags=tags, per_page=per_page, page=page, staleness=staleness, registered_with=registered_with, filter=filter)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling SystemProfileApi->api_system_profile_get_operating_system: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **tags** | [**list[str]**](str.md)| Filters systems by tag(s). Specify multiple tags as a comma-separated list (e.g. insights-client/security&#x3D;strict,env/type&#x3D;prod). | [optional]
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **staleness** | [**list[str]**](str.md)| Culling states of the hosts. Default: fresh, stale and stale_warning | [optional] [default to [&quot;fresh&quot;,&quot;stale&quot;,&quot;stale_warning&quot;]]
 **registered_with** | [**list[str]**](str.md)| Filters out any host not registered by the specified reporters | [optional]
 **filter** | [**dict(str, object)**](object.md)| Filters hosts based on system_profile fields. For example: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;workloads\&quot;: {\&quot;sap\&quot;: {\&quot;sap_system\&quot;: {\&quot;eq\&quot;: \&quot;true\&quot;}}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][sap_system][eq]&#x3D;true\&quot; &lt;br /&gt;&lt;br /&gt; To get \&quot;edge\&quot; hosts, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;host_type\&quot;: {\&quot;eq\&quot;: \&quot;edge\&quot;}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][host_type][eq]&#x3D;edge\&quot; &lt;br /&gt;&lt;br /&gt; To get hosts with an specific operating system, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;operating_system\&quot;: {\&quot;name\&quot;: {\&quot;eq\&quot;: \&quot;rhel\&quot;}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][name][eq]&#x3D;rhel\&quot; | [optional]

### Return type

[**SystemProfileOperatingSystemOut**](SystemProfileOperatingSystemOut.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | operating system versions and counts on the account |  -  |
**400** | Invalid request. |  -  |
**404** | Requested page is outside of the range of available pages |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_system_profile_get_sap_sids**
> SystemProfileSapSystemOut api_system_profile_get_sap_sids(search=search, tags=tags, per_page=per_page, page=page, staleness=staleness, registered_with=registered_with, filter=filter)

get all sap sids values and counts on the account

Required permissions: inventory:hosts:read

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
    api_instance = iqe_host_inventory_api.SystemProfileApi(api_client)
    search = 'search_example' # str | Used for searching tags and sap_sids that match the given search string. For searching tags, a tag's namespace, key, and/or value is used for matching. (optional)
tags = ['tags_example'] # list[str] | Filters systems by tag(s). Specify multiple tags as a comma-separated list (e.g. insights-client/security=strict,env/type=prod). (optional)
per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
page = 1 # int | A page number of the items to return. (optional) (default to 1)
staleness = ["fresh","stale","stale_warning"] # list[str] | Culling states of the hosts. Default: fresh, stale and stale_warning (optional) (default to ["fresh","stale","stale_warning"])
registered_with = ['registered_with_example'] # list[str] | Filters out any host not registered by the specified reporters (optional)
filter = {'key': {}} # dict(str, object) | Filters hosts based on system_profile fields. For example: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"workloads\": {\"sap\": {\"sap_system\": {\"eq\": \"true\"}}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][sap_system][eq]=true\" <br /><br /> To get \"edge\" hosts, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"host_type\": {\"eq\": \"edge\"}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][host_type][eq]=edge\" <br /><br /> To get hosts with an specific operating system, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"operating_system\": {\"name\": {\"eq\": \"rhel\"}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][name][eq]=rhel\" (optional)

    try:
        # get all sap sids values and counts on the account
        api_response = api_instance.api_system_profile_get_sap_sids(search=search, tags=tags, per_page=per_page, page=page, staleness=staleness, registered_with=registered_with, filter=filter)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling SystemProfileApi->api_system_profile_get_sap_sids: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **search** | **str**| Used for searching tags and sap_sids that match the given search string. For searching tags, a tag&#39;s namespace, key, and/or value is used for matching. | [optional]
 **tags** | [**list[str]**](str.md)| Filters systems by tag(s). Specify multiple tags as a comma-separated list (e.g. insights-client/security&#x3D;strict,env/type&#x3D;prod). | [optional]
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **staleness** | [**list[str]**](str.md)| Culling states of the hosts. Default: fresh, stale and stale_warning | [optional] [default to [&quot;fresh&quot;,&quot;stale&quot;,&quot;stale_warning&quot;]]
 **registered_with** | [**list[str]**](str.md)| Filters out any host not registered by the specified reporters | [optional]
 **filter** | [**dict(str, object)**](object.md)| Filters hosts based on system_profile fields. For example: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;workloads\&quot;: {\&quot;sap\&quot;: {\&quot;sap_system\&quot;: {\&quot;eq\&quot;: \&quot;true\&quot;}}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][sap_system][eq]&#x3D;true\&quot; &lt;br /&gt;&lt;br /&gt; To get \&quot;edge\&quot; hosts, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;host_type\&quot;: {\&quot;eq\&quot;: \&quot;edge\&quot;}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][host_type][eq]&#x3D;edge\&quot; &lt;br /&gt;&lt;br /&gt; To get hosts with an specific operating system, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;operating_system\&quot;: {\&quot;name\&quot;: {\&quot;eq\&quot;: \&quot;rhel\&quot;}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][name][eq]&#x3D;rhel\&quot; | [optional]

### Return type

[**SystemProfileSapSystemOut**](SystemProfileSapSystemOut.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | sap_system values and counts for the account |  -  |
**400** | Invalid request. |  -  |
**404** | Requested page is outside of the range of available pages |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_system_profile_get_sap_system**
> SystemProfileSapSystemOut api_system_profile_get_sap_system(tags=tags, per_page=per_page, page=page, staleness=staleness, registered_with=registered_with, filter=filter)

get all sap system values and counts on the account

Required permissions: inventory:hosts:read

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
    api_instance = iqe_host_inventory_api.SystemProfileApi(api_client)
    tags = ['tags_example'] # list[str] | Filters systems by tag(s). Specify multiple tags as a comma-separated list (e.g. insights-client/security=strict,env/type=prod). (optional)
per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
page = 1 # int | A page number of the items to return. (optional) (default to 1)
staleness = ["fresh","stale","stale_warning"] # list[str] | Culling states of the hosts. Default: fresh, stale and stale_warning (optional) (default to ["fresh","stale","stale_warning"])
registered_with = ['registered_with_example'] # list[str] | Filters out any host not registered by the specified reporters (optional)
filter = {'key': {}} # dict(str, object) | Filters hosts based on system_profile fields. For example: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"workloads\": {\"sap\": {\"sap_system\": {\"eq\": \"true\"}}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][sap_system][eq]=true\" <br /><br /> To get \"edge\" hosts, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"host_type\": {\"eq\": \"edge\"}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][host_type][eq]=edge\" <br /><br /> To get hosts with an specific operating system, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"operating_system\": {\"name\": {\"eq\": \"rhel\"}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][name][eq]=rhel\" (optional)

    try:
        # get all sap system values and counts on the account
        api_response = api_instance.api_system_profile_get_sap_system(tags=tags, per_page=per_page, page=page, staleness=staleness, registered_with=registered_with, filter=filter)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling SystemProfileApi->api_system_profile_get_sap_system: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **tags** | [**list[str]**](str.md)| Filters systems by tag(s). Specify multiple tags as a comma-separated list (e.g. insights-client/security&#x3D;strict,env/type&#x3D;prod). | [optional]
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **staleness** | [**list[str]**](str.md)| Culling states of the hosts. Default: fresh, stale and stale_warning | [optional] [default to [&quot;fresh&quot;,&quot;stale&quot;,&quot;stale_warning&quot;]]
 **registered_with** | [**list[str]**](str.md)| Filters out any host not registered by the specified reporters | [optional]
 **filter** | [**dict(str, object)**](object.md)| Filters hosts based on system_profile fields. For example: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;workloads\&quot;: {\&quot;sap\&quot;: {\&quot;sap_system\&quot;: {\&quot;eq\&quot;: \&quot;true\&quot;}}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][sap_system][eq]&#x3D;true\&quot; &lt;br /&gt;&lt;br /&gt; To get \&quot;edge\&quot; hosts, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;host_type\&quot;: {\&quot;eq\&quot;: \&quot;edge\&quot;}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][host_type][eq]&#x3D;edge\&quot; &lt;br /&gt;&lt;br /&gt; To get hosts with an specific operating system, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;operating_system\&quot;: {\&quot;name\&quot;: {\&quot;eq\&quot;: \&quot;rhel\&quot;}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][name][eq]&#x3D;rhel\&quot; | [optional]

### Return type

[**SystemProfileSapSystemOut**](SystemProfileSapSystemOut.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | sap_system values and counts for the account |  -  |
**400** | Invalid request. |  -  |
**404** | Requested page is outside of the range of available pages |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **api_system_profile_validate_schema**
> api_system_profile_validate_schema(repo_branch, repo_fork=repo_fork, days=days, max_messages=max_messages)

validate system profile schema

Validates System Profile data from recent Kafka messages against a given spec, and compares it with the current one. Only HBI Admins can access this endpoint.

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
    api_instance = iqe_host_inventory_api.SystemProfileApi(api_client)
    repo_branch = 'repo_branch_example' # str | The branch of the inventory-schemas repo to use
repo_fork = 'repo_fork_example' # str | The fork of the inventory-schemas repo to use (optional)
days = 56 # int | How many days worth of data to validate (optional)
max_messages = 10000 # int | Stops polling when this number of messages has been collected (optional) (default to 10000)

    try:
        # validate system profile schema
        api_instance.api_system_profile_validate_schema(repo_branch, repo_fork=repo_fork, days=days, max_messages=max_messages)
    except ApiException as e:
        print("Exception when calling SystemProfileApi->api_system_profile_validate_schema: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_branch** | **str**| The branch of the inventory-schemas repo to use |
 **repo_fork** | **str**| The fork of the inventory-schemas repo to use | [optional]
 **days** | **int**| How many days worth of data to validate | [optional]
 **max_messages** | **int**| Stops polling when this number of messages has been collected | [optional] [default to 10000]

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
**200** | Host validation results |  -  |
**403** | Forbidden |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)
