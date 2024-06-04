#!/bin/bash

# Prepare env
source $(pwd)/pr_check_common.sh

export REF_ENV="insights-stage"
export IQE_MARKER_EXPRESSION="rbac_dependent and not cert_auth and not service_accounts"
export IQE_FILTER_EXPRESSION=""
export IQE_CJI_TIMEOUT="1h"
export EXTRA_DEPLOY_ARGS="-p host-inventory/BYPASS_RBAC=false"

# Wait until the PR image is built
check_image
if [[ $? -ne 0 ]]
then
  echo "Image '$IMAGE:$IMAGE_TAG' not found in quay, exiting script"
  exit 1
fi

# Deploy ephemeral env and run IQE tests
source $CICD_ROOT/deploy_ephemeral_env.sh
source $CICD_ROOT/cji_smoke_test.sh
source $CICD_ROOT/post_test_results.sh
