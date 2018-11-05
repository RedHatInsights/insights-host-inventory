import json


class HostWrapper:

    def __init__(self, data={}):
        self.__data = data

    def data(self):
        return self.__data

    def __delattr__(self, name):
        if name in self.__data:
            del self.__data[name]
        else:
            raise AttributeError("No such attribute: " + name)

    CANONICAL_FACTS = ("insights-id",
                       "rhel-machine-id",
                       "subscription-manager-id",
                       "satellite-id",
                       "bios-uuid",
                       "ip-addresses",
                       "fqdn",
                       "mac-addresses")

    @property
    def insights_id(self):
        return self.__data["insights-id"]

    @insights_id.setter
    def insights_id(self, cf):
        self.__data["insights-id"] = cf

    @property
    def rhel_machine_id(self):
        return self.__data["rhel-machine-id"]

    @rhel_machine_id.setter
    def rhel_machine_id(self, cf):
        self.__data["rhel-machine-id"] = cf

    @property
    def subscription_manager_id(self):
        return self.__data["subscription-manager-id"]

    @subscription_manager_id.setter
    def subscription_manager_id(self, cf):
        self.__data["subscription-manager-id"] = cf

    @property
    def bios_uuid(self):
        return self.__data["bios-uuid"]

    @bios_uuid.setter
    def bios_uuid(self, cf):
        self.__data["bios-uuid"] = cf

    @property
    def ip_addresses(self):
        return self.__data["ip-addresses"]

    @ip_addresses.setter
    def ip_addresses(self, cf):
        self.__data["ip-addresses"] = cf

    @property
    def fqdn(self):
        return self.__data["fqdn"]

    @fqdn.setter
    def fqdn(self, cf):
        self.__data["fqdn"] = cf

    @property
    def mac_addresses(self):
        return self.__data["mac-addresses"]

    @mac_addresses.setter
    def mac_addresses(self, cf):
        self.__data["mac-addresses"] = cf

    @property
    def facts(self):
        return self.__data["facts"]

    @facts.setter
    def facts(self, facts):
        self.__data["facts"] = facts

    @property
    def tags(self):
        return self.__data["tags"]

    @tags.setter
    def tags(self, tags):
        self.__data["tags"] = tags

    @property
    def id(self):
        return self.__data["id"]

    @id.setter
    def id(self, id):
        self.__data["id"] = id

    @property
    def account(self):
        return self.__data["account"]

    @account.setter
    def account(self, account):
        self.__data["account"] = account

    @property
    def display_name(self):
        return self.__data["display_name"]

    @display_name.setter
    def display_name(self, display_name):
        self.__data["display_name"] = display_name

    def to_json(self):
        return json.dumps(self.__data)

    @classmethod
    def from_json(cls, d):
        return cls(json.loads(d))
