
# Default value for BASE_IMAGE
BASE_IMAGE ?= registry.access.redhat.com/ubi9/ubi-minimal:latest
# Default value for CONTAINERFILE
CONTAINERFILE ?= Dockerfile

hermetic_builds_dir = .hermetic_builds
hermetic_builds_path = $(project_dir)/$(hermetic_builds_dir)

.PHONY: generate-hermetic-lockfiles
generate-hermetic-lockfiles: generate-rpms-lockfile generate-requirements-txt generate-requirements-build-txt

# Generate rpms.in.yaml listing RPM packages installed via yum, dnf, or microdnf from CONTAINERFILE
# Usage: make generate-rpms-lockfile [CONTAINERFILE=<path>] [BASE_IMAGE=<image>|local]
#   BASE_IMAGE can be set to 'local' to use the local system's repositories instead of a container image.
#     It then assumes you're running in the context of the base image already (e.g., in a UBI 9).
# Example: make generate-rpms-lockfile CONTAINERFILE=Containerfile BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest
#          make generate-rpms-lockfile (uses default CONTAINERFILE=Dockerfile and BASE_IMAGE=registry.access.redhat.com/ubi9/ubi-minimal:latest)
.PHONY: generate-rpms-lockfile
generate-rpms-lockfile: $(hermetic_builds_dir)/rpms.lock.yaml

$(hermetic_builds_dir)/ubi.repo:
	@if ! grep -q "Red Hat Enterprise Linux release 9" /etc/redhat-release 2>/dev/null; then \
		echo "Error: This system is not running RHEL 9"; \
		exit 1; \
	fi
	@if [ "$(BASE_IMAGE)" = "local" ]; then \
		cp /etc/yum.repos.d/ubi.repo $(hermetic_builds_path)/ubi.repo || { echo "Failed to fetch ubi.repo"; exit 1; }; \
	else \
		podman run -it $(BASE_IMAGE) cat /etc/yum.repos.d/ubi.repo > $(hermetic_builds_path)/ubi.repo || { echo "Failed to fetch ubi.repo"; exit 1; }; \
	fi
	@sed -i 's/ubi-9-appstream-source-rpms/ubi-9-for-x86_64-appstream-source-rpms/' $(hermetic_builds_path)/ubi.repo
	@sed -i 's/ubi-9-appstream-rpms/ubi-9-for-x86_64-appstream-rpms/' $(hermetic_builds_path)/ubi.repo
	@sed -i 's/ubi-9-baseos-source-rpms/ubi-9-for-x86_64-baseos-source-rpms/' $(hermetic_builds_path)/ubi.repo
	@sed -i 's/ubi-9-baseos-rpms/ubi-9-for-x86_64-baseos-rpms/' $(hermetic_builds_path)/ubi.repo
	@sed -i 's/\r$$//' $(hermetic_builds_path)/ubi.repo
	@sed -i '/\[.*x86_64.*\]/,/^\[/ s/enabled[[:space:]]*=[[:space:]]*0/enabled = 1/g' $(hermetic_builds_path)/ubi.repo
	@ENTITLEMENT_KEY=$$(ls /etc/pki/entitlement/*-key.pem 2>/dev/null | head -n 1); \
	ENTITLEMENT_CERT=$$(ls /etc/pki/entitlement/*.pem 2>/dev/null | grep -v -- '-key.pem' | head -n 1); \
	if [ -z "$$ENTITLEMENT_KEY" ] || [ -z "$$ENTITLEMENT_CERT" ]; then \
		echo "Error: Entitlement key or certificate not found in /etc/pki/entitlement"; \
		exit 1; \
	fi; \
	$(hermetic_builds_path)/generate_repo_config.sh "rhel-9-for-x86_64-baseos-rpms" \
		'Red Hat Enterprise Linux 9 for x86_64 - BaseOS (RPMs)' \
		'https://cdn.redhat.com/content/dist/rhel9/9/$$basearch/baseos/os' \
		"$$ENTITLEMENT_KEY" "$$ENTITLEMENT_CERT" >> $(hermetic_builds_path)/ubi.repo; \
	$(hermetic_builds_path)/generate_repo_config.sh "rhel-9-for-x86_64-baseos-source-rpms" \
		'Red Hat Enterprise Linux 9 for x86_64 - BaseOS (RPMs)' \
		'https://cdn.redhat.com/content/dist/rhel9/9/$$basearch/baseos/source/SRPMS' \
		"$$ENTITLEMENT_KEY" "$$ENTITLEMENT_CERT" >> $(hermetic_builds_path)/ubi.repo; \
	$(hermetic_builds_path)/generate_repo_config.sh "rhel-9-for-x86_64-appstream-rpms" \
		'Red Hat Enterprise Linux 9 for x86_64 - AppStream (RPMs)' \
		'https://cdn.redhat.com/content/dist/rhel9/9/$$basearch/appstream/os' \
		"$$ENTITLEMENT_KEY" "$$ENTITLEMENT_CERT" >> $(hermetic_builds_path)/ubi.repo; \
	$(hermetic_builds_path)/generate_repo_config.sh "rhel-9-for-x86_64-appstream-source-rpms" \
		'Red Hat Enterprise Linux 9 for x86_64 - AppStream (RPMs)' \
		'https://cdn.redhat.com/content/dist/rhel9/9/$$basearch/appstream/source/SRPMS' \
		"$$ENTITLEMENT_KEY" "$$ENTITLEMENT_CERT" >> $(hermetic_builds_path)/ubi.repo;


$(hermetic_builds_dir)/rpms.in.yaml: $(CONTAINERFILE) $(hermetic_builds_dir)/ubi.repo
	@if ! command -v $(AWK) >/dev/null 2>&1; then \
		echo "Error: AWK command not found"; \
		exit 1; \
	fi;
	@echo "Generating rpms.in.yaml from $(CONTAINERFILE)..."; \
	packages=$$(grep -E '^(RUN[[:space:]]+)?(.*[[:space:]]*(yum|dnf|microdnf)[[:space:]]+.*install.*)' "$(CONTAINERFILE)" | \
		sed -E 's/\\$$//' | \
		$(AWK) '{ \
			start=0; \
			for (i=1; i<=NF; i++) { \
				if ($$i == "install") { start=1; continue } \
				if (start && $$i ~ /^[a-zA-Z0-9][a-zA-Z0-9_.+-]*$$/ && \
					$$i !~ /^-/ && $$i != "&&" && $$i != "clean" && $$i != "all" && $$i != "upgrade") { \
					print $$i \
				} \
				if ($$i == "&&") { start=0 } \
			} \
		}' | sort -u); \
	if [ -z "$$packages" ]; then \
		exit 1; \
	else \
		echo "packages: [$$(echo "$$packages" | tr '\n' ',' | sed -E 's/,/, /g; s/, $$//')]" > $@; \
		echo "contentOrigin:" >> $@; \
		echo "  repofiles: [\"./ubi.repo\"]" >> $@; \
		echo "moduleEnable: [\"postgresql:16\"]" >> $@; \
		echo "arches: [x86_64]" >> $@; \
	fi

# Generate rpms.lock.yaml using rpm-lockfile-prototype
# Usage: make .hermetic_builds/rpms.lock.yaml [BASE_IMAGE=<image>]
# Example: make .hermetic_builds/rpms.lock.yaml BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest
#          make .hermetic_builds/rpms.lock.yaml (uses default BASE_IMAGE)
$(hermetic_builds_dir)/rpms.lock.yaml: $(hermetic_builds_dir)/rpms.in.yaml
	@if [ ! command -v rpm-lockfile-prototype >/dev/null 2>&1 ]; then \
		echo "Error: Command rpm-lockfile-prototype not found"; \
		echo "Please install it using 'python3 -m pip install --user https://github.com/konflux-ci/rpm-lockfile-prototype/archive/refs/heads/main.zip'"; \
		echo "See https://github.com/konflux-ci/rpm-lockfile-prototype/?tab=readme-ov-file#running-in-a-container for usage in a container"; \
		exit 1; \
	fi;
	@rpm-lockfile-prototype --image $(BASE_IMAGE) --outfile=$@ $<
	@if [ ! -f $(hermetic_builds_dir)/rpms.lock.yaml ]; then \
		echo "Error: rpms.lock.yaml was not generated"; \
		exit 1; \
	fi

# Generate requirements.txt from Poetry or Pipenv lock files
.PHONY: generate-requirements-txt
generate-requirements-txt: $(hermetic_builds_dir)/requirements.txt

$(hermetic_builds_dir)/requirements.txt: Pipfile.lock
	@if [ -f poetry.lock ]; then \
		poetry export --format requirements.txt --output $(hermetic_builds_dir)/requirements.txt; \
	elif [ -f Pipfile.lock ]; then \
		pipenv requirements > $(hermetic_builds_dir)/requirements.txt; \
	elif [ -f requirements.txt ]; then \
		cp requirements.txt $(hermetic_builds_dir)/requirements.txt; \
		exit 0; \
	else \
		echo "Error: Unable to generate requirements.txt file"; \
		exit 1; \
	fi
	@if [ ! -f $(hermetic_builds_dir)/requirements.txt ]; then \
		echo "Error: requirements.txt was not generated"; \
		exit 1; \
	fi

# Generate requirements-build.in from [build-system] in pyproject.toml
# Truncates existing requirements-build.in and requirements-extras.in files first
# Adds extras through add_manual_build_dependencies.sh script
# Usage: make generate-requirements-build-in
# Example: make generate-requirements-build-in
.PHONY: generate-requirements-build-in
generate-requirements-build-in: pyproject.toml
	@> $(hermetic_builds_path)/requirements-build.in
	@> $(hermetic_builds_path)/requirements-extras.in

	@if ! grep -q '^\[build-system\]' pyproject.toml; then \
		exit 0; \
	fi
	@requires=$$(sed -n '/^\[build-system\]/,/^\[/p' pyproject.toml | \
	grep 'requires[[:space:]]*=' | \
	sed 's/.*requires[[:space:]]*=[[:space:]]*\[\(.*\)\]/\1/' | \
	sed 's/"//g; s/,[[:space:]]*/\n/g' | \
	sed 's/^[[:space:]]*//; s/[[:space:]]*$$//; /^$$/d'); \
	if [ -z "$$requires" ]; then \
		exit 0; \
	fi; \
	for pkg in $$requires; do \
		if echo "$$pkg" | grep -q "=="; then \
			echo "$$pkg" >> $(hermetic_builds_path)/requirements-build.in; \
		else \
			version=$$(curl -s "https://pypi.org/pypi/$$pkg/json" | \
			sed -n 's/.*"version":[[:space:]]*"\([^"]*\)".*/\1/p' | head -1); \
			if [ -z "$$version" ]; then \
				echo "Error: Failed to fetch version for $$pkg from PyPI"; \
				exit 1; \
			fi; \
			echo "$$pkg==$$version" >> $(hermetic_builds_path)/requirements-build.in; \
		fi; \
	done
	@if [ ! -f $(hermetic_builds_path)/add_manual_build_dependencies.sh ]; then \
		echo "Error: Missing scripts in $(hermetic_builds_path) directory"; \
		exit 1; \
	fi
	$(hermetic_builds_path)/add_manual_build_dependencies.sh $(hermetic_builds_path)
	@if [ ! -f $(hermetic_builds_path)/requirements-build.in ]; then \
		echo "Error: requirements-build.in was not generated"; \
		exit 1; \
	fi

# Generate build dependencies requirements-build.txt using pip-tools and pybuild-deps
# Usage: make generate-requirements-build-txt [BASE_IMAGE=<image>]
# Example: make generate-requirements-build-txt BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest
.PHONY: generate-requirements-build-txt
generate-requirements-build-txt: generate-requirements-build-in
	@if [ ! -f $(hermetic_builds_path)/prep_python_build_container_dependencies.sh ] || [ ! -f $(hermetic_builds_path)/generate_requirements_build.sh ]; then \
		echo "Error: Missing scripts in $(hermetic_builds_dir) directory"; \
		exit 1; \
	fi
	@if [ "$(BASE_IMAGE)" = "local" ]; then \
		$(hermetic_builds_path)/generate_requirements_build.sh; \
	else \
		podman run -it -v "$(hermetic_builds_path)":/project:Z --user 0:0 -w /project $(BASE_IMAGE) bash -c "/project/prep_python_build_container_dependencies.sh && /project/generate_requirements_build.sh"; \
	fi
	@if [ ! -f $(hermetic_builds_path)/requirements-build.txt ]; then \
		echo "Error: requirements-build.txt was not generated"; \
		exit 1; \
	fi
