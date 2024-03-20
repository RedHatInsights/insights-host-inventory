#!/bin/bash

if [ "$#" -eq 0 ]; then
    echo "ERROR: No command provided to run."
    exit 1
fi

# The command to execute is provided by the user of this script
command_to_run="$@"

# Run the command
eval "$command_to_run"
