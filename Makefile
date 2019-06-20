.PHONY: init test run_inv_mq_service

init:
	pipenv shell

test:
	pytest --cov=.

upgrade_db:
	python manage.py db upgrade

run_inv_mq_service:
	INVENTORY_LOGGING_CONFIG_FILE=logconfig.ini INVENTORY_LOG_LEVEL=DEBUG python inv_mq_service.py

run_inv_mq_service_test:
	KAFKA_TOPIC="platform.host-ingress" python utils/kafka_producer.py
