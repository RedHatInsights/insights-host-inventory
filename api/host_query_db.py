from app.auth import get_current_identity
from app.instrumentation import log_get_host_list_succeeded
from app.logging import get_logger
from app.models import Host
from lib.host_repository import get_host_list_by_id_list_from_db
from lib.host_repository import update_query_for_owner_id

__all__ = ("get_all_hosts", "params_to_order_by")

NULL = None

logger = get_logger(__name__)


def get_all_hosts():
    query = _find_all_hosts()
    query_results = query.all()
    ids_list = [str(host.id) for host in query_results]

    log_get_host_list_succeeded(logger, ids_list)
    return ids_list


def params_to_order_by(order_by=None, order_how=None):
    modified_on_ordering = (Host.modified_on.desc(),)
    ordering = ()

    if order_by == "updated":
        if order_how:
            modified_on_ordering = (_order_how(Host.modified_on, order_how),)
    elif order_by == "display_name":
        if order_how:
            ordering = (_order_how(Host.display_name, order_how),)
        else:
            ordering = (Host.display_name.asc(),)
    elif order_by:
        raise ValueError('Unsupported ordering column, use "updated" or "display_name".')
    elif order_how:
        raise ValueError(
            "Providing ordering direction without a column is not supported. "
            "Provide order_by={updated,display_name}."
        )

    return ordering + modified_on_ordering + (Host.id.desc(),)


def _order_how(column, order_how):
    if order_how == "ASC":
        return column.asc()
    elif order_how == "DESC":
        return column.desc()
    else:
        raise ValueError('Unsupported ordering direction, use "ASC" or "DESC".')


def _find_all_hosts():
    identity = get_current_identity()
    query = Host.query.filter(Host.org_id == identity.org_id)
    return update_query_for_owner_id(identity, query)


def get_host_tags_list_by_id_list(host_id_list, page, per_page, order_by, order_how, rbac_filter):
    columns = [Host.id, Host.tags]
    query = get_host_list_by_id_list_from_db(host_id_list, rbac_filter, columns)
    order = params_to_order_by(order_by, order_how)
    query_results = query.order_by(*order).offset((page - 1) * per_page).limit(per_page).all()
    host_tags_dict = _expand_host_tags(query_results)
    return host_tags_dict, len(host_id_list)


def _expand_host_tags(hosts):
    host_tags_dict = {}
    for host in hosts:
        host_tags = []
        host_namespace_tags_dict = host.tags
        for host_namespace, host_namespace_tags in host_namespace_tags_dict.items():
            for tag_key, tag_values in host_namespace_tags.items():
                for tag_value in tag_values:
                    host_tag_obj = {"namespace": host_namespace, "key": tag_key, "value": tag_value}
                    host_tags.append(host_tag_obj)
        host_tags_dict[host.id] = host_tags
    return host_tags_dict
