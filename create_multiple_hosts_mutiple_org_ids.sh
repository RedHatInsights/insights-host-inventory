#!/bin/bash

# Script to loop a specified number of times and run a make command with arguments.
#
# Usage:
#   ./create_multiple_hosts_mutiple_org_ids.sh <number_of_org_ids> [make_target] [VAR=VALUE ...]
#
# Description:
#   For each iteration from 1..N, this script invokes `make` with the provided target and variables,
#   and injects NUM_OF_DIFF_ORG_ID=<i> into the environment/CLI for `make`.
#   This is useful for generating data across multiple org_ids where downstream logic reads
#   the NUM_OF_DIFF_ORG_ID value to vary the org_id per run.
#
# Examples:
#   # Generate 4 org ids using the test producer target
#   ./create_multiple_hosts_mutiple_org_ids.sh 4 run_inv_mq_service_test_producer
#
#   # Pass additional make variables (these are forwarded as-is)
#   ./create_multiple_hosts_mutiple_org_ids.sh 3 run_inv_mq_service_test_producer \
#     INVENTORY_HOST_ACCOUNT=5894300 HOST_TYPE=sap
#
#   # Call with only variables (no explicit target)
#   ./create_multiple_hosts_mutiple_org_ids.sh 2 INVENTORY_HOST_ACCOUNT=5894300

print_usage() {
  cat <<'EOF'
Usage:
  create_multiple_hosts_mutiple_org_ids.sh <number_of_org_ids> [make_target] [VAR=VALUE ...]

Description:
  Loops <number_of_org_ids> times and invokes "make" on each iteration, passing through any provided
  target/variables and injecting NUM_OF_DIFF_ORG_ID=<i> (1-based) so downstream logic can vary org_id.

Examples:
  # Generate 4 different org ids using the test producer
  ./create_multiple_hosts_mutiple_org_ids.sh 4 run_inv_mq_service_test_producer

  # Pass additional make variables
  ./create_multiple_hosts_mutiple_org_ids.sh 3 run_inv_mq_service_test_producer \
    INVENTORY_HOST_ACCOUNT=5894300 HOST_TYPE=sap

  # Call make with no target (variables only)
  ./create_multiple_hosts_mutiple_org_ids.sh 2 run_inv_mq_service_test_producer \
  INVENTORY_HOST_ACCOUNT=foo HOST_TYPE=sap
EOF
}

# Help flag
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  print_usage
  exit 0
fi

# Read first argument as number of org ids (iterations)
iterations="$1"

# Require iterations argument
if [ -z "$iterations" ]; then
  echo "Error: <number_of_org_ids> is required."
  echo "Usage: $0 <number_of_org_ids> [run_inv_mq_service_test_producer] [make_argument1=value1 ...]"
  exit 1
fi

# Validate that iterations is a positive integer
if ! [[ "$iterations" =~ ^[0-9]+$ ]]; then
  echo "Error: <number_of_org_ids> must be a positive integer."
  echo "Usage: $0 <number_of_org_ids> [run_inv_mq_service_test_producer] [make_argument1=value1 ...]"
  exit 1
fi
# Shift the first argument (iterations) so that $@ contains only the make arguments
shift

# Check if there are any arguments for make
if [ $# -eq 0 ]; then
  echo "Warning: No arguments provided for the 'make' command."
  echo "Make will be called without any targets or variables."
fi

# Loop from 1 to the specified number of iterations
for i in $(seq 1 "$iterations")
do
  echo "------------------------------------"
  echo "Iteration $i of $iterations"
  echo "Running: make $@ NUM_OF_DIFF_ORG_ID=$i"
  echo "------------------------------------"

  # Run the make command with all remaining arguments
  make "$@" NUM_OF_DIFF_ORG_ID="$i"

    # Check the exit status of the make command
  if [ $? -ne 0 ]; then
    echo "Error: 'make $@' failed on iteration $i"
    # Decide if you want to exit the script on failure or continue
    # exit 1 # Uncomment to exit on failure
  fi
  echo "" # Add a newline for better readability
done

echo "------------------------------------"
echo "Script finished."
echo "------------------------------------"
