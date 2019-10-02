.PHONY: init test run_inv_mq_service

init:
	pipenv shell

test:
	pytest --cov=.

upgrade_db:
	python manage.py db upgrade

run_inv_web_service:
	# Set the "KAFKA_TOPIC", "KAFKA_GROUP", "KAFKA_BOOTSTRAP_SERVERS" environment variables
	# if you want the system_profile message queue consumer and event producer to be started
	#
	# KAFKA_TOPIC="platform.system-profile" KAFKA_GROUP="inventory" KAFKA_BOOTSTRAP_SERVERS="localhost:29092"
	#
	INVENTORY_LOGGING_CONFIG_FILE=logconfig.ini INVENTORY_LOG_LEVEL=DEBUG gunicorn -b :8080 run

run_inv_mq_service:
	PAYLOAD_TRACKER_SERVICE_NAME=inventory-mq-service INVENTORY_LOGGING_CONFIG_FILE=logconfig.ini \
	INVENTORY_LOG_LEVEL=DEBUG python inv_mq_service.py

run_inv_mq_service_test_producer:
	KAFKA_GROUP="inventory-mq" KAFKA_TOPIC="platform.inventory.host-ingress" python utils/kafka_producer.py

run_inv_mq_service_test_consumer:
	KAFKA_GROUP="inventory-mq" KAFKA_TOPIC="platform.inventory.host-egress" python utils/kafka_consumer.py

run_inv_http_test_producer:
	python utils/rest_producer.py
