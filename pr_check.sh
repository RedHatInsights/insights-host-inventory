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

# If local IQE plugin is configured, use custom script to deploy and test
# Otherwise, use the standard cji_smoke_test.sh
if [ "$IQE_INSTALL_LOCAL_PLUGIN" = "true" ]; then
    echo "Using local IQE plugin for CJI tests"
    source $APP_ROOT/run_cji_with_local_plugin.sh
else
    echo "Using standard IQE plugin from Nexus for CJI tests"
    source $CICD_ROOT/cji_smoke_test.sh
fi

source $CICD_ROOT/post_test_results.sh
