from signal import Signals
from app.logging import get_logger

logger = get_logger(__name__)

class ShutdownHandler:
    def __init__(self):
        self._shutdown = False

    def signal_handler(self, signum, frame):
        signame = Signals(signum).name
        logger.info("Gracefully Shutting Down. Received: %s", signame)
        self._shutdown = True

    def shut_down(self):
        return self._shutdown

