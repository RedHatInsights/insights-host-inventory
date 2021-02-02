def custom_fields_parser(root_key, key_path, val):
    """ consumes keys, value pairs like (a[foo], "baz,hello")
        returns (a, {"foo": {"baz": True, "hello": True}}}, is_deep_object)
    """
    root = {key_path[0]: {}}
    for v in val:
        for fields in v.split(","):
            root[key_path[0]][fields] = True
    return (root_key, [root], True)
