import json

from requests import Session
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from api.metrics import outbound_http_response_time
from app.instrumentation import pendo_failure
from app.models import Host

__all__ = ("pendo_sync",)

PENDO_ROUTE = "/metadata/account/custom/value"
KEY_HEADER = "x-pendo-integration-key"
CONTENT_TYPE_HEADER = "content-type"
RETRY_STATUSES = [408, 500, 502, 503, 504]

outbound_http_metric = outbound_http_response_time.labels("pendo")


def _process_response(pendo_response, logger):
    if pendo_response.status_code != 200:
        raise Exception(f"Pendo responded with status {pendo_response.status_code}")

    resp_data = pendo_response.json()

    logger.info(
        f"Pendo Data Sent. Total: {resp_data['total']} Updated: {resp_data['updated']}, Failed, {resp_data['failed']}"
    )
    if resp_data.get("missing"):
        logger.debug("Some accounts failed to sync.", extra={"sync_failed_accounts": resp_data["missing"]})


def _make_request(request_body, config, logger):
    request_headers = {KEY_HEADER: config.pendo_integration_key, CONTENT_TYPE_HEADER: "application/json"}

    request_session = Session()
    retry_config = Retry(total=config.pendo_retries, backoff_factor=1, status_forcelist=RETRY_STATUSES)
    request_url = config.pendo_endpoint + PENDO_ROUTE

    request_session.mount(request_url, HTTPAdapter(max_retries=retry_config))

    try:
        with outbound_http_metric.time():
            pendo_response = request_session.post(
                url=request_url, headers=request_headers, data=request_body, timeout=config.pendo_timeout
            )
            _process_response(pendo_response, logger)
    except Exception as e:
        pendo_failure(logger, e)
    finally:
        request_session.close()


def _pendo_update(account_list, config, logger):
    request_body = []
    for account_info in account_list:
        account_number, host_count = account_info

        request_data = {"accountId": account_number, "values": {"hostCount": host_count}}
        request_body.append(request_data)

        logger.debug(f"Account Number: {account_number}, Host Count: {host_count}")
    request_body = json.dumps(request_body)
    if config.pendo_sync_active:
        _make_request(request_body, config, logger)


def pendo_sync(select_query, config, logger, interrupt=lambda: False):
    query = select_query.group_by(Host.account).order_by(Host.account)
    account_list = query.limit(config.pendo_request_size).all()

    while len(account_list) > 0 and not interrupt():
        _pendo_update(account_list, config, logger)
        account_list = query.filter(Host.account > account_list[-1].account).limit(config.pendo_request_size).all()
