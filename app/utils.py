import json
import re
import urllib

from app.exceptions import ValidationException
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
    def provider_id(self):
        return self.__data.get("provider_id")

    @provider_id.setter
    def provider_id(self, cf):
        self.__data["provider_id"] = cf

    @property
    def provider_type(self):
        return self.__data.get("provider_type")

    @provider_type.setter
    def provider_type(self, cf):
        self.__data["provider_type"] = cf

    @property
    def system_profile(self):
        return self.__data.get("system_profile", None)

    @system_profile.setter
    def system_profile(self, system_profile):
        self.__data["system_profile"] = system_profile

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
    def org_id(self):
        return self.__data.get("org_id", None)

    @org_id.setter
    def org_id(self, org_id):
        self.__data["org_id"] = org_id

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

    @property
    def stale_timestamp(self):
        return self.__data.get("stale_timestamp", None)

    @stale_timestamp.setter
    def stale_timestamp(self, stale_timestamp):
        self.__data["stale_timestamp"] = stale_timestamp

    @property
    def reporter(self):
        return self.__data.get("reporter", None)

    @reporter.setter
    def reporter(self, reporter):
        self.__data["reporter"] = reporter

    @property
    def created(self):
        return self.__data.get("created", None)

    @created.setter
    def created(self, created):
        self.__data["created"] = created

    @property
    def updated(self):
        return self.__data.get("updated", None)

    @updated.setter
    def updated(self, updated):
        self.__data["updated"] = updated

    @property
    def groups(self):
        return self.__data.get("groups")

    @groups.setter
    def groups(self, groups):
        self.__data["groups"] = groups

    def to_json(self):
        return json.dumps(self.__data)

    @classmethod
    def from_json(cls, d):
        return cls(json.loads(d))

    def __repr__(self):
        return f"HostWrapper({json.dumps(self.__data, indent=2)})"

    def __eq__(self, other):
        return self.__data == other.__data


"""
Tagging: functions for converting tags between valid representations
"""


class Tag:
    NULL_NAMESPACES = (None, "", "null")

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

    def _create_nested(self, namespace, key, value):
        return {namespace: {key: [value]}}

    def __eq__(self, other):
        return self.data() == other.data()

    @staticmethod
    def from_string(string_tag):
        match = re.match(r"((?P<namespace>[^=/]+)/)?(?P<key>[^=/]+)(=(?P<value>[^=/]+))?$", string_tag)
        encoded_tag_data = match.groupdict()
        decoded_tag_data = {}
        for k, v in encoded_tag_data.items():
            if v is None:
                decoded_tag_data[k] = None
            else:
                decoded_tag_data[k] = urllib.parse.unquote(v)
                if len(decoded_tag_data[k]) > 255:
                    raise ValidationException(f"{k} is longer than 255 characters")
        return Tag(**decoded_tag_data)

    @staticmethod
    def from_nested(nested_tag):
        if len(nested_tag.keys()) > 1:
            raise ValueError("too many namespaces. Expecting 1")

        namespace = list(nested_tag.keys())[0]
        if len(nested_tag[namespace].keys()) > 1:
            raise ValueError("too many keys. Expecting 1")

        key = list(nested_tag[namespace].keys())[0]
        if len(nested_tag[namespace][key]) > 1:
            raise ValueError("too many values. Expecting 1")

        if len(nested_tag[namespace][key]) == 1:
            value = nested_tag[namespace][key][0]
        else:
            value = None

        return Tag(namespace, key, value)

    def to_string(self):
        if self.namespace is None:
            namespace_string = ""
        else:
            namespace = urllib.parse.quote(self.namespace, safe="")
            namespace_string = f"{namespace}/"

        key_string = urllib.parse.quote(self.key, safe="")

        if self.value is None:
            value_string = ""
        else:
            value = urllib.parse.quote(self.value, safe="")
            value_string = f"={value}"

        return f"{namespace_string}{key_string}{value_string}"

    def to_nested(self):
        if self.namespace is None:
            raise ValueError("No namespace")

        if self.value is not None:
            return {self.namespace: {self.key: [self.value]}}

        return {self.namespace: {self.key: []}}

    @staticmethod
    def create_nested_from_tags(tags):
        """
        accepts an array of structured tags and makes a combined nested version
        of the tags
        """
        nested_tags = {}

        for tag in tags:
            if tag is None:
                raise TypeError("tag is none")
            elif tag.key is None:
                raise TypeError("tag is missing key")
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

    @classmethod
    def serialize_namespace(cls, value):
        """
        replaces the null string used in the database with None
        """
        return None if value in cls.NULL_NAMESPACES else value

    @classmethod
    def deserialize_namespace(cls, value):
        """
        replaces the null string used in the database with None
        """
        return "null" if value in cls.NULL_NAMESPACES else value

    @staticmethod
    def filter_tags(tags, searchTerm):
        """
        takes structured tags and returns an array of structured tags that are filtered by a searchterm
        """

        if searchTerm is None:
            return tags
        if tags is None:
            tags = {}

        filtered_tags = []

        for tag in tags:
            if any(filter(lambda x: x is not None and searchTerm in x, list(tag.values()))):
                filtered_tags.append(tag)

        return filtered_tags

    @staticmethod
    def create_tags_from_nested(nested_tags):
        """
        takes a nesting of tags and returns an array of structured tags
        """
        if nested_tags is None:
            nested_tags = {}

        tags = []
        for namespace in nested_tags:
            for key in nested_tags[namespace]:
                if len(nested_tags[namespace][key]) == 0:
                    tags.append(Tag(Tag.serialize_namespace(namespace), key))
                else:
                    for value in nested_tags[namespace][key]:
                        tags.append(Tag(Tag.serialize_namespace(namespace), key, value))
        return tags

    @staticmethod
    def create_flat_tags_from_structured(structured_tags):
        """
        takes a nesting of tags and returns an array of structured tags
        """
        if structured_tags is None:
            return []

        return [{"namespace": tag.namespace, "key": tag.key, "value": tag.value} for tag in structured_tags]
