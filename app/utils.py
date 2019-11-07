import json
import re
import urllib


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


"""
Tagging: functions for converting tags between valid representations
"""


class Tag:
    def __init__(self, namespace=None, key=None, value=None):
        self.__data = {"namespace": namespace, "key": key, "value": value}

    def data(self):
        return self.__data

    @property
    def namespace(self):
        return self.__data.get("namespace", None)

    @namespace.setter
    def namespace(self, namespace):
        self.__data["namespace"] = namespace

    @property
    def key(self):
        return self.__data.get("key", None)

    @key.setter
    def key(self, key):
        self.__data["key"] = key

    @property
    def value(self):
        return self.__data.get("value", None)

    @value.setter
    def value(self, value):
        self.__data["value"] = value

    def _split_string_tag(self, string_tag):
        namespace = None
        key = None
        value = None

        if re.match(r"\w+\/\w+=\w+", string_tag):  # NS/key=value
            namespace, key, value = re.split(r"/|=", string_tag)
        elif re.match(r"\w+\/\w+", string_tag):  # NS/key
            namespace, key = re.split(r"/", string_tag)
        elif re.match(r"\w+=\w+", string_tag):  # key=value
            key, value = re.split(r"=", string_tag)
        else:  # key
            key = string_tag

        return (namespace, key, value)

    def _create_nested(self, namespace, key, value):
        return {namespace: {key: [value]}}

    def from_string(self, string_tag):
        namespace, key, value = self._split_string_tag(string_tag)

        if namespace is not None:
            self.namespace = urllib.parse.unquote(namespace)
        self.key = urllib.parse.unquote(key)
        if value is not None:
            self.value = urllib.parse.unquote(value)

        return self

    def from_nested(self, nested_tag):
        namespace, key, value = None, None, None

        if len(nested_tag.keys()) > 1:
            raise ValueError("too many namespaces. Expecting 1")
        else:
            namespace = list(nested_tag.keys())[0]
            if len(nested_tag[namespace].keys()) > 1:
                raise ValueError("too many keys. Expecting 1")
            else:
                key = list(nested_tag[namespace].keys())[0]
                if len(nested_tag[namespace][key]) > 1:
                    raise ValueError("too many values. Expecting 1")
                else:
                    value = nested_tag[namespace][key][0]

        self.namespace = namespace
        self.key = key
        self.value = value

        return self

    def from_tag_data(self, tag_data):
        self.namespace = tag_data["namespace"]
        self.key = tag_data["key"]
        self.value = tag_data["value"]

        return self

    def to_string(self):
        namespace_string = ""
        key_string = ""
        value_string = ""

        if self.namespace is not None:
            namespace = urllib.parse.quote(self.namespace)
            namespace_string = f"{namespace}/"
        key_string = urllib.parse.quote(self.key)
        if self.value is not None:
            value = urllib.parse.quote(self.value)
            value_string = f"={value}"

        return f"{namespace_string}{key_string}{value_string}"

    def to_nested(self):
        return {self.namespace: {self.key: [self.value]}}

    @staticmethod
    def create_nested_from_tags(tags):
        """
        accepts an array of structured tags and makes a combined nested version
        of the tags
        """
        nested_tags = {}

        for tag in tags:
            if tag is None:
                raise TypeError(tag)
            elif tag.key is None or tag.namespace is None:
                raise TypeError(tag)
            namespace, key, value = tag.namespace, tag.key, tag.value
            if namespace in nested_tags:
                if value is None:
                    if key not in nested_tags[namespace]:
                        nested_tags[namespace][key] = []
                else:
                    if key in nested_tags[namespace]:
                        nested_tags[namespace][key].append(value)
                    else:
                        nested_tags[namespace][key] = [value]
            else:
                if value is None:
                    nested_tags[namespace] = {key: []}
                else:
                    nested_tags[namespace] = {key: [value]}

        return nested_tags

    @staticmethod
    def create_tags_from_nested(nested_tags):
        """
        takes a nesting of tags and returns an array of structured tags
        """
        tags = []
        for namespace in nested_tags:
            for key in nested_tags[namespace]:
                for value in nested_tags[namespace][key]:
                    tags.append(Tag(namespace, key, value))
        return tags

    @staticmethod
    def create_structered_tags_from_tag_data_list(tag_data_list):
        """
        takes an array of structured tag data and
        returns an array of tag class objects
        """
        tag_list = []

        if tag_data_list is None:
            return tag_list

        for tag_data in tag_data_list:
            tag_list.append(Tag(tag_data["namespace"], tag_data["key"], tag_data["value"]))

        return tag_list
