#!/bin/bash

# Prepare env
source $(pwd)/pr_check_common.sh

export IQE_MARKER_EXPRESSION="backend and smoke"
export IQE_FILTER_EXPRESSION=""
export IQE_CJI_TIMEOUT="30m"

# build the PR commit image
source $CICD_ROOT/build.sh

# Run the unit tests
source $APP_ROOT/unit_test.sh

# Run IQE tests
source $CICD_ROOT/deploy_ephemeral_env.sh
source $CICD_ROOT/cji_smoke_test.sh
source $CICD_ROOT/post_test_results.sh
