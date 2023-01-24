def get_group_list(
    group_name=None,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
    staleness=None,
):
    pass


def create_group(body):
    pass


def get_group(group_id):
    pass


def patch_group_by_id(group_id, body):
    pass


def update_group_details(group_id, body):
    pass


def delete_group(group_id):
    pass


def get_groups_by_id(group_id_list):
    pass


def delete_hosts_from_group(group_id, host_id_list):
    pass
