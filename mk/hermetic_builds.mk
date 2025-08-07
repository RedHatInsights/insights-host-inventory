
# Default value for BASE_IMAGE
BASE_IMAGE ?= registry.access.redhat.com/ubi9/ubi-minimal:latest
# Default value for CONTAINERFILE
CONTAINERFILE ?= Dockerfile

# Generate the ubi.repo file from the specified BASE_IMAGE
# Usage: make generate-repo-file [BASE_IMAGE=<image>]
# Example: make generate-repo-file BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest
#          make generate-repo-file (uses default BASE_IMAGE)
.PHONY: generate-repo-file
generate-repo-file:
	@if ! grep -q "Red Hat Enterprise Linux release 9" /etc/redhat-release 2>/dev/null; then \
		echo "Error: This system is not running RHEL 9"; \
		exit 1; \
	fi
	@podman run -it $(BASE_IMAGE) cat /etc/yum.repos.d/ubi.repo > ubi.repo || { echo "Failed to fetch ubi.repo"; exit 1; }
	@sed -i 's/ubi-9-appstream-source-rpms/ubi-9-for-x86_64-appstream-source-rpms/' ubi.repo
	@sed -i 's/ubi-9-appstream-rpms/ubi-9-for-x86_64-appstream-rpms/' ubi.repo
	@sed -i 's/ubi-9-baseos-source-rpms/ubi-9-for-x86_64-baseos-source-rpms/' ubi.repo
	@sed -i 's/ubi-9-baseos-rpms/ubi-9-for-x86_64-baseos-rpms/' ubi.repo
	@sed -i 's/\r$$//' ubi.repo
	@sed -i '/\[.*x86_64.*\]/,/^\[/ s/enabled[[:space:]]*=[[:space:]]*0/enabled = 1/g' ubi.repo
	@ENTITLEMENT_KEY=$$(ls /etc/pki/entitlement/*-key.pem 2>/dev/null | head -n 1); \
	ENTITLEMENT_CERT=$$(ls /etc/pki/entitlement/*.pem 2>/dev/null | grep -v -- '-key.pem' | head -n 1); \
	if [ -z "$$ENTITLEMENT_KEY" ] || [ -z "$$ENTITLEMENT_CERT" ]; then \
		echo "Error: Entitlement key or certificate not found in /etc/pki/entitlement"; \
		exit 1; \
	fi; \
	$(MAKE) append-repo-config REPO_NAME="rhel-9-for-x86_64-baseos-rpms" \
		REPO_DESC="Red Hat Enterprise Linux 9 for x86_64 - BaseOS (RPMs)" \
		REPO_URL="https://cdn.redhat.com/content/dist/rhel9/9/\$$basearch/baseos/os" \
		ENTITLEMENT_KEY="$$ENTITLEMENT_KEY" \
		ENTITLEMENT_CERT="$$ENTITLEMENT_CERT"; \
	$(MAKE) append-repo-config REPO_NAME="rhel-9-for-x86_64-baseos-source-rpms" \
		REPO_DESC="Red Hat Enterprise Linux 9 for x86_64 - BaseOS (RPMs)" \
		REPO_URL="https://cdn.redhat.com/content/dist/rhel9/9/\$$basearch/baseos/source/SRPMS" \
		ENTITLEMENT_KEY="$$ENTITLEMENT_KEY" \
		ENTITLEMENT_CERT="$$ENTITLEMENT_CERT"; \
	$(MAKE) append-repo-config REPO_NAME="rhel-9-for-x86_64-appstream-rpms" \
		REPO_DESC="Red Hat Enterprise Linux 9 for x86_64 - AppStream (RPMs)" \
		REPO_URL="https://cdn.redhat.com/content/dist/rhel9/9/\$$basearch/appstream/os" \
		ENTITLEMENT_KEY="$$ENTITLEMENT_KEY" \
		ENTITLEMENT_CERT="$$ENTITLEMENT_CERT"; \
	$(MAKE) append-repo-config REPO_NAME="rhel-9-for-x86_64-appstream-source-rpms" \
		REPO_DESC="Red Hat Enterprise Linux 9 for x86_64 - AppStream (RPMs)" \
		REPO_URL="https://cdn.redhat.com/content/dist/rhel9/9/\$$basearch/appstream/source/SRPMS" \
		ENTITLEMENT_KEY="$$ENTITLEMENT_KEY" \
		ENTITLEMENT_CERT="$$ENTITLEMENT_CERT"

# Append common repository configuration to ubi.repo
# Usage: make append-repo-config REPO_NAME=<name> REPO_DESC=<description> REPO_URL=<url> ENTITLEMENT_KEY=<key> ENTITLEMENT_CERT=<cert>
.PHONY: append-repo-config
append-repo-config:
	@echo "" >> ubi.repo
	@echo "[$(REPO_NAME)]" >> ubi.repo
	@echo "name = $(REPO_DESC)" >> ubi.repo
	@echo "baseurl = $(REPO_URL)" >> ubi.repo
	@echo "enabled = 1" >> ubi.repo
	@echo "gpgkey = file:///etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release" >> ubi.repo
	@echo "gpgcheck = 1" >> ubi.repo
	@echo "sslverify = 1" >> ubi.repo
	@echo "sslcacert = /etc/rhsm/ca/redhat-uep.pem" >> ubi.repo
	@echo "sslclientkey = $(ENTITLEMENT_KEY)" >> ubi.repo
	@echo "sslclientcert = $(ENTITLEMENT_CERT)" >> ubi.repo
	@echo "sslverifystatus = 1" >> ubi.repo
	@echo "metadata_expire = 86400" >> ubi.repo
	@echo "enabled_metadata = 0" >> ubi.repo

# Generate rpms.in.yaml listing RPM packages installed via yum, dnf, or microdnf from CONTAINERFILE
# Usage: make generate-rpms-in-yaml [CONTAINERFILE=<path>]
# Example: make generate-rpms-in-yaml CONTAINERFILE=Containerfile
#          make generate-rpms-in-yaml (uses default CONTAINERFILE=Dockerfile)
.PHONY: generate-rpms-in-yaml
generate-rpms-in-yaml:
	@if [ ! -f "$(CONTAINERFILE)" ]; then \
		exit 1; \
	fi
	@if ! command -v $(AWK) >/dev/null 2>&1; then \
		exit 1; \
	fi; \
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
		echo "packages: [$$(echo "$$packages" | tr '\n' ',' | sed -E 's/,/, /g; s/, $$//')]" > rpms.in.yaml; \
		echo "contentOrigin:" >> rpms.in.yaml; \
		echo "  repofiles: [\"./ubi.repo\"]" >> rpms.in.yaml; \
		echo "moduleEnable: [\"postgresql:16\"]" >> rpms.in.yaml; \
		echo "arches: [x86_64]" >> rpms.in.yaml; \
	fi

# Generate rpms.lock.yaml using rpm-lockfile-prototype
# Usage: make generate-rpm-lockfile [BASE_IMAGE=<image>]
# Example: make generate-rpm-lockfile BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest
#          make generate-rpm-lockfile (uses default BASE_IMAGE)
.PHONY: generate-rpm-lockfile
generate-rpm-lockfile: rpms.in.yaml
	@curl -s https://raw.githubusercontent.com/konflux-ci/rpm-lockfile-prototype/refs/heads/main/Containerfile | \
	podman build -t localhost/rpm-lockfile-prototype -
	@container_dir=/work; \
	podman run --rm -v $${PWD}:$${container_dir}:Z -v /etc/pki/entitlement:/etc/pki/entitlement:Z -v /etc/rhsm/ca/:/etc/rhsm/ca/:Z localhost/rpm-lockfile-prototype:latest --outfile=$${container_dir}/rpms.lock.yaml --image $(BASE_IMAGE) $${container_dir}/rpms.in.yaml
	@if [ ! -f rpms.lock.yaml ]; then \
		echo "Error: rpms.lock.yaml was not generated"; \
		exit 1; \
	fi

# Generate requirements.txt from Poetry or Pipenv lock files
# Usage: make generate-requirements-txt
# Example: make generate-requirements-txt
.PHONY: generate-requirements-txt
generate-requirements-txt:
	@if [ -f poetry.lock ]; then \
		poetry export --format requirements.txt --output requirements.txt; \
	elif [ -f Pipfile.lock ]; then \
		pipenv requirements > requirements.txt; \
	elif [ -f requirements.txt ]; then \
		exit 0; \
	else \
		echo "Error: Unable to generate requirements.txt file"; \
		exit 1; \
	fi
	@if [ ! -f requirements.txt ]; then \
		echo "Error: requirements.txt was not generated"; \
		exit 1; \
	fi

# Generate requirements-build.in from [build-system] in pyproject.toml
# Usage: make generate-requirements-build-in
# Example: make generate-requirements-build-in
.PHONY: generate-requirements-build-in
generate-requirements-build-in:
	@> requirements-build.in
	@> requirements-extras.in
	@if [ ! -f pyproject.toml ]; then \
		echo "Error: pyproject.toml not found"; \
		exit 1; \
	fi
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
	> requirements-build.in; \
	> requirements-extras.in; \
	for pkg in $$requires; do \
		if echo "$$pkg" | grep -q "=="; then \
			echo "$$pkg" >> requirements-build.in; \
		else \
			version=$$(curl -s "https://pypi.org/pypi/$$pkg/json" | \
			sed -n 's/.*"version":[[:space:]]*"\([^"]*\)".*/\1/p' | head -1); \
			if [ -z "$$version" ]; then \
				echo "Error: Failed to fetch version for $$pkg from PyPI"; \
				exit 1; \
			fi; \
			echo "$$pkg==$$version" >> requirements-build.in; \
		fi; \
	done
	@if [ ! -f .hermetic_builds/add_manual_build_dependencies.sh ] || [ ! -f .hermetic_builds/add_manual_build_dependencies.sh ]; then \
		echo "Error: Missing scripts in .hermetic_builds directory"; \
		exit 1; \
	fi
	.hermetic_builds/add_manual_build_dependencies.sh
	@if [ ! -f requirements-build.in ]; then \
		echo "Error: requirements-build.in was not generated"; \
		exit 1; \
	fi

# Generate requirements-build.txt using pip-tools and pybuild-deps
# Usage: make generate-requirements-build-txt [BASE_IMAGE=<image>]
# Example: make generate-requirements-build-txt BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest
.PHONY: generate-requirements-build-txt
generate-requirements-build-txt:
	@if [ ! -f requirements.txt ]; then \
		echo "Error: requirements.txt not found"; \
		exit 1; \
	fi
	@if [ ! -f .hermetic_builds/prep_python_build_container_dependencies.sh ] || [ ! -f .hermetic_builds/generate_requirements_build.sh ]; then \
		echo "Error: Missing scripts in .hermetic_builds directory"; \
		exit 1; \
	fi
	@podman run -it -v "$$(pwd)":/var/tmp:rw --user 0:0 $(BASE_IMAGE) bash -c "/var/tmp/.hermetic_builds/prep_python_build_container_dependencies.sh && /var/tmp/.hermetic_builds/generate_requirements_build.sh"
	@if [ ! -f requirements-build.txt ]; then \
		echo "Error: requirements-build.txt was not generated"; \
		exit 1; \
	fi
