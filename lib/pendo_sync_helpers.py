
from app.models import Host
import json
from requests import Session
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

__all__ = ("pendo_sync",)


def _make_request(request_body, config):
    pass

def _pendo_update(account_list, logger, config):
    '''
    TODO Serialize and send Data to Pendo
    '''
    request_body = []
    for account_info in account_list:
        account_number, host_count = account_info

        request_data = {"accountId": account_number, "values": {"hostCount": host_count}}
        request_body.append(request_data)

        logger.info(f"Account Number: {account_number}, Host Count: {host_count}")
    request_body = json.dumps(request_body)

def pendo_sync(select_query, limit, config, logger, interrupt=lambda: False):
    query = select_query.group_by(Host.account).order_by(Host.account)
    account_list = query.limit(limit).all()

    update_count = 0
    while len(account_list) > 0 and not interrupt():
        _pendo_update(account_list, logger, config)
        account_list = query.filter(Host.account > account_list[-1].account).limit(limit).all()
    logger.info(f"Accounts updated: {update_count}")