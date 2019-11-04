import json
import re
import urllib

#TODO: REMOVE
from app.logging import get_logger
logger = get_logger(__name__)

class HostWrapper:
    def __init__(self, data=None):
        self.__data = data or {}

    def data(self):
        return self.__data

    def __delattr__(self, name):
        if name in self.__data:
            del self.__data[name]
        # else:
        #    raise AttributeError("No such attribute: " + name)

    @property
    def insights_id(self):
        return self.__data.get("insights_id", None)

    @insights_id.setter
    def insights_id(self, cf):
        self.__data["insights_id"] = cf

    @property
    def rhel_machine_id(self):
        return self.__data.get("rhel_machine_id", None)

    @rhel_machine_id.setter
    def rhel_machine_id(self, cf):
        self.__data["rhel_machine_id"] = cf

    @property
    def subscription_manager_id(self):
        return self.__data.get("subscription_manager_id", None)

    @subscription_manager_id.setter
    def subscription_manager_id(self, cf):
        self.__data["subscription_manager_id"] = cf

    @property
    def satellite_id(self):
        return self.__data.get("satellite_id", None)

    @satellite_id.setter
    def satellite_id(self, cf):
        self.__data["satellite_id"] = cf

    @property
    def bios_uuid(self):
        return self.__data.get("bios_uuid", None)

    @bios_uuid.setter
    def bios_uuid(self, cf):
        self.__data["bios_uuid"] = cf

    @property
    def ip_addresses(self):
        return self.__data.get("ip_addresses", None)

    @ip_addresses.setter
    def ip_addresses(self, cf):
        self.__data["ip_addresses"] = cf

    @property
    def fqdn(self):
        return self.__data.get("fqdn")

    @fqdn.setter
    def fqdn(self, cf):
        self.__data["fqdn"] = cf

    @property
    def mac_addresses(self):
        return self.__data.get("mac_addresses", None)

    @mac_addresses.setter
    def mac_addresses(self, cf):
        self.__data["mac_addresses"] = cf

    @property
    def external_id(self):
        return self.__data.get("external_id")

    @external_id.setter
    def external_id(self, cf):
        self.__data["external_id"] = cf

    @property
    def facts(self):
        return self.__data.get("facts", None)

    @facts.setter
    def facts(self, facts):
        self.__data["facts"] = facts

    @property
    def tags(self):
        return self.__data.get("tags", None)

    @tags.setter
    def tags(self, tags):
        self.__data["tags"] = tags

    @property
    def id(self):
        return self.__data.get("id", None)

    @id.setter
    def id(self, id):
        self.__data["id"] = id

    @property
    def account(self):
        return self.__data.get("account", None)

    @account.setter
    def account(self, account):
        self.__data["account"] = account

    @property
    def display_name(self):
        return self.__data.get("display_name", None)

    @display_name.setter
    def display_name(self, display_name):
        self.__data["display_name"] = display_name

    @property
    def ansible_host(self):
        return self.__data.get("ansible_host", None)

    @ansible_host.setter
    def ansible_host(self, ansible_host):
        self.__data["ansible_host"] = ansible_host

    def to_json(self):
        return json.dumps(self.__data)

    @classmethod
    def from_json(cls, d):
        return cls(json.loads(d))

'''
Tagging: functions for converting tags between valid representations
'''
class Tag: 
    def __init__(self, data=None):
        self.__data = data or {}

    def data(self):
        return self.__data

    def __delattr__(self, name):
        if name in self.__data:
            del self.__data[name]

    @property
    def namespace(self):
        return self.__data.get("insights_id", None)

    @namespace.setter
    def namespace(self, namespace):
        self.__data["namespace"] = namespace

    @property
    def key(self):
        return self.__data.get("insights_id", None)

    @key.setter
    def key(self, key):
        self.__data["key"] = key

    @property
    def value(self):
        return self.__data.get("insights_id", None)

    @value.setter
    def value(self, value):
        self.__data["value"] = value

    def _split_string_tag(self, string_tag):
        namespace = None
        key = None 
        value = None

        if(re.match(r"\w+\/\w+=\w+", string_tag)):  # NS/key=value
            namespace, key, value = re.split(r"/|=", string_tag)
        elif(re.match(r"\w+\/\w+", string_tag)):  # NS/key
            namespace, key = re.split(r"/", string_tag)
        else:  # key
            key = string_tag

        return (namespace, key, value)

    def _create_nested(self, namespace, key, value):
        return {
            namespace: {
                key: [
                    value
                ]
            }
        }

    def tag_string_to_structured(self, string_tag):
        namespace, key, value = self._split_string_tag(string_tag)
        
        return {
            "namespace" : namespace,
            "key" : key,
            "value" : value
        }

    def tag_string_to_nested(self, string_tag):
        namespace, key, value = self._split_string_tag(string_tag)

        return self._create_nested(namespace, key, value)

    def tag_structured_to_string(self, structured_tag):
        namespace = urllib.urlencode(structured_tag.namespace)
        key = urllib.urlencode(structured_tag.key)
        value = urllib.urlencode(structured_tag.value)

        return f"{namespace}/{key}={value}"

    def tag_structured_to_nested(self, structured_tag):
        return {
            structured_tag.namespace: {
                structured_tag.key: [
                    structured_tag.value
                ]
            }
        }


    # def tag_nested_to_string(nested_tag):


    # def tag_nested_to_structured(nested_tag):