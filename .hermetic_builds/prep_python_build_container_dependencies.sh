#!/bin/bash

# PostgreSQL 16 is the default stream on RHEL/UBI 10 (no modules).
# Match the application image Python version from the Dockerfile.
microdnf upgrade -y && \
    microdnf install --setopt=tsflags=nodocs -y postgresql python3.14 python3.14-pip rsync tar procps-ng make which && \
    microdnf install --setopt=tsflags=nodocs -y libpq-devel python3.14-devel gcc cargo rust glibc-devel krb5-libs krb5-devel libffi-devel gcc-c++ make zlib zlib-devel openssl-libs openssl-devel libzstd libzstd-devel unzip which diffutils && \
    microdnf clean all

set -ex && if [ -e `which python3.14` ]; then ln -sf `which python3.14` /usr/local/bin/python3; fi
set -ex && if [ -e `which python3.14` ]; then ln -sf `which python3.14` /usr/local/bin/python; fi
set -ex && if [ -e `which pip3.14` ]; then ln -sf `which pip3.14` /usr/local/bin/pip3; fi
set -ex && if [ -e `which pip3.14` ]; then ln -sf `which pip3.14` /usr/local/bin/pip; fi
# Fallback when pip is only available as a module
python3.14 -m pip --version >/dev/null 2>&1 || microdnf install --setopt=tsflags=nodocs -y python3.14-pip
microdnf install -y wget
