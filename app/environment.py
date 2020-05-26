from enum import auto
from enum import Enum

__all__ = ("RuntimeEnvironment",)


class RuntimeEnvironment(Enum):
    SERVER = auto()
    SERVICE = auto()
    JOB = auto()
    COMMAND = auto()
    TEST = auto()

    @property
    def logging_enabled(self):
        return self != self.TEST

    @property
    def event_producer_enabled(self):
        return self in (self.SERVER, self.JOB)

    @property
    def metrics_endpoint_enabled(self):
        return self == self.SERVER

    @property
    def metrics_pushgateway_enabled(self):
        return self == self.JOB

    @property
    def payload_tracker_enabled(self):
        return self in (self.SERVER, self.SERVICE)
