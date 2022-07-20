import json
import sys
from functools import partial

from prometheus_client import CollectorRegistry
from prometheus_client import push_to_gateway
from requests import Session
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy.orm import sessionmaker

from api.metrics import outbound_http_response_time
from app import UNKNOWN_REQUEST_ID_VALUE
from app.config import Config
from app.environment import RuntimeEnvironment
from app.instrumentation import pendo_failure
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from lib.db import session_guard
from lib.handlers import register_shutdown
from lib.handlers import ShutdownHandler
from lib.metrics import pendo_fetching_failure


__all__ = ("main", "run")

PROMETHEUS_JOB = "inventory-pendo-syncher"
LOGGER_NAME = "inventory_pendo_syncher"
COLLECTED_METRICS = (pendo_fetching_failure,)
RUNTIME_ENVIRONMENT = RuntimeEnvironment.PENDO_JOB

PENDO_ROUTE = "/metadata/account/custom/value"
KEY_HEADER = "x-pendo-integration-key"
CONTENT_TYPE_HEADER = "content-type"
RETRY_STATUSES = [408, 500, 502, 503, 504]

outbound_http_metric = outbound_http_response_time.labels("pendo")


def _init_config():
    config = Config(RUNTIME_ENVIRONMENT)
    config.log_configuration()
    return config


def _init_db(config):
    engine = create_engine(config.db_uri)
    return sessionmaker(bind=engine)


def _prometheus_job(namespace):
    return f"{PROMETHEUS_JOB}-{namespace}" if namespace else PROMETHEUS_JOB


def _excepthook(logger, type, value, traceback):
    logger.exception("Pendo Syncher failed", exc_info=value)


def _process_response(pendo_response, logger):
    if pendo_response.status_code != 200:
        raise Exception(f"Pendo responded with status {pendo_response.status_code}")

    resp_data = pendo_response.json()

    logger.info(f"Total: {resp_data['total']} Updated: {resp_data['updated']}, Failed: {resp_data['failed']}")

    if resp_data.get("missing"):
        logger.debug("Some org IDs failed to sync.", extra={"sync_failed_accounts": resp_data["missing"]})


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


def _pendo_update(org_id_list, config, logger):
    request_body = []
    for org_id_info in org_id_list:
        org_id, host_count = org_id_info

        request_data = {"accountId": org_id, "values": {"hostCount": host_count}}
        request_body.append(request_data)

        logger.debug(f"Org ID: {org_id}, Host Count: {host_count}")
    request_body = json.dumps(request_body)
    if config.pendo_sync_active:
        _make_request(request_body, config, logger)


def pendo_sync(select_query, config, logger, interrupt=lambda: False):
    query = select_query.group_by(Host.org_id).order_by(Host.org_id)
    org_id_list = query.limit(config.pendo_request_size).all()

    while len(org_id_list) > 0 and not interrupt():
        _pendo_update(org_id_list, config, logger)
        org_id_list = query.filter(Host.org_id > org_id_list[-1].org_id).limit(config.pendo_request_size).all()


def run(config, logger, session, shutdown_handler):

    query = session.query(Host.org_id, func.count(Host.id))

    pendo_sync(query, config, logger, shutdown_handler.shut_down)
    logger.info("Pendo Syncher Run Complete.")


def main(logger):

    config = _init_config()
    registry = CollectorRegistry()

    for metric in COLLECTED_METRICS:
        registry.register(metric)

    job = _prometheus_job(config.kubernetes_namespace)
    prometheus_shutdown = partial(push_to_gateway, config.prometheus_pushgateway, job, registry)
    register_shutdown(prometheus_shutdown, "Pushing metrics")

    Session = _init_db(config)
    session = Session()
    register_shutdown(session.get_bind().dispose, "Closing database")

    shutdown_handler = ShutdownHandler()
    shutdown_handler.register()

    with session_guard(session):
        run(config, logger, session, shutdown_handler)


if __name__ == "__main__":
    configure_logging()

    logger = get_logger(LOGGER_NAME)
    sys.excepthook = partial(_excepthook, logger)

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    main(logger)
