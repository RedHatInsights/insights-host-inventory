#!/bin/bash
# Usage: ./append_repo_config.sh REPO_NAME REPO_DESC REPO_URL ENTITLEMENT_KEY ENTITLEMENT_CERT

REPO_NAME="$1"
REPO_DESC="${REPO_DESC:-$2}"
REPO_URL="${REPO_URL:-$3}"
ENTITLEMENT_KEY="${ENTITLEMENT_KEY:-$4}"
ENTITLEMENT_CERT="${ENTITLEMENT_CERT:-$5}"

cat <<EOF

[$REPO_NAME]
name = $REPO_DESC
baseurl = $REPO_URL
enabled = 1
gpgkey = file:///etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release
gpgcheck = 1
sslverify = 1
sslcacert = /etc/rhsm/ca/redhat-uep.pem
sslclientkey = $ENTITLEMENT_KEY
sslclientcert = $ENTITLEMENT_CERT
sslverifystatus = 1
metadata_expire = 86400
enabled_metadata = 0
EOF
