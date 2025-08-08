# Targets to ensure quality of the codebase

.PHONY: test style scan_project validate-dashboard

IDENTITY_HEADER="eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiYWNjb3VudDEyMyIsICJvcmdfaWQiOiAiNTg5NDMwMCIsICJ0eXBlIjogIlVzZXIiLCAiYXV0aF90eXBlIjogImJhc2ljLWF1dGgiLCAidXNlciI6IHsiaXNfb3JnX2FkbWluIjogdHJ1ZSwgInVzZXJuYW1lIjogImZyZWQifSwgImludGVybmFsIjogeyJvcmdfaWQiOiAib3JnMTIzIn19fQ=="


test:
	pytest --cov=.

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


serve-docs:
	@echo "Serving docs at http://localhost:8080"
	@podman start kroki || podman run -d --name kroki -p 8000:8000 yuzutech/kroki
	@mkdocs serve -a localhost:8080
