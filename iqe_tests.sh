#!/bin/bash

# Prepare env
source $(pwd)/pr_check_common.sh

export REF_ENV="insights-stage"
export IQE_MARKER_EXPRESSION="backend and not resilience and not cert_auth and not rbac_dependent"
export IQE_FILTER_EXPRESSION=""
export IQE_CJI_TIMEOUT="2h"
export RESERVE_DURATION="2h"

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
