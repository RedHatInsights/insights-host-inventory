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

RUN microdnf module enable postgresql:13 python38:3.8 && \
    microdnf upgrade -y && \
    microdnf install --setopt=tsflags=nodocs -y postgresql python38 rsync tar procps-ng make snappy && \
    rpm -qa | sort > packages-before-devel-install.txt && \
    microdnf install --setopt=tsflags=nodocs -y libpq-devel python38-devel gcc && \
    rpm -qa | sort > packages-after-devel-install.txt

COPY . .

ENV PIP_NO_CACHE_DIR=1
ENV PIPENV_CLEAR=1
ENV PIPENV_VENV_IN_PROJECT=1

RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install pipenv && \
    pipenv install --system --dev

# allows unit tests to run successfully within the container if image is built in "test" environment
RUN if [ "$TEST_IMAGE" = "true" ]; then chgrp -R 0 $APP_ROOT && chmod -R g=u $APP_ROOT; fi

# remove devel packages that were only necessary for psycopg2 to compile
RUN microdnf remove -y $( comm -13 packages-before-devel-install.txt packages-after-devel-install.txt ) && \
    rm packages-before-devel-install.txt packages-after-devel-install.txt && \
    microdnf clean all

USER 1001

CMD bash -c 'make upgrade_db && make run_inv_mq_service'
