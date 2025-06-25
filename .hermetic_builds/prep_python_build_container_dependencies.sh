#!/bin/bash

pgRepo="https://copr.fedorainfracloud.org/coprs/g/insights/postgresql-16/repo/epel-9/group_insights-postgresql-16-epel-9.repo"
microdnf module enable -y postgresql:16  || curl -o /etc/yum.repos.d/postgresql.repo $pgRepo && \
    microdnf upgrade -y && \
    microdnf install --setopt=tsflags=nodocs -y postgresql python39 rsync tar procps-ng make which && \
    microdnf install --setopt=tsflags=nodocs -y libpq-devel python3-devel gcc cargo rust glibc-devel krb5-libs krb5-devel libffi-devel gcc-c++ make zlib zlib-devel openssl-libs openssl-devel libzstd libzstd-devel unzip which diffutils && \
    microdnf clean all

set -ex && if [ -e `which python3.9` ]; then ln -s `which python3.9` /usr/local/bin/python3; fi
set -ex && if [ -e `which python3.9` ]; then ln -s `which python3.9` /usr/local/bin/python; fi
set -ex && if [ -e `which pip3.9` ]; then ln -s `which pip3.9` /usr/local/bin/pip3; fi
set -ex && if [ -e `which pip3.9` ]; then ln -s `which pip3.9` /usr/local/bin/pip; fi
microdnf install -y wget
