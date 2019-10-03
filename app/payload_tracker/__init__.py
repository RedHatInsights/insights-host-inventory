import abc
import json
from datetime import datetime

from kafka import KafkaProducer

from app.logging import get_logger
from app.payload_tracker import metrics

logger = get_logger(__name__)

_CFG = None
_PRODUCER = None
_UNKNOWN_PAYLOAD_ID = "-1"


def init_payload_tracker(config, producer=None):
    global _CFG
    global _PRODUCER

    _CFG = config

    if producer is not None:
        logger.info("Using injected producer object (%s) for PayloadTracker" % (producer))
        _PRODUCER = producer
    else:
        logger.info("Starting KafkaProducer() for PayloadTracker")
        _PRODUCER = KafkaProducer(bootstrap_servers=config.bootstrap_servers)


def get_payload_tracker(account=None, payload_id=None):

    if _CFG.payload_tracker_enabled is False or payload_id is None or payload_id == _UNKNOWN_PAYLOAD_ID:
        return NullPayloadTracker()

    payload_tracker = KafkaPayloadTracker(
        _PRODUCER, _CFG.payload_tracker_kafka_topic, _CFG.payload_tracker_service_name, account, payload_id
    )

    return payload_tracker


class PayloadTracker(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def payload_received(self, status_message=None):
        pass

    @abc.abstractmethod
    def payload_success(self, status_message=None):
        pass

    @abc.abstractmethod
    def payload_error(self, status_message=None):
        pass

    @abc.abstractmethod
    def processing(self, status_message=None):
        pass

    @abc.abstractmethod
    def processing_success(self, status_message=None):
        pass

    @abc.abstractmethod
    def processing_error(self, status_message=None):
        pass

    @property
    @abc.abstractmethod
    def inventory_id(self):
        pass

    @inventory_id.setter
    @abc.abstractmethod
    def inventory_id(self, inventory_id):
        pass


class NullPayloadTracker(PayloadTracker):
    def payload_received(self, status_message=None):
        pass

    def payload_success(self, status_message=None):
        pass

    def payload_error(self, status_message=None):
        pass

    def processing(self, status_message=None):
        pass

    def processing_success(self, status_message=None):
        pass

    def processing_error(self, status_message=None):
        pass

    def inventory_id(self):
        pass

    def inventory_id(self, inventory_id):  # noqa: F811
        pass


class KafkaPayloadTracker(PayloadTracker):
    def __init__(self, producer, topic, service_name, account, payload_id):
        self._producer = producer
        self._topic = topic
        self._service_name = service_name
        self._account = account
        self._payload_id = payload_id
        self._inventory_id = None

    def payload_received(self, status_message=None):
        message = self._construct_message("received", status_message=status_message)
        self._send_message(message)

    def payload_success(self, status_message=None):
        message = self._construct_message("success", status_message=status_message)
        self._send_message(message)

    def payload_error(self, status_message=None):
        message = self._construct_message("error", status_message=status_message)
        self._send_message(message)

    def processing(self, status_message=None):
        message = self._construct_message("processing", status_message=status_message)
        self._send_message(message)

    def processing_success(self, status_message=None):
        message = self._construct_message("processing_success", status_message=status_message)
        self._send_message(message)

    def processing_error(self, status_message=None):
        message = self._construct_message("processing_error", status_message=status_message)
        self._send_message(message)

    @property
    def inventory_id(self):
        return self._inventory_id

    @inventory_id.setter
    def inventory_id(self, inventory_id):
        self._inventory_id = inventory_id

    def _construct_message(self, status, status_message=None):
        try:

            if self._payload_id is None:
                logger.debug("payload_id is None...ignoring payload_tracker data")
                return None

            if status not in ["received", "success", "error", "processing", "processing_success", "processing_error"]:
                logger.debug(f"Invalid payload_tracker status ({status})...ignoring payload_tracker data")
                return None

            message = {
                "service": self._service_name,
                "payload_id": self._payload_id,
                "status": status,
                "date": datetime.utcnow().isoformat(),
            }

            if self._account:
                message["account"] = self._account

            if self.inventory_id:
                message["inventory_id"] = "%s" % (self.inventory_id)

            if status_message:
                message["status_msg"] = status_message

            json_message = json.dumps(message, sort_keys=True)

            return json_message
        except Exception:
            logger.exception("Error while constructing payload tracker message")
            metrics.payload_tracker_message_construction_failure.inc()
            return None

    def _send_message(self, message):
        if not message:
            return

        try:
            self._producer.send(self._topic, message.encode("utf-8"))
        except Exception:
            logger.exception("Error sending payload tracker message")
            metrics.payload_tracker_message_send_failure.inc()


class NullProducer:
    def send(self, topic, msg):
        print(f"sending message: {topic} - {msg}")


class PayloadTrackerContext:
    def __init__(
        self,
        payload_tracker=None,
        received_status_message=None,
        success_status_message=None,
        error_status_message=None,
    ):
        self._payload_tracker = payload_tracker
        self._received_status_msg = received_status_message
        self._success_status_msg = success_status_message
        self._error_status_msg = error_status_message

    def __enter__(self):
        self._payload_tracker.payload_received(status_message=self._received_status_msg)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self._payload_tracker.payload_error(status_message=self._error_status_msg)
        else:
            self._payload_tracker.payload_success(status_message=self._success_status_msg)


class PayloadTrackerProcessingContext:
    def __init__(
        self,
        payload_tracker=None,
        processing_status_message=None,
        success_status_message=None,
        error_status_message=None,
    ):
        self._payload_tracker = payload_tracker
        self._processing_status_msg = processing_status_message
        self._success_status_msg = success_status_message
        self._error_status_msg = error_status_message
        self._inventory_id = None

    def __enter__(self):
        self._payload_tracker.processing(status_message=self._processing_status_msg)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self._payload_tracker.processing_error(status_message=self._error_status_msg)
        else:
            self._payload_tracker.processing_success(status_message=self._success_status_msg)

        if self._inventory_id:
            self._payload_tracker.inventory_id = None

    @property
    def inventory_id(self):
        return self._inventory_id

    @inventory_id.setter
    def inventory_id(self, inventory_id):
        self._inventory_id = inventory_id
        self._payload_tracker.inventory_id = inventory_id
