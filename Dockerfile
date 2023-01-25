FROM registry.access.redhat.com/ubi8/ubi-minimal:latest

USER root

# install postgresql from centos if not building on RHSM system
RUN FULL_RHEL=$(microdnf repolist --enabled | grep rhel-8) ; \
    if [ -z "$FULL_RHEL" ] ; then \
        rpm -Uvh http://mirror.centos.org/centos/8-stream/BaseOS/x86_64/os/Packages/centos-stream-repos-8-4.el8.noarch.rpm \
                 http://mirror.centos.org/centos/8-stream/BaseOS/x86_64/os/Packages/centos-gpg-keys-8-4.el8.noarch.rpm && \
        sed -i 's/^\(enabled.*\)/\1\npriority=200/;' /etc/yum.repos.d/CentOS*.repo ; \
    fi

RUN microdnf module enable postgresql:13 python38:3.8 && \
    microdnf install --setopt=tsflags=nodocs -y postgresql python38 && \
    microdnf install -y rsync tar procps-ng make snappy && \
    microdnf upgrade -y && \
    microdnf clean all

WORKDIR /opt/app-root/src
COPY . .

RUN python -m pip install --upgrade pip && \
    python -m pip install pipenv && \
    pipenv install --system --dev

USER 1001

CMD bash -c 'make upgrade_db && make run_inv_mq_service'
