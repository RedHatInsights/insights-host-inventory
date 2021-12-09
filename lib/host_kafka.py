import socket

from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import get_logger

logger = get_logger(__name__)


def _check_connection(kafka_socket, server):
    conn_check = 999
    try:
        host, port = server.split(":")
        nw_addr = (host, int(port))
        conn_check = kafka_socket.connect_ex(nw_addr)
    except ValueError as ve:
        logger.error(f"Invalid server address: {str(ve)}")
    return conn_check


def _get_bootstrap_servers(servers):
    if not servers:
        config = Config(RuntimeEnvironment.SERVICE)
        servers = config.bootstrap_servers
    return servers


def kafka_available(servers=None):
    # random bad value. Set to zero by successful connection attempt
    kafka_check = 999

    kafkas = _get_bootstrap_servers(servers)
    kafka_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if isinstance(kafkas, str):
        kafka_check = _check_connection(kafka_socket, kafkas)
    elif isinstance(kafkas, list):
        for server in kafkas:
            kafka_check = _check_connection(kafka_socket, server)
            if kafka_check == 0:
                # finding one is enough
                break
    else:
        logger.error("Bad kafka broker address")

    kafka_socket.close()

    return kafka_check == 0
