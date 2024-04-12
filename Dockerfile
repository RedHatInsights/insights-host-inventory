FROM registry.access.redhat.com/ubi8/ubi-minimal:latest

ARG TEST_IMAGE=false

USER root

# install postgresql from centos if not building on RHSM system
RUN FULL_RHEL=$(microdnf repolist --enabled | grep rhel-8) ; \
    if [ -z "$FULL_RHEL" ] ; then \
        rpm -Uvh http://mirror.centos.org/centos/8-stream/BaseOS/x86_64/os/Packages/centos-stream-repos-8-4.el8.noarch.rpm \
                 http://mirror.centos.org/centos/8-stream/BaseOS/x86_64/os/Packages/centos-gpg-keys-8-4.el8.noarch.rpm && \
        sed -i 's/^\(enabled.*\)/\1\npriority=200/;' /etc/yum.repos.d/CentOS*.repo ; \
    fi

ENV APP_ROOT=/opt/app-root/src
WORKDIR $APP_ROOT

RUN microdnf module enable postgresql:13 python39:3.9 && \
    microdnf upgrade -y && \
    microdnf install --setopt=tsflags=nodocs -y postgresql python39 rsync tar procps-ng make snappy && \
    rpm -qa | sort > packages-before-devel-install.txt && \
    microdnf install --setopt=tsflags=nodocs -y libpq-devel python39-devel gcc && \
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
COPY logconfig.yaml logconfig.yaml
COPY manage.py manage.py
COPY pendo_syncher.py pendo_syncher.py
COPY Pipfile Pipfile
COPY Pipfile.lock Pipfile.lock
COPY pytest.ini pytest.ini
COPY rebuild_events_topic.py rebuild_events_topic.py
COPY run_gunicorn.py run_gunicorn.py
COPY run_command.sh run_command.sh
COPY run_pg_repack.py run_pg_repack.py
COPY system_profile_validator.py system_profile_validator.py

ENV PIP_NO_CACHE_DIR=1
ENV PIPENV_CLEAR=1
ENV PIPENV_VENV_IN_PROJECT=1

RUN python3 -m pip install --upgrade pip setuptools wheel && \
    python3 -m pip install pipenv && \
    python3 -m pip install dumb-init && \
    pipenv install --system --dev

# allows pre-commit and unit tests to run successfully within the container if image is built in "test" environment
RUN if [ "$TEST_IMAGE" = "true" ]; then \
        microdnf install --setopt=tsflags=nodocs -y git && \
        chgrp -R 0 $APP_ROOT && \
        chmod -R g=u $APP_ROOT ; \
    fi

# remove devel packages that were only necessary for psycopg2 to compile
RUN microdnf remove -y $( comm -13 packages-before-devel-install.txt packages-after-devel-install.txt ) && \
    rm packages-before-devel-install.txt packages-after-devel-install.txt && \
    microdnf clean all

USER 1001

ENTRYPOINT [ "dumb-init", "./run_command.sh" ]
