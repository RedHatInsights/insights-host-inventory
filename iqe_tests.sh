#!/bin/bash

# Prepare env
source $(pwd)/pr_check_common.sh

export REF_ENV="insights-stage"
export IQE_MARKER_EXPRESSION="not resilience and not cert_auth and not rbac_dependent"
export IQE_FILTER_EXPRESSION=""
export IQE_CJI_TIMEOUT="3h"
export RESERVE_DURATION="3h"

# Wait until the PR image is built
check_image
if [[ $? -ne 0 ]]
then
  echo "Image '$IMAGE:$IMAGE_TAG' not found in quay, exiting script"
  exit 1
fi

# Deploy ephemeral env and run IQE tests
source $CICD_ROOT/deploy_ephemeral_env.sh

# Workaround for bonfire CICD script issue: https://github.com/RedHatInsights/bonfire/issues/283
# Restart `oc logs -f` after 1 hour
sed -i \
's/oc_wrapper logs -n $NAMESPACE $POD -c $CONTAINER -f &/ \
oc_wrapper logs -n $NAMESPACE $POD -c $CONTAINER -f \&\n \
LOGS_PID=$!\n sleep 3600\n kill $LOGS_PID\n \
oc_wrapper logs -n $NAMESPACE $POD -c $CONTAINER -f \&/' \
$CICD_ROOT/cji_smoke_test.sh

source $CICD_ROOT/cji_smoke_test.sh
source $CICD_ROOT/post_test_results.sh
