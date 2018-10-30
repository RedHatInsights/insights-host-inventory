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

    @property
    def canonical_facts(self):
        return self.__data["canonical_facts"]
    @canonical_facts.setter
    def canonical_facts(self, cf):
        self.__data["canonical_facts"] = cf

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
