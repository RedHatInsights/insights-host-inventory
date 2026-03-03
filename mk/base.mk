# Init the project and run it

.PHONY: init run_inv_mq_service

SCHEMA_VERSION ?= $(shell date '+%Y-%m-%d')
NUM_HOSTS=1


init:
	pipenv shell

migrate_db:
	SQLALCHEMY_ENGINE_LOG_LEVEL=INFO FLASK_APP=manage.py flask db migrate -m "${message}"

upgrade_db:
	SQLALCHEMY_ENGINE_LOG_LEVEL=INFO FLASK_APP=manage.py flask db upgrade


run_inv_web_service:
	# Set the "KAFKA_TOPIC", "KAFKA_GROUP", "KAFKA_BOOTSTRAP_SERVERS" environment variables
	# if you want the system_profile message queue consumer and event producer to be started
	#
	# KAFKA_TOPIC="platform.system-profile" KAFKA_GROUP="inventory" KAFKA_BOOTSTRAP_SERVERS="localhost:29092"
	#
	INVENTORY_LOG_LEVEL=DEBUG BYPASS_RBAC=true gunicorn -b :8080 run:app ${reload}

run_inv_mq_service:
	KAFKA_EVENT_TOPIC=platform.inventory.events PAYLOAD_TRACKER_SERVICE_NAME=inventory-mq-service INVENTORY_LOG_LEVEL=DEBUG python3 inv_mq_service.py

run_inv_export_service:
	KAFKA_EXPORT_SERVICE_TOPIC=platform.export.requests EXPORT_SERVICE_TOKEN=testing-a-psk python3 inv_export_service.py

run_inv_mq_service_test_producer:
	NUM_HOSTS=${NUM_HOSTS} python3 utils/kafka_producer.py

run_inv_mq_service_test_consumer:
	python3 utils/kafka_consumer.py

run_inv_http_test_producer:
	python3 utils/rest_producer.py

run_reaper:
	python3 jobs/host_reaper.py

run_pendo_syncher:
	python3 jobs/pendo_syncher.py

run_host_delete_access_tags:
	python3 jobs/delete_host_namespace_access_tags.py
