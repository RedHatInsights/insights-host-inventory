mq: KAFKA_EVENT_TOPIC=platform.inventory.events PAYLOAD_TRACKER_SERVICE_NAME=inventory-mq-service INVENTORY_LOG_LEVEL=DEBUG python inv_mq_service.py
web: INVENTORY_LOG_LEVEL=DEBUG gunicorn -b :8080 run
