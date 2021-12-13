import socket

from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import get_logger

logger = get_logger(__name__)


def _get_bootstrap_servers(kafka_socket, servers):
    if not servers:
        config = Config(RuntimeEnvironment.SERVICE)
        servers = [config.bootstrap_servers]

    try:
        for server in servers:
            try:
                host, port = server.split(":")
                new_addr = (host, int(port))
                may_be_errcode = kafka_socket.connect_ex(new_addr)
                if may_be_errcode == 0:
                    return True
            except ValueError as ve:
                logger.error(f"Invalid server address: {str(ve)}")
    except ValueError as ve:
        logger.error(f"No servers available: {str(ve)}")


def kafka_available(servers=None):
    kafka_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    kafka = _get_bootstrap_servers(kafka_socket, servers)
    kafka_socket.close()

    return kafka is True
