#!/bin/bash
set -x

# WARNING: Running this script can take up to 3 hours

# This script has these dependencies
# - iqe-core
# - iqe-host-inventory-plugin
# - iqe-ingress-plugin
# - iqe-advisor-plugin

DATE=$(date -d now +%F)
ENV=stage_proxy
REGULAR_ACCOUNT=insights_test_day
SPECIAL_ACCOUNT=edge_parity_special
REG_ACC_ARCHIVE_PREFIX=edge_stage_test_day
SPC_ACC_ARCHIVE_PREFIX=edge_stage_special
HOSTS_PER_ARCHIVE=10

for i in {01..30}
do

  # Conventional hosts
  for user in $REGULAR_ACCOUNT $SPECIAL_ACCOUNT
  do
    ENV_FOR_DYNACONF=$ENV iqe host_inventory create-hosts --user $user -n $HOSTS_PER_ARCHIVE --archive-repo ingress --base-archive rhel87_core_collect.tar.gz --display-name-prefix user-${i}.${DATE}.rhel
    ENV_FOR_DYNACONF=$ENV iqe host_inventory create-hosts --user $user -n $HOSTS_PER_ARCHIVE --archive-repo ingress --base-archive centos79.tar.gz --display-name-prefix user-${i}.${DATE}.centos
    ENV_FOR_DYNACONF=$ENV iqe host_inventory create-hosts --user $user -n $HOSTS_PER_ARCHIVE --archive-repo ingress --base-archive sap_core_collect.tar.gz --display-name-prefix user-${i}.${DATE}.sap
    ENV_FOR_DYNACONF=$ENV iqe host_inventory create-hosts --user $user -n $HOSTS_PER_ARCHIVE --archive-repo advisor --base-archive sample_archive_pathways.tar.gz --display-name-prefix user-${i}.${DATE}.advisor
  done

  # Edge hosts for regular account
  ENV_FOR_DYNACONF=$ENV iqe host_inventory create-hosts --user $REGULAR_ACCOUNT -n $HOSTS_PER_ARCHIVE --archive-repo ingress --base-archive ${REG_ACC_ARCHIVE_PREFIX}.tar.gz --display-name-prefix user-${i}.${DATE}.edge
  ENV_FOR_DYNACONF=$ENV iqe host_inventory create-hosts --user $REGULAR_ACCOUNT -n $HOSTS_PER_ARCHIVE --archive-repo ingress --base-archive ${REG_ACC_ARCHIVE_PREFIX}_pathways.tar.gz --display-name-prefix user-${i}.${DATE}.edge-advisor
  ENV_FOR_DYNACONF=$ENV iqe host_inventory create-hosts --user $REGULAR_ACCOUNT -n $HOSTS_PER_ARCHIVE --archive-repo ingress --base-archive ${REG_ACC_ARCHIVE_PREFIX}_outdated.tar.gz --display-name-prefix user-${i}.${DATE}.edge-outdated

  # Edge hosts for special account (should use old Edge management service)
  ENV_FOR_DYNACONF=$ENV iqe host_inventory create-hosts --user $SPECIAL_ACCOUNT -n $HOSTS_PER_ARCHIVE --archive-repo ingress --base-archive ${SPC_ACC_ARCHIVE_PREFIX}.tar.gz --display-name-prefix user-${i}.${DATE}.edge
  ENV_FOR_DYNACONF=$ENV iqe host_inventory create-hosts --user $SPECIAL_ACCOUNT -n $HOSTS_PER_ARCHIVE --archive-repo ingress --base-archive ${SPC_ACC_ARCHIVE_PREFIX}_pathways.tar.gz --display-name-prefix user-${i}.${DATE}.edge-advisor
  ENV_FOR_DYNACONF=$ENV iqe host_inventory create-hosts --user $SPECIAL_ACCOUNT -n $HOSTS_PER_ARCHIVE --archive-repo ingress --base-archive ${SPC_ACC_ARCHIVE_PREFIX}_outdated.tar.gz --display-name-prefix user-${i}.${DATE}.edge-outdated

done
