#!/bin/bash
set -euo pipefail

pgRepo="https://copr.fedorainfracloud.org/coprs/g/insights/postgresql-16/repo/epel-9/group_insights-postgresql-16-epel-9.repo"
if ! microdnf module enable -y postgresql:16; then
    curl -fSLo /etc/yum.repos.d/postgresql.repo "$pgRepo"
fi
microdnf upgrade -y
microdnf install --setopt=tsflags=nodocs -y postgresql python3.12 python3.12-pip rsync tar procps-ng make which
microdnf install --setopt=tsflags=nodocs -y libpq-devel python3.12-devel gcc cargo rust glibc-devel krb5-libs krb5-devel libffi-devel gcc-c++ make zlib zlib-devel openssl-libs openssl-devel libzstd libzstd-devel unzip which diffutils
microdnf clean all

python312=$(command -v python3.12)
pip312=$(command -v pip3.12)
ln -sf "$python312" /usr/local/bin/python3
ln -sf "$python312" /usr/local/bin/python
ln -sf "$pip312" /usr/local/bin/pip3
ln -sf "$pip312" /usr/local/bin/pip
microdnf install -y wget
