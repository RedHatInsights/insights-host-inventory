import logging

from api import api_operation, metrics
from app.auth import current_identity
from app.models import SearchSchema

from .host import build_paginated_host_list_response, get_host_list_by_id_list

logger = logging.getLogger(__name__)


@api_operation
@metrics.api_request_time.time()
def post(post_body, page=1, per_page=100):
    host_list_field_name = "host_id_list"
    validated_input = SearchSchema(strict=True).load(post_body)
    query = get_host_list_by_id_list(current_identity.account_number,
                                     validated_input.data[host_list_field_name])
    query_results = query.paginate(page, per_page, True)
    return build_paginated_host_list_response(
        query_results.total, page, per_page, query_results.items
    )
