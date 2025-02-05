from atexit import register
from signal import SIGINT as CTRL_C_TERM
from signal import SIGTERM as OPENSHIFT_TERM
from signal import Signals
from signal import signal

from app.logging import get_logger

logger = get_logger(__name__)


class ShutdownHandler:
    def __init__(self):
        self._shutdown = False

    def _signal_handler(self, signum, frame):  # noqa: ARG002, required by signal
        signame = Signals(signum).name
        logger.info("Gracefully Shutting Down. Received: %s", signame)
        self._shutdown = True

    def register(self):
        signal(OPENSHIFT_TERM, self._signal_handler)
        signal(CTRL_C_TERM, self._signal_handler)

    def shut_down(self):
        return self._shutdown


def register_shutdown(function, message):
    def atexit_function():
        logger.info(message)
        function()

    register(atexit_function)
