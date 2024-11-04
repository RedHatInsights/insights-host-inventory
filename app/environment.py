from enum import Enum
from enum import auto

__all__ = ("RuntimeEnvironment",)


class RuntimeEnvironment(Enum):
    SERVER = auto()
    SERVICE = auto()
    JOB = auto()
    PENDO_JOB = auto()
    COMMAND = auto()
    TEST = auto()

    @property
    def logging_enabled(self):
        return self != self.TEST

    @property
    def event_producer_enabled(self):
        return self in (self.SERVER, self.JOB)

    @property
    def notification_producer_enabled(self):
        return self in (self.SERVER, self.JOB)

    @property
    def metrics_endpoint_enabled(self):
        return self == self.SERVER

    @property
    def metrics_pushgateway_enabled(self):
        return self in (self.JOB, self.PENDO_JOB)

    @property
    def payload_tracker_enabled(self):
        return self in (self.SERVER, self.SERVICE)
