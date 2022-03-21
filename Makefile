.PHONY: init test run_inv_mq_service

init:
	pipenv shell

test:
	pytest --cov=.

upgrade_db:
	SQLALCHEMY_ENGINE_LOG_LEVEL=INFO python manage.py db upgrade

run_inv_web_service:
	# Set the "KAFKA_TOPIC", "KAFKA_GROUP", "KAFKA_BOOTSTRAP_SERVERS" environment variables
	# if you want the system_profile message queue consumer and event producer to be started
	#
	# KAFKA_TOPIC="platform.system-profile" KAFKA_GROUP="inventory" KAFKA_BOOTSTRAP_SERVERS="localhost:29092"
	#
	INVENTORY_LOG_LEVEL=DEBUG BYPASS_RBAC=true gunicorn -b :8080 run

run_inv_mq_service:
	KAFKA_EVENT_TOPIC=platform.inventory.events PAYLOAD_TRACKER_SERVICE_NAME=inventory-mq-service INVENTORY_LOG_LEVEL=DEBUG python inv_mq_service.py

run_inv_mq_service_test_producer:
	python utils/kafka_producer.py

run_inv_mq_service_test_consumer:
	python utils/kafka_consumer.py

run_inv_http_test_producer:
	python utils/rest_producer.py

run_reaper:
	python host_reaper.py

run_pendo_syncher:
	python pendo_syncher.py

style:
	pre-commit run --all-files

scan_project:
	./sonarqube.sh

validate-dashboard:
	python utils/validate_dashboards.py


update-schema:
	[ -d swagger/inventory-schemas ] || git clone git@github.com:RedHatInsights/inventory-schemas.git swagger/inventory-schemas
	(cd swagger/inventory-schemas && git pull)
	cp \
	    swagger/inventory-schemas/schemas/system_profile/v1.yaml \
	    swagger/system_profile.spec.yaml
	( cd swagger/inventory-schemas; set +e;git rev-parse HEAD) > swagger/system_profile_commit_id
	git add swagger/system_profile.spec.yaml
	git add swagger/system_profile_commit_id
	git diff --cached
