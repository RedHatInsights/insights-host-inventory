from signal import SIGINT as CTRL_C_TERM
from signal import signal
from signal import Signals
from signal import SIGTERM as OPENSHIFT_TERM

from app.logging import get_logger

logger = get_logger(__name__)


class ShutdownHandler:
    def __init__(self):
        self._shutdown = False

    def _signal_handler(self, signum, frame):
        signame = Signals(signum).name
        logger.info("Gracefully Shutting Down. Received: %s", signame)
        self._shutdown = True

    def register(self):
        signal(OPENSHIFT_TERM, self._signal_handler)
        signal(CTRL_C_TERM, self._signal_handler)

    def shut_down(self):
        return self._shutdown
