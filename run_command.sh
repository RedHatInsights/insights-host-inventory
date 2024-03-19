#!/bin/bash

# Provide the complete command to run a service
if [ "$#" -eq 0 ]; then
    echo "ERROR: Provide a command to start one of the following:"
    echo "    - API server,"
    echo "    - host_reaper,"
    echo "    - system_profile_validator,"
    echo "    - pendo_syncher", or
    echo "    - host_synchronizer"
    exit 1
fi

# The command to execute is provided by the user of this script
command_to_run="$@"

# Run the command
eval "$command_to_run"
