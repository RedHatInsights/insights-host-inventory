FROM registry.access.redhat.com/ubi9/ubi-minimal:latest

ARG pgRepo="https://copr.fedorainfracloud.org/coprs/g/insights/postgresql-16/repo/epel-9/group_insights-postgresql-16-epel-9.repo"
ARG TEST_IMAGE=false

USER root

ENV APP_ROOT=/opt/app-root/src
WORKDIR $APP_ROOT

RUN (microdnf module enable -y postgresql:16 || curl -o /etc/yum.repos.d/postgresql.repo $pgRepo) && \
    microdnf upgrade -y && \
    microdnf install --setopt=tsflags=nodocs -y postgresql python39 rsync tar procps-ng make && \
    rpm -qa | sort > packages-before-devel-install.txt && \
    microdnf install --setopt=tsflags=nodocs -y libpq-devel python3-devel gcc && \
    rpm -qa | sort > packages-after-devel-install.txt

COPY api/ api/
COPY app/ app/
COPY lib/ lib/
COPY migrations/ migrations/
COPY swagger/ swagger/
COPY tests/ tests/
COPY utils/ utils/
COPY Makefile Makefile
COPY gunicorn.conf.py gunicorn.conf.py
COPY host_reaper.py host_reaper.py
COPY host_synchronizer.py host_synchronizer.py
COPY inv_mq_service.py inv_mq_service.py
COPY inv_publish_hosts.py inv_publish_hosts.py
COPY inv_export_service.py inv_export_service.py
COPY logconfig.yaml logconfig.yaml
COPY manage.py manage.py
COPY pendo_syncher.py pendo_syncher.py
COPY Pipfile Pipfile
COPY Pipfile.lock Pipfile.lock
COPY pytest.ini pytest.ini
COPY rebuild_events_topic.py rebuild_events_topic.py
COPY run_gunicorn.py run_gunicorn.py
COPY run_command.sh run_command.sh
COPY run.py run.py
COPY system_profile_validator.py system_profile_validator.py
COPY inv_migration_runner.py inv_migration_runner.py
COPY app_migrations/ app_migrations/

ENV PIP_NO_CACHE_DIR=1
ENV PIPENV_CLEAR=1
ENV PIPENV_VENV_IN_PROJECT=1

RUN python3 -m pip install --upgrade pip setuptools wheel && \
    python3 -m pip install pipenv && \
    python3 -m pip install dumb-init && \
    pipenv install --system --dev

# allows pre-commit and unit tests to run successfully within the container if image is built in "test" environment
RUN if [ "$TEST_IMAGE" = "true" ]; then \
        microdnf module enable -y nodejs:20 && \
        microdnf install --setopt=tsflags=nodocs -y git npm which && \
        chgrp -R 0 $APP_ROOT && \
        chmod -R g=u $APP_ROOT ; \
    fi

# remove devel packages that were only necessary for psycopg2 to compile
RUN microdnf remove  -y  libpq-devel python3-devel gcc && \
    microdnf clean all

USER 1001

ENTRYPOINT [ "dumb-init", "./run_command.sh" ]
