# iqe_host_inventory_api.TagsApi

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**api_tag_get_tags**](TagsApi.md#api_tag_get_tags) | **GET** /tags | Get the active host tags for a given account


# **api_tag_get_tags**
> ActiveTags api_tag_get_tags(tags=tags, order_by=order_by, order_how=order_how, per_page=per_page, page=page, staleness=staleness, search=search, display_name=display_name, fqdn=fqdn, hostname_or_id=hostname_or_id, insights_id=insights_id, provider_id=provider_id, provider_type=provider_type, updated_start=updated_start, updated_end=updated_end, last_check_in_start=last_check_in_start, last_check_in_end=last_check_in_end, group_name=group_name, group_id=group_id, registered_with=registered_with, system_type=system_type, filter=filter)

Get the active host tags for a given account

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
    api_instance = iqe_host_inventory_api.TagsApi(api_client)
    tags = ['tags_example'] # list[str] | filters out hosts not tagged by the given tags (optional)
order_by = 'tag' # str | Ordering field name (optional) (default to 'tag')
order_how = 'order_how_example' # str | Direction of the ordering (case-insensitive). Valid values are ASC (default) and DESC. (optional)
per_page = 50 # int | A number of items to return per page. (optional) (default to 50)
page = 1 # int | A page number of the items to return. (optional) (default to 1)
staleness = ["fresh","stale","stale_warning"] # list[str] | Culling states of the hosts. Default: fresh, stale and stale_warning (optional) (default to ["fresh","stale","stale_warning"])
search = 'search_example' # str | Used for searching tags and sap_sids that match the given search string. For searching tags, a tag's namespace, key, and/or value is used for matching. (optional)
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
filter = {'key': {}} # dict(str, object) | Filters hosts based on system_profile fields. For example: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"workloads\": {\"sap\": {\"sap_system\": {\"eq\": \"true\"}}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][sap_system][eq]=true\" <br /><br /> To get \"edge\" hosts, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"host_type\": {\"eq\": \"edge\"}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][host_type][eq]=edge\" <br /><br /> To get hosts with an specific operating system, use this explicit filter: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;{\"system_profile\": {\"operating_system\": {\"name\": {\"eq\": \"rhel\"}}}} <br /><br /> which equates to the URL param: <br /><br /> &nbsp;&nbsp;&nbsp;&nbsp;\"?filter[system_profile][name][eq]=rhel\" (optional)

    try:
        # Get the active host tags for a given account
        api_response = api_instance.api_tag_get_tags(tags=tags, order_by=order_by, order_how=order_how, per_page=per_page, page=page, staleness=staleness, search=search, display_name=display_name, fqdn=fqdn, hostname_or_id=hostname_or_id, insights_id=insights_id, provider_id=provider_id, provider_type=provider_type, updated_start=updated_start, updated_end=updated_end, last_check_in_start=last_check_in_start, last_check_in_end=last_check_in_end, group_name=group_name, group_id=group_id, registered_with=registered_with, system_type=system_type, filter=filter)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling TagsApi->api_tag_get_tags: %s\n" % e)
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **tags** | [**list[str]**](str.md)| filters out hosts not tagged by the given tags | [optional]
 **order_by** | **str**| Ordering field name | [optional] [default to &#39;tag&#39;]
 **order_how** | **str**| Direction of the ordering (case-insensitive). Valid values are ASC (default) and DESC. | [optional]
 **per_page** | **int**| A number of items to return per page. | [optional] [default to 50]
 **page** | **int**| A page number of the items to return. | [optional] [default to 1]
 **staleness** | [**list[str]**](str.md)| Culling states of the hosts. Default: fresh, stale and stale_warning | [optional] [default to [&quot;fresh&quot;,&quot;stale&quot;,&quot;stale_warning&quot;]]
 **search** | **str**| Used for searching tags and sap_sids that match the given search string. For searching tags, a tag&#39;s namespace, key, and/or value is used for matching. | [optional]
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
 **filter** | [**dict(str, object)**](object.md)| Filters hosts based on system_profile fields. For example: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;workloads\&quot;: {\&quot;sap\&quot;: {\&quot;sap_system\&quot;: {\&quot;eq\&quot;: \&quot;true\&quot;}}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][sap_system][eq]&#x3D;true\&quot; &lt;br /&gt;&lt;br /&gt; To get \&quot;edge\&quot; hosts, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;host_type\&quot;: {\&quot;eq\&quot;: \&quot;edge\&quot;}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][host_type][eq]&#x3D;edge\&quot; &lt;br /&gt;&lt;br /&gt; To get hosts with an specific operating system, use this explicit filter: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;{\&quot;system_profile\&quot;: {\&quot;operating_system\&quot;: {\&quot;name\&quot;: {\&quot;eq\&quot;: \&quot;rhel\&quot;}}}} &lt;br /&gt;&lt;br /&gt; which equates to the URL param: &lt;br /&gt;&lt;br /&gt; &amp;nbsp;&amp;nbsp;&amp;nbsp;&amp;nbsp;\&quot;?filter[system_profile][name][eq]&#x3D;rhel\&quot; | [optional]

### Return type

[**ActiveTags**](ActiveTags.md)

### Authorization

[ApiKeyAuth](../README.md#ApiKeyAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Tags |  -  |
**400** | Invalid request. |  -  |
**404** | Requested page is outside of the range of available pages |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)
