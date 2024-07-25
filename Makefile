.PHONY: init test run_inv_mq_service

IDENTITY_HEADER="eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiYWNjb3VudDEyMyIsICJvcmdfaWQiOiAiNTg5NDMwMCIsICJ0eXBlIjogIlVzZXIiLCAidXNlciI6IHsiaXNfb3JnX2FkbWluIjogdHJ1ZSwgInVzZXJuYW1lIjogImZyZWQifSwgImludGVybmFsIjogeyJvcmdfaWQiOiAib3JnMTIzIn19fQ=="
NUM_HOSTS=1

init:
	pipenv shell

test:
	pytest --cov=.

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
	INVENTORY_LOG_LEVEL=DEBUG BYPASS_RBAC=true BYPASS_TENANT_TRANSLATION=true gunicorn -b :8080 run:app ${reload}

run_inv_mq_service:
	KAFKA_EVENT_TOPIC=platform.inventory.events PAYLOAD_TRACKER_SERVICE_NAME=inventory-mq-service INVENTORY_LOG_LEVEL=DEBUG BYPASS_TENANT_TRANSLATION=true python3 inv_mq_service.py

run_inv_export_service:
	KAFKA_EXPORT_SERVICE_TOPIC=platform.export.requests EXPORT_SERVICE_TOKEN=testing-a-psk python3 inv_export_service.py

run_inv_mq_service_test_producer:
	NUM_HOSTS=${NUM_HOSTS} python3 utils/kafka_producer.py

run_inv_mq_service_test_consumer:
	python3 utils/kafka_consumer.py

run_inv_http_test_producer:
	python3 utils/rest_producer.py

run_reaper:
	python3 host_reaper.py

run_pendo_syncher:
	python3 pendo_syncher.py

style:
	pre-commit run --all-files

scan_project:
	./sonarqube.sh

validate-dashboard:
	python3 utils/validate_dashboards.py


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

ifndef format
override format = json
endif

sample-request-create-export:
	@curl -sS -X POST http://localhost:8001/api/export/v1/exports -H "x-rh-identity: ${IDENTITY_HEADER}" -H "Content-Type: application/json" -d @example_${format}_export_request.json > response.json
	@cat response.json | jq
	@cat response.json | jq -r '.id' | xargs -I {} echo "EXPORT_ID: {}"
	@cat response.json | jq -r '.sources[] | "EXPORT_APPLICATION: \(.application)\nEXPORT_RESOURCE: \(.id)\n---"'
	@rm response.json

sample-request-get-exports:
	curl -X GET http://localhost:8001/api/export/v1/exports -H "x-rh-identity: ${IDENTITY_HEADER}" | jq

sample-request-export-download:
	curl -X GET http://localhost:8001/api/export/v1/exports/$(EXPORT_ID) -H "x-rh-identity: ${IDENTITY_HEADER}" -f --output ./export_download.zip
